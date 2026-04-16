#!/usr/bin/env python3

from __future__ import annotations

import logging
import random
import re
import secrets
import string
import subprocess
import shutil
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from playwright.sync_api import sync_playwright, Page, Locator
from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table
from rich.text import Text

IDENTITY_URL = (
    "https://www.fakenamegenerator.com/advanced.php"
    "?t=country&n[]=no&c[]=no&gen=0&age-min=18&age-max=24"
)
REGISTER_URL = "https://register.mailbox.org/en/private1?plan=light"
LOG_DIR = Path.home() / ".local" / "share" / "auto-register"
POLL_ATTEMPTS = 2

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
class Identity:
    full_name: str
    username: str
    first_name: str
    last_name: str

    @property
    def email(self) -> str:
        return f"{self.username}@mailbox.org"


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


def print_warnings() -> None:
    if not detect_arch():
        return
    missing = check_system_deps()
    if missing:
        pkgs_str = " ".join(missing)
        console.print(
            Panel(
                Text(
                    f"Missing packages: {pkgs_str}\n\n"
                    f"sudo pacman -S {pkgs_str}\n"
                    f"playwright install chromium\n"
                    f"playwright install-deps chromium",
                    style="yellow",
                ),
                title="[!] Warning",
                border_style="yellow",
                padding=(1, 2),
            )
        )
        console.print()


def generate_password(length: int = 20) -> str:
    uppercase = string.ascii_uppercase
    lowercase = string.ascii_lowercase
    digits = string.digits
    specials = "!@#$%()"

    num_specials = secrets.choice([2, 3, 4])
    required = [
        secrets.choice(uppercase),
        secrets.choice(lowercase),
        secrets.choice(digits),
    ] + [secrets.choice(specials) for _ in range(num_specials)]

    full_pool = uppercase + lowercase + digits + specials
    remaining = length - len(required)
    if remaining < 0:
        raise ValueError(f"Password length {length} is too short for requirements")

    chars = required + [secrets.choice(full_pool) for _ in range(remaining)]
    random.shuffle(chars)
    return "".join(chars)


def _human_delay(low: float = 0.3, high: float = 0.8) -> None:
    time.sleep(random.uniform(low, high))


def _extract_full_name(page: Page) -> str | None:
    try:
        headings = page.locator("h2, h3").all()
        for h in headings:
            text = h.inner_text().strip()
            if text and len(text) < 50 and not text.startswith(("Your", "Random", "Generated")):
                if re.match(r"^[A-Z][a-z]+(\.?\s[A-Z][a-z]+)+", text):
                    return text
    except Exception:
        pass

    try:
        rows = page.locator("tr").all()
        for row in rows:
            text = row.inner_text()
            if "Full Name" in text or "full name" in text.lower():
                parts = re.split(r"Full Name", text, flags=re.IGNORECASE)
                if len(parts) > 1:
                    val = parts[1].strip().split("\n")[0].strip()
                    if val:
                        return val
    except Exception:
        pass

    try:
        body = page.inner_text("main, body")
        lines = body.split("\n")
        for line in lines:
            line = line.strip()
            if re.match(r"^[A-ZØÆÅ][a-zøæåéèêë]+(\s+[A-ZØÆÅ][a-zøæåéèêë]+){1,2}$", line):
                skip = {"Norway", "Address", "City", "State", "Phone", "Mobile", "Email", "Username"}
                if line.split()[0] not in skip:
                    return line
    except Exception:
        pass

    return None


def _extract_username(page: Page) -> str | None:
    try:
        rows = page.locator("tr").all()
        for row in rows:
            text = row.inner_text()
            if "Username" in text:
                parts = text.split("Username", 1)
                if len(parts) > 1:
                    val = parts[1].strip().split("\n")[0].strip()
                    if re.match(r"^[a-zA-Z][a-zA-Z0-9._]+$", val):
                        return val
    except Exception:
        pass

    try:
        body = page.inner_text("main, body")
        match = re.search(r"Username\s*[:\s]+([a-z][a-z0-9._]+)", body, re.IGNORECASE)
        if match:
            return match.group(1)
    except Exception:
        pass

    try:
        body = page.inner_text("main, body")
        matches = re.findall(r"\b([a-zA-Z]+\.[a-zA-Z]+\d+)\b", body)
        if matches:
            return matches[0]
    except Exception:
        pass

    return None


def extract_identity(page: Page) -> Identity:
    for attempt in range(POLL_ATTEMPTS):
        if attempt > 0:
            console.print("[yellow]Reloading page...[/yellow]")
            page.reload(timeout=30000)
            _human_delay(1, 2)

        full_name = _extract_full_name(page)
        username = _extract_username(page)

        if full_name and username:
            parts = full_name.strip().split(None, 1)
            first = parts[0]
            last = parts[1] if len(parts) > 1 else ""

            return Identity(
                full_name=full_name.strip(),
                username=username.strip().lower(),
                first_name=first,
                last_name=last,
            )

        logger.warning(
            "Extraction attempt %d failed: name=%s, username=%s",
            attempt + 1, full_name, username,
        )

    raise RuntimeError("Could not extract data after multiple attempts.")


def fill_registration_form(page: Page, identity: Identity, password: str) -> None:
    _step_one_credentials(page, identity, password)
    _step_two_personal_data(page, identity, password)


def _step_one_credentials(page: Page, identity: Identity, password: str) -> None:
    console.print()
    console.print(
        Panel(
            "Step 1: Filling credentials",
            title="[bold cyan]Registration - Page 1",
            border_style="cyan",
        )
    )

    try:
        page.wait_for_selector("input, form", timeout=15000)
    except Exception:
        console.print("[yellow]Timeout waiting for form. Trying anyway...[/yellow]")

    _human_delay(1, 2)

    email_selectors = [
        "input[name='email']",
        "input[name='login']",
        "input[name='username']",
        "input[name='mail']",
        "input[placeholder*='email' i]",
        "input[placeholder*='mail' i]",
        "input[placeholder*='username' i]",
        "input[type='email']",
    ]
    for sel in email_selectors:
        try:
            el = page.locator(sel).first
            if el.count() > 0 and el.is_visible():
                el.scroll_into_view_if_needed()
                _human_delay()
                el.fill(identity.username)
                _human_delay()
                console.print(f"[dim]Username filled: {identity.username}[/dim]")
                break
        except Exception:
            continue
    else:
        console.print("[yellow]Email/username field not found. Fill it manually.[/yellow]")

    password_selectors = [
        "input[type='password']",
        "input[name='password']",
        "input[name='passwd']",
    ]
    pw_filled = False
    for sel in password_selectors:
        try:
            elements = page.locator(sel)
            count = elements.count()
            if count > 0:
                for i in range(count):
                    el = elements.nth(i)
                    if el.is_visible():
                        el.scroll_into_view_if_needed()
                        _human_delay()
                        el.fill(password)
                        _human_delay()
                console.print(f"[dim]Password filled ({count} field(s))[/dim]")
                pw_filled = True
                break
        except Exception:
            continue

    if not pw_filled:
        console.print("[yellow]Password field not found. Fill it manually.[/yellow]")

    _human_delay(1, 2)

    console.print("[dim]Clicking Continue...[/dim]")
    continue_selectors = [
        "button:has-text('Continue')",
        "button:has-text('Next')",
        "button:has-text('Weiter')",
        "button:has-text('Proceed')",
        "button[type='submit']",
        "input[type='submit']",
    ]
    clicked_continue = False
    for sel in continue_selectors:
        try:
            btn = page.locator(sel).first
            if btn.count() > 0 and btn.is_visible():
                btn.scroll_into_view_if_needed()
                _human_delay(0.3, 0.6)
                btn.click()
                console.print("[dim]Continue button clicked[/dim]")
                clicked_continue = True
                break
        except Exception:
            continue

    if not clicked_continue:
        console.print("[yellow]Continue button not found. Click it manually and press ENTER.[/yellow]")
        input()

    console.print("[dim]Waiting for next page...[/dim]")
    try:
        page.wait_for_load_state("networkidle", timeout=20000)
    except Exception:
        pass
    try:
        page.wait_for_selector(
            "input[name='first_name'], input[name='firstName'], input[name='givenName'], input[name='given_name']",
            timeout=15000,
        )
    except Exception:
        console.print("[yellow]Timeout waiting for step 2 fields. Trying anyway...[/yellow]")

    _human_delay(1, 2)


def _step_two_personal_data(page: Page, identity: Identity, password: str) -> None:
    console.print()
    console.print(
        Panel(
            "Step 2: Filling personal data",
            title="[bold cyan]Registration - Page 2",
            border_style="cyan",
        )
    )

    first_selectors = [
        "input[name='first_name']",
        "input[name='firstName']",
        "input[name='givenName']",
        "input[name='given_name']",
        "input[placeholder*='first' i]",
    ]
    _fill_first_found(page, first_selectors, identity.first_name, "First Name")

    last_selectors = [
        "input[name='last_name']",
        "input[name='lastName']",
        "input[name='familyName']",
        "input[name='family_name']",
        "input[name='surname']",
        "input[placeholder*='last' i]",
        "input[placeholder*='surname' i]",
    ]
    _fill_first_found(page, last_selectors, identity.last_name, "Last Name")

    _select_country(page)
    _check_all_boxes(page)
    _show_manual_prompt(identity, password)


def _fill_first_found(page: Page, selectors: list[str], value: str, label: str) -> None:
    for sel in selectors:
        try:
            el = page.locator(sel).first
            if el.count() > 0 and el.is_visible():
                el.scroll_into_view_if_needed()
                _human_delay()
                el.fill(value)
                _human_delay()
                console.print(f"[dim]{label}: {value}[/dim]")
                return
        except Exception:
            continue
    console.print(f"[yellow]{label} field not found automatically.[/yellow]")


def _select_country(page: Page) -> None:
    try:
        selects = page.locator("select").all()
        for s in selects:
            text = s.inner_text().lower()
            if "norway" in text or "noruega" in text or "norge" in text or "no " in text:
                options = s.locator("option").all()
                for opt in options:
                    otext = opt.inner_text().strip().lower()
                    oval = opt.get_attribute("value") or ""
                    if any(k in otext for k in ("norway", "noruega", "norge")) or oval.upper() == "NO":
                        opt_value = opt.get_attribute("value")
                        if opt_value:
                            s.select_option(value=opt_value)
                            _human_delay()
                            console.print("[dim]Country: Norway selected[/dim]")
                            return
    except Exception:
        pass

    country_input_selectors = [
        "input[name='country']",
        "input[name='location']",
        "input[name='nationality']",
        "input[placeholder*='country' i]",
        "input[placeholder*='location' i]",
    ]
    for sel in country_input_selectors:
        try:
            el = page.locator(sel).first
            if el.count() > 0 and el.is_visible():
                el.scroll_into_view_if_needed()
                _human_delay()
                el.fill("Norway")
                _human_delay()
                el.press("ArrowDown")
                _human_delay(0.2, 0.4)
                el.press("Enter")
                _human_delay()
                console.print("[dim]Country: Norway filled[/dim]")
                return
        except Exception:
            continue

    console.print("[yellow]Country field not found. Select Norway manually.[/yellow]")


def _check_all_boxes(page: Page) -> None:
    try:
        checkboxes = page.locator("input[type='checkbox']").all()
        checked_count = 0
        for cb in checkboxes:
            try:
                if not cb.is_visible():
                    continue
                is_checked = cb.evaluate("el => el.checked")
                if is_checked:
                    checked_count += 1
                    continue

                try:
                    cb.scroll_into_view_if_needed()
                    _human_delay(0.2, 0.4)
                    cb.check()
                    _human_delay()
                    is_now = cb.evaluate("el => el.checked")
                    if is_now:
                        checked_count += 1
                        continue
                except Exception:
                    pass

                cb.click(force=True)
                _human_delay()
                checked_count += 1
            except Exception:
                continue

        label_selectors = [
            "label:has-text('agree')",
            "label:has-text('Accept')",
            "label:has-text('Terms')",
            "label:has-text('Privacy')",
            "label:has-text('I have read')",
        ]
        for sel in label_selectors:
            try:
                lbl = page.locator(sel)
                count = lbl.count()
                for i in range(count):
                    el = lbl.nth(i)
                    if el.is_visible():
                        el.scroll_into_view_if_needed()
                        _human_delay(0.2, 0.4)
                        el.click()
                        _human_delay()
                        checked_count += 1
            except Exception:
                continue

        console.print(f"[dim]Checkboxes checked: {checked_count}[/dim]")
    except Exception as e:
        logger.error("Error checking boxes: %s", e)
        console.print("[yellow]Could not check checkboxes automatically.[/yellow]")


def _show_manual_prompt(identity: Identity, password: str) -> None:
    console.print()
    panel = Panel(
        Text(
            f"\n"
            f"  FILLED DATA: First Name, Last Name, Country, Checkboxes\n\n"
            f"  Click the 'Create Account' button in the browser manually.\n\n"
            f"  Generated password: {password}\n"
            f"  Full email: {identity.email}\n\n"
            f"  Press ENTER in the terminal to exit.\n",
            style="bold yellow",
        ),
        title="[i] WAITING FOR MANUAL ACTION",
        border_style="yellow",
        padding=(1, 2),
    )
    console.print(panel)


def main() -> None:
    print_warnings()

    try:
        import playwright
    except ImportError:
        console.print(
            Panel(
                Text(
                    "\nPlaywright is not installed.\n"
                    "  pip install playwright\n"
                    "  playwright install chromium\n",
                    style="bold red",
                ),
                title="[x] Error",
                border_style="red",
            )
        )
        sys.exit(1)

    password = generate_password(20)

    with sync_playwright() as pw:
        ua = (
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
        )
        browser = pw.chromium.launch(
            headless=False,
            args=["--disable-blink-features=AutomationControlled", "--no-sandbox"],
        )
        context = browser.new_context(
            user_agent=ua,
            viewport={"width": 1280, "height": 800},
            locale="en-US",
        )
        context.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined});"
        )
        page = context.new_page()

        try:
            console.print()
            console.print(
                Panel(
                    "Step 1: Generating identity (Norway, 18-24)",
                    title="[bold green]Identity Generation",
                    border_style="green",
                )
            )

            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                console=console,
            ) as progress:
                task = progress.add_task("Generating identity...", total=None)
                page.goto(IDENTITY_URL, timeout=30000)

                try:
                    page.wait_for_selector("h2, h3, table tr", timeout=20000)
                except Exception:
                    page.wait_for_load_state("networkidle", timeout=15000)

                _human_delay(1, 2)
                progress.update(task, description="Identity generated")

            identity = extract_identity(page)

            console.print()
            table = Table(
                title="[bold green]Generated Identity",
                border_style="green",
                box=box.ROUNDED,
            )
            table.add_column("Field", style="cyan")
            table.add_column("Value", style="green")
            table.add_row("Full Name", identity.full_name)
            table.add_row("First Name", identity.first_name)
            table.add_row("Last Name", identity.last_name)
            table.add_row("Username", identity.username)
            table.add_row("Generated Password", password)
            table.add_row("Email", identity.email)
            console.print(table)

            console.print()
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                console=console,
            ) as progress:
                task = progress.add_task("Navigating to registration page...", total=None)
                page.goto(REGISTER_URL, timeout=30000)
                progress.update(task, description="Page loaded")

            fill_registration_form(page, identity, password)

            console.print()
            input("\nPress ENTER after creating the account to exit...")

        except Exception as e:
            logger.exception("Fatal error")
            console.print()
            console.print(
                Panel(
                    Text(
                        f"\nFatal error: {e}\n\n"
                        f"Details: {LOG_DIR / 'error.log'}",
                        style="bold red",
                    ),
                    title="[x] Error",
                    border_style="red",
                )
            )
        finally:
            browser.close()

    console.print()
    table = Table(
        title="[bold magenta]Summary",
        border_style="magenta",
        box=box.ROUNDED,
    )
    table.add_column("Field", style="cyan")
    table.add_column("Value", style="magenta")
    try:
        table.add_row("Full Name", identity.full_name)
        table.add_row("Username", identity.username)
        table.add_row("Password", password)
        table.add_row("Email", identity.email)
    except NameError:
        table.add_row("—", "Extraction failed")
    console.print(table)


if __name__ == "__main__":
    main()
