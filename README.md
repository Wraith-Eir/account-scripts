# Auto-Registration Tools

A collection of Python scripts for automated browser registration flows using Playwright and Rich. These tools assist in creating accounts on supported platforms by automating form filling, handling identity generation, and managing manual verification steps.

## Features

- **Automated Form Filling**: Fills registration forms with human-like typing delays to avoid bot detection.
- **CAPTCHA Detection**: Identifies common CAPTCHA/Cloudflare challenges and pauses for manual resolution.
- **Arch Linux Support**: Automatically checks for missing system dependencies on Arch Linux.
- **Interactive CLI**: Rich-formatted terminal output with progress indicators, tables, and panels.
- **Session Saving**: Exports browser cookies and storage state for future use.
- **Anti-Fingerprinting**: Masks automation indicators (e.g., `navigator.webdriver`) for better compatibility.

## Prerequisites

- **Python 3.10+**
- **Chromium browser** (installed via Playwright or system package manager)
- A compatible Linux environment (Arch Linux recommended, though other distros/OSes may work)

## Installation

1. **Clone the repository:**
   ```bash
   git clone https://github.com/Wraith-Eir/account-scripts.git
   cd account-scripts
   ```

2. **Install Python dependencies:**
   ```bash
   pip install playwright rich
   ```

3. **Install Playwright Chromium and system dependencies:**
   ```bash
   playwright install chromium
   playwright install-deps chromium
   ```

   > **Note for Arch Linux users:** The scripts will automatically check for `chromium`, `nss`, and `harfbuzz-icu` and warn you if they are missing. You can install them manually via:
   > ```bash
   > sudo pacman -S chromium nss harfbuzz-icu
   > ```

## Usage

### 1. Mailbox.org Auto-Registration

Generates a fake identity (Norway, ages 18-24) using FakeNameGenerator, pre-fills the Mailbox.org registration form, and pauses for you to manually submit the final step.

```bash
python email_register.py
```

**What it does:**
1. Navigates to FakeNameGenerator and extracts a random name and username.
2. Generates a strong random password.
3. Navigates to the Mailbox.org registration page.
4. Fills in the username, password, first name, last name, country (Norway), and checks required boxes.
5. Pauses and prompts you to click "Create Account" manually.

---

### 2. Qwen AI Auto-Registration

Automates the Qwen AI account creation process. It fills out the registration form and opens a second tab to Mailbox.org so you can manually verify the confirmation email.

```bash
python ai_register.py
```

**Command-line options:**
| Flag | Description |
|---|---|
| `--headless` | Runs the browser in headless mode (no GUI). |
| `--email` | Provides the mailbox.org email upfront (skips interactive prompt). |
| `--name` | Provides the full name upfront (skips interactive prompt). |

**What it does:**
1. Prompts you for your full name, a mailbox.org email, a password for Qwen, and your mailbox.org password.
2. Navigates to the Qwen registration page and fills the form.
3. Checks the "Terms of Service" checkbox.
4. Detects and pauses for CAPTCHAs if present.
5. Submits the registration form.
6. Opens a new browser tab, logs into mailbox.org, and prompts you to click the verification link.

## Logging & Sessions

- **Logs:** Error logs and debug information are saved locally:
  - `~/.local/share/auto-register/error.log`
- **Sessions:** Qwen login sessions (cookies and storage state) are saved to:
  - `~/.config/auto-register/session_<email>.json`

## Disclaimer

These tools are intended for educational purposes and legitimate automation testing only. Ensure your usage complies with the Terms of Service of the respective websites. The authors assume no responsibility for misuse.
