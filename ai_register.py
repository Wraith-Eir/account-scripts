#!/usr/bin/env python3

from __future__ import annotations

import argparse
import getpass
import json
import logging
import random
import re
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.prompt import Prompt
from rich.table import Table
from rich.text import Text

REGISTER_URL = "https://chat.qwen.ai/auth?mode=register"
MAILBOX_LOGIN_URL = "https://login.mailbox.org"
SESSION_DIR = Path.home() / ".config" / "auto-register"
LOG_DIR = Path.home() / ".local" / "share" / "auto-register"

CAPTCHA_SELECTORS = [
    ".cf-turnstile",
    ".h-captcha",
    ".g-recaptcha",
    "iframe[src*='captcha']",
    "iframe[src*='turnstile']",
    "iframe[src*='hcaptcha']",
]

CAPTCHA_TEXT_PATTERNS = [
    "Verify you are human",
    "Checking your browser",
    "Just a moment",
    "Enable JavaScript and cookies to continue",
]

console = Console()


def _setup_logging() -> logging.Logger:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_file = LOG_DIR / "error.log"
    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[
            logging.FileHandler(log_file, encoding="utf-8"),
        ],
    )
    return logging.getLogger("auto-register")


logger = _setup_logging()


@dataclass
class UserCredentials:
    full_name: str
    email: str
    password: str
    mailbox_password: str


def detect_arch() -> bool:
    try:
        with open("/etc/os-release", encoding="utf-8") as f:
            return "arch" in f.read().lower()
    except FileNotFoundError:
        return False


def check_system_deps() -> list[str]:
    missing: list[str] = []
    needed = [
        ("chromium", "chromium"),
        ("nss", "nss"),
        ("harfbuzz", "harfbuzz-icu"),
    ]
    for binary, pkg in needed:
        if not shutil.which(binary):
            if pkg in ("nss", "harfbuzz-icu"):
                try:
                    result = subprocess.run(
                        ["pacman", "-Q", pkg],
                        capture_output=True,
                        text=True,
                        timeout=5,
                    )
                    if result.returncode != 0:
                        missing.append(pkg)
                except (FileNotFoundError, subprocess.TimeoutExpired):
                    pass
            else:
                missing.append(pkg)
    return missing


def print_system_warnings() -> None:
    if not detect_arch():
        return
    missing = check_system_deps()
    if missing:
        pkgs_str = " ".join(missing)
        warning_panel = Panel(
            Text(
                f"Missing system packages: {pkgs_str}\n\n"
                f"Run:\n  sudo pacman -S {pkgs_str}\n\n"
                f"And also run:\n  playwright install-deps chromium\n"
                f"  playwright install chromium",
                style="yellow",
            ),
            title="[!] Warning",
            border_style="yellow",
            padding=(1, 2),
        )
        console.print(warning_panel)
        console.print()


def validate_email(email: str) -> bool:
    return bool(re.match(r"^[a-zA-Z0-9_.+-]+@mailbox\.org$", email))


def validate_password(pw: str) -> bool:
    return len(pw) >= 8


def get_user_input() -> UserCredentials:
    console.print(
        Panel(
            "Fill in the details below to create the account",
            title="[bold green]Account Details",
            border_style="green",
        )
    )
    console.print()

    full_name = ""
    while not full_name.strip():
        full_name = Prompt.ask("  [bold]Full Name")
        if not full_name.strip():
            console.print("  [red]Name cannot be empty.[/red]")

    email = ""
    while not validate_email(email):
        email = Prompt.ask("  [bold]Email (@mailbox.org)")
        if not validate_email(email):
            console.print(
                "  [red]Email must be a valid @mailbox.org address.[/red]"
            )

    password = ""
    while not validate_password(password):
        password = Prompt.ask(
            "  [bold]Password (min 8 chars)",
            password=True,
        )
        if not validate_password(password):
            console.print("  [red]Password must be at least 8 characters.[/red]")

    confirm = ""
    while confirm != password:
        confirm = Prompt.ask("  [bold]Confirm Password", password=True)
        if confirm != password:
            console.print("  [red]Passwords do not match.[/red]")

    console.print()
    console.print(
        "  [dim]Password for mailbox.org login (usually the same as the email)[/dim]"
    )
    console.print()
    mailbox_password = Prompt.ask("  [bold]Mailbox.org Password", password=True)

    return UserCredentials(
        full_name=full_name.strip(),
        email=email.strip(),
        password=password,
        mailbox_password=mailbox_password,
    )


def _human_delay(low: float = 0.5, high: float = 1.5) -> None:
    time.sleep(random.uniform(low, high))


def _check_captcha(page: Any) -> bool:
    for selector in CAPTCHA_SELECTORS:
        try:
            if page.locator(selector).count() > 0:
                return True
        except Exception:
            pass

    try:
        body_text = page.inner_text("body")
        for pattern in CAPTCHA_TEXT_PATTERNS:
            if pattern.lower() in body_text.lower():
                return True
    except Exception:
        pass

    return False


def _wait_for_captcha(page: Any) -> None:
    panel = Panel(
        Text(
            "\n[CAPTCHA DETECTED] Solve it manually in the browser "
            "and press ENTER in the terminal to continue...",
            style="bold red",
        ),
        title="[!] Waiting",
        border_style="red",
    )
    console.print(panel)
    input()
    _human_delay(1, 2)


class Automation:
    def __init__(
        self, creds: UserCredentials, headless: bool = False
    ) -> None:
        self.creds = creds
        self.headless = headless
        self.browser: Any = None
        self.page: Any = None

    def start_browser(self) -> None:
        from playwright.sync_api import sync_playwright

        self._pw = sync_playwright().start()
        ua = (
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
        )
        console.print("[dim]Launching Chromium...[/dim]")
        self.browser = self._pw.chromium.launch(
            headless=self.headless,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
            ],
        )
        context = self.browser.new_context(
            user_agent=ua,
            viewport={"width": 1280, "height": 800},
            locale="en-US",
        )
        context.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined});"
        )
        self.page = context.new_page()

    def close_browser(self) -> None:
        if self.browser:
            self.browser.close()
        if hasattr(self, "_pw"):
            self._pw.stop()

    def create_account(self) -> bool:
        assert self.page is not None

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            task = progress.add_task(
                "Navigating to registration...", total=None
            )
            self.page.goto(REGISTER_URL, timeout=30000)
            progress.update(task, description="Page loaded")
            _human_delay(1, 2)

        if _check_captcha(self.page):
            _wait_for_captcha(self.page)

        console.print("[dim]Waiting for form to load...[/dim]")
        try:
            self.page.wait_for_selector(
                "input[type='email'], input[name='email'], input[placeholder*='email' i], input[placeholder*='mail' i]",
                timeout=15000,
            )
        except Exception:
            if _check_captcha(self.page):
                _wait_for_captcha(self.page)
                self.page.wait_for_selector(
                    "input[type='email'], input[name='email'], input[placeholder*='mail' i]",
                    timeout=15000,
                )

        _human_delay(1, 2)

        self._fill_field(
            selectors=[
                "input[placeholder*='name' i]",
                "input[name='name']",
                "input[name='full_name']",
                "input[name='fullName']",
                "input[type='text']",
            ],
            value=self.creds.full_name,
            label="Name",
        )

        self._fill_field(
            selectors=[
                "input[type='email']",
                "input[name='email']",
                "input[placeholder*='mail' i]",
            ],
            value=self.creds.email,
            label="Email",
        )

        self._fill_field(
            selectors=[
                "input[type='password']",
            ],
            value=self.creds.password,
            label="Password",
            fill_all=True,
        )

        _human_delay(1, 2)

        self._click_terms_checkbox()

        _human_delay(1, 2)

        if _check_captcha(self.page):
            _wait_for_captcha(self.page)

        console.print("[dim]Clicking Register...[/dim]")
        try:
            btn_selectors = [
                "button[type='submit']",
                "button:has-text('Register')",
                "button:has-text('Sign up')",
                "button:has-text('Create')",
                "input[type='submit']",
            ]
            for sel in btn_selectors:
                btn = self.page.locator(sel).first
                if btn.count() > 0:
                    btn.click()
                    break
            else:
                console.print(
                    "[red]Register button not found. Click manually and press ENTER.[/red]"
                )
                input()
        except Exception as e:
            logger.error("Error clicking register button: %s", e)
            console.print(
                "[red]Error clicking register. Click manually and press ENTER.[/red]"
            )
            input()

        _human_delay(2, 3)

        if self._is_email_registered_error():
            return False

        return True

    def _click_terms_checkbox(self) -> None:
        checkbox_selectors = [
            "input[type='checkbox']",
            "label:has-text('Terms') input[type='checkbox']",
            "label:has-text('agree') input[type='checkbox']",
            "label:has-text('Privacy') input[type='checkbox']",
            "input[name='agree']",
            "input[name='terms']",
            "label[for*='agree'] input",
            "label[for*='terms'] input",
        ]

        for sel in checkbox_selectors:
            try:
                cb = self.page.locator(sel).first
                if cb.count() > 0 and cb.is_visible():
                    is_checked = cb.evaluate("el => el.checked")
                    if is_checked:
                        console.print("[dim]Terms checkbox already checked[/dim]")
                        return

                    cb.scroll_into_view_if_needed()
                    _human_delay(0.3, 0.6)
                    cb.click(force=True)
                    _human_delay(0.5, 1.0)
                    console.print("[dim]Terms checkbox checked[/dim]")

                    is_now_checked = cb.evaluate("el => el.checked")
                    if is_now_checked:
                        return
                    cb.evaluate("el => { el.checked = true; el.dispatchEvent(new Event('change')); }")
                    console.print("[dim]Checkbox checked via JavaScript[/dim]")
                    return
            except Exception:
                continue

        label_selectors = [
            "label:has-text('I agree')",
            "label:has-text('Accept')",
        ]
        for sel in label_selectors:
            try:
                lbl = self.page.locator(sel).first
                if lbl.count() > 0 and lbl.is_visible():
                    lbl.scroll_into_view_if_needed()
                    _human_delay(0.3, 0.6)
                    lbl.click()
                    _human_delay(0.5, 1.0)
                    console.print("[dim]Terms checkbox clicked via label[/dim]")
                    return
            except Exception:
                continue

        console.print("[yellow]Terms checkbox not found. Verify manually.[/yellow]")

    def _fill_field(
        self,
        selectors: list[str],
        value: str,
        label: str,
        fill_all: bool = False,
    ) -> None:
        for sel in selectors:
            try:
                if fill_all:
                    elements = self.page.locator(sel)
                    count = elements.count()
                    for i in range(count):
                        el = elements.nth(i)
                        if el.is_visible():
                            el.click()
                            _human_delay(0.3, 0.6)
                            el.fill(value)
                            _human_delay(0.5, 1.0)
                            console.print(
                                f"[dim]{label} filled (field {i + 1}/{count})[/dim]"
                            )
                    if count > 0:
                        return
                else:
                    el = self.page.locator(sel).first
                    if el.count() > 0 and el.is_visible():
                        el.click()
                        _human_delay(0.3, 0.6)
                        el.fill(value)
                        _human_delay(0.5, 1.0)
                        console.print(f"[dim]{label} filled[/dim]")
                        return
            except Exception:
                continue
        console.print(f"[yellow]Field '{label}' not found automatically.[/yellow]")

    def _is_email_registered_error(self) -> bool:
        try:
            body = self.page.inner_text("body")
            error_patterns = [
                "already registered",
                "already exists",
                "email already",
            ]
            for pat in error_patterns:
                if pat.lower() in body.lower():
                    console.print(
                        Panel(
                            Text(
                                "\nEmail already registered! The system reported that this account already exists.",
                                style="bold red",
                            ),
                            title="[x] Error",
                            border_style="red",
                        )
                    )
                    return True
        except Exception:
            pass
        return False

    def open_mailbox_manual(self) -> Any | None:
        assert self.page is not None

        console.print()
        console.print(
            Panel(
                "Opening Mailbox.org for manual verification...",
                title="[bold blue]Mailbox",
                border_style="blue",
            )
        )

        mailbox_page = self.page.context.new_page()

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            task = progress.add_task(
                "Navigating to Mailbox...", total=None
            )
            try:
                mailbox_page.goto(MAILBOX_LOGIN_URL, timeout=30000)
                progress.update(task, description="Page loaded")
            except Exception as e:
                logger.error("Error loading mailbox login: %s", e)
                console.print(
                    "[yellow]Could not open Mailbox login. Open manually at https://login.mailbox.org[/yellow]"
                )
                _human_delay(2, 3)
                return mailbox_page

        _human_delay(1, 2)

        email_selectors = [
            "input[name='email']",
            "input[name='login']",
            "input[type='email']",
            "input[id*='email']",
            "input[placeholder*='mail' i]",
        ]
        email_filled = False
        for sel in email_selectors:
            try:
                el = mailbox_page.locator(sel).first
                if el.count() > 0 and el.is_visible():
                    el.scroll_into_view_if_needed()
                    _human_delay(0.3, 0.6)
                    el.fill(self.creds.email)
                    _human_delay(0.5, 1.0)
                    console.print("[dim]Email filled in Mailbox[/dim]")
                    email_filled = True
                    break
            except Exception:
                continue

        if not email_filled:
            console.print(
                "[yellow]Email field not found in Mailbox. Fill manually.[/yellow]"
            )

        self._click_mailbox_continue(mailbox_page)
        _human_delay(1, 2)

        pw_selectors = [
            "input[name='password']",
            "input[type='password']",
            "input[id*='pass']",
        ]
        pw_filled = False
        for sel in pw_selectors:
            try:
                el = mailbox_page.locator(sel).first
                if el.count() > 0 and el.is_visible():
                    el.scroll_into_view_if_needed()
                    _human_delay(0.3, 0.6)
                    el.fill(self.creds.mailbox_password)
                    _human_delay(0.5, 1.0)
                    console.print("[dim]Password filled in Mailbox[/dim]")
                    pw_filled = True
                    break
            except Exception:
                continue

        if not pw_filled:
            console.print(
                "[yellow]Password field not found in Mailbox. Fill manually.[/yellow]"
            )

        _human_delay(1, 2)

        login_selectors = [
            "button[type='submit']",
            "button:has-text('Login')",
            "button:has-text('Continue')",
            "button:has-text('Sign in')",
            "button:has-text('Anmelden')",
            "input[type='submit']",
        ]
        for sel in login_selectors:
            try:
                btn = mailbox_page.locator(sel).first
                if btn.count() > 0 and btn.is_visible():
                    btn.click()
                    console.print("[dim]Mailbox login submitted[/dim]")
                    break
            except Exception:
                continue

        _human_delay(3, 5)
        console.print()
        console.print(
            Panel(
                Text(
                    "\nMailbox opened in a new tab. Manually check the "
                    "confirmation email and click the verification link.",
                    style="bold yellow",
                ),
                title="[i] Info",
                border_style="yellow",
            )
        )

        return mailbox_page

    def _click_mailbox_continue(self, page: Any) -> None:
        continue_selectors = [
            "button:has-text('Continue')",
            "button:has-text('Weiter')",
            "button:has-text('Next')",
            "button[type='submit']",
            "input[type='submit']",
        ]
        for sel in continue_selectors:
            try:
                btn = page.locator(sel).first
                if btn.count() > 0 and btn.is_visible():
                    btn.click()
                    console.print("[dim]Continue button clicked in Mailbox[/dim]")
                    return
            except Exception:
                continue
        console.print(
            "[yellow]Continue button not found. Click manually.[/yellow]"
        )

    def save_session(self) -> str | None:
        assert self.page is not None and self.browser is not None
        SESSION_DIR.mkdir(parents=True, exist_ok=True)

        safe_email = self.creds.email.replace("@", "_at_")
        session_file = SESSION_DIR / f"session_{safe_email}.json"

        try:
            cookies = self.page.context.cookies()
            storage = self.page.context.storage_state()
            session_data = {
                "email": self.creds.email,
                "created_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
                "cookies": cookies,
                "storage": storage,
            }
            session_file.write_text(
                json.dumps(session_data, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
            console.print(f"[dim]Session saved to: {session_file}[/dim]")
            return str(session_file)
        except Exception as e:
            logger.error("Error saving session: %s", e)
            console.print(f"[yellow]Could not save session: {e}[/yellow]")
            return None


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Auto-Register with manual email verification"
    )
    parser.add_argument(
        "--headless",
        action="store_true",
        help="Run browser in headless mode",
    )
    parser.add_argument(
        "--email",
        help="Mailbox.org email (skips interactive input)",
    )
    parser.add_argument(
        "--name",
        help="Full name (skips interactive input)",
    )
    args = parser.parse_args()

    print_system_warnings()

    try:
        import playwright
    except ImportError:
        console.print(
            Panel(
                Text(
                    "\nPlaywright is not installed. Run:\n"
                    "  pip install -r requirements.txt\n"
                    "  playwright install chromium\n",
                    style="bold red",
                ),
                title="[x] Missing Dependency",
                border_style="red",
            )
        )
        sys.exit(1)

    if args.email and args.name:
        password = getpass.getpass("  Password (min 8 chars): ")
        while not validate_password(password):
            console.print("  [red]Password must be at least 8 characters.[/red]")
            password = getpass.getpass("  Password (min 8 chars): ")
        confirm = getpass.getpass("  Confirm Password: ")
        while confirm != password:
            console.print("  [red]Passwords do not match.[/red]")
            confirm = getpass.getpass("  Confirm Password: ")
        mailbox_pw = getpass.getpass("  Mailbox.org Password: ")
        creds = UserCredentials(
            full_name=args.name,
            email=args.email,
            password=password,
            mailbox_password=mailbox_pw,
        )
    else:
        creds = get_user_input()

    automation = Automation(creds, headless=args.headless)

    try:
        automation.start_browser()

        console.print()
        console.print(
            Panel(
                "Step 1: Filling registration form",
                title="[bold cyan]Registration",
                border_style="cyan",
            )
        )
        created = automation.create_account()
        if not created:
            console.print(
                "[red]Registration failed. Check the data and try again.[/red]"
            )
            sys.exit(1)

        console.print(
            "[dim]Waiting for confirmation page...[/dim]"
        )
        _human_delay(2, 3)

        session_path = automation.save_session()

        console.print()
        console.print(
            Panel(
                "Step 2: Opening Mailbox.org for manual verification",
                title="[bold cyan]Mailbox",
                border_style="cyan",
            )
        )
        automation.open_mailbox_manual()

        console.print()
        table = Table(
            title="[bold green]Registration Submitted!",
            border_style="green",
            box=box.ROUNDED,
        )
        table.add_column("Field", style="cyan")
        table.add_column("Value", style="green")
        table.add_row("Name", creds.full_name)
        table.add_row("Email", creds.email)
        if session_path:
            table.add_row("Session", session_path)
        console.print(table)

        console.print()
        console.print(
            "[dim]Registration and Mailbox tabs remain open.[/dim]"
        )
        console.print(
            "[dim]Check the confirmation email in Mailbox and click the verification link.[/dim]"
        )

        console.print()
        input("Press ENTER to close the browser...")

    except Exception as e:
        logger.exception("Fatal error during automation")
        console.print()
        console.print(
            Panel(
                Text(
                    f"\nFatal error: {e}\n\n"
                    f"Details saved to: {str(LOG_DIR / 'error.log')}",
                    style="bold red",
                ),
                title="[x] Error",
                border_style="red",
            )
        )
    finally:
        automation.close_browser()


if __name__ == "__main__":
    main()
