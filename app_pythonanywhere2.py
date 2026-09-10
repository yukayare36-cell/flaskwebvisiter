from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import time
import subprocess
import sys
import importlib
import datetime
import signal
import os
import platform
import shutil

# ============ CONFIGURATION ============
TARGET_URL = "https://example.com"
VISIT_DURATION_MINUTES = 5
WAIT_BETWEEN_MINUTES = 10
# =======================================

running = True

def signal_handler(sig, frame):
    global running
    print("\n🛑 Shutdown signal received. Exiting after current cycle...")
    running = False

signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)


def log(msg):
    ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{ts}] {msg}")


# ============================================================
#  Package installation
# ============================================================
def pip_install(package, quiet=True):
    cmd = [sys.executable, '-m', 'pip', 'install', package]
    if quiet:
        cmd.append('--quiet')
    try:
        subprocess.check_call(cmd)
        return True
    except subprocess.CalledProcessError as e:
        log(f"⚠️ pip install {package} failed: {e}")
        return False


def ensure_python_deps():
    log("🔍 Checking required Python packages...")
    required = {
        'selenium': 'selenium',
        'webdriver_manager': 'webdriver-manager',  # optional fallback
    }
    for module, pkg in required.items():
        try:
            importlib.import_module(module)
            log(f"✅ {pkg} is already installed")
        except ImportError:
            log(f"📦 Installing {pkg}...")
            if pip_install(pkg):
                log(f"✅ Installed {pkg}")
            else:
                log(f"⚠️ Could not install {pkg} — continuing anyway")


ensure_python_deps()


# ============================================================
#  Chrome / Chromium detection & installation
# ============================================================
def find_chrome_binary():
    """Return path to Chrome/Chromium binary if it exists, else None."""
    system = platform.system()
    candidates = []

    if system == "Windows":
        candidates = [
            r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
            os.path.expanduser(
                r"~\AppData\Local\Google\Chrome\Application\chrome.exe"
            ),
            r"C:\Program Files\Chromium\Application\chrome.exe",
            r"C:\Program Files (x86)\Chromium\Application\chrome.exe",
            os.path.expanduser(
                r"~\AppData\Local\Chromium\Application\chrome.exe"
            ),
        ]
    elif system == "Darwin":
        candidates = [
            "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
            "/Applications/Chromium.app/Contents/MacOS/Chromium",
            "/Applications/Google Chrome Canary.app/Contents/MacOS/"
            "Google Chrome Canary",
        ]
    else:  # Linux
        candidates = [
            "/usr/bin/chromium",
            "/usr/bin/chromium-browser",
            "/usr/bin/google-chrome",
            "/usr/bin/google-chrome-stable",
            "/snap/bin/chromium",
        ]

    # First, check the common paths
    for path in candidates:
        if os.path.exists(path):
            return path

    # Then, try PATH lookup
    for name in ("chromium", "chromium-browser", "google-chrome",
                 "google-chrome-stable", "chrome"):
        found = shutil.which(name)
        if found:
            return found

    return None


def try_install_chromium():
    """Attempt to install Chromium via the OS package manager."""
    system = platform.system()
    log("📦 Chrome/Chromium not found — attempting installation...")

    try:
        if system == "Windows":
            # Try winget first, then choco
            if shutil.which("winget"):
                log("   ↳ Trying winget install Google.Chrome ...")
                subprocess.check_call([
                    "winget", "install", "--id", "Google.Chrome",
                    "-e", "--silent",
                    "--accept-package-agreements",
                    "--accept-source-agreements",
                ])
                return True
            if shutil.which("choco"):
                log("   ↳ Trying choco install googlechrome ...")
                subprocess.check_call([
                    "choco", "install", "googlechrome", "-y"
                ])
                return True
            log("   ⚠️ Neither winget nor choco available on this Windows box.")
            log("   👉 Please install Chrome manually: "
                "https://www.google.com/chrome/")
            return False

        elif system == "Darwin":
            if shutil.which("brew"):
                log("   ↳ Trying brew install --cask chromium ...")
                subprocess.check_call([
                    "brew", "install", "--cask", "chromium"
                ])
                return True
            log("   ⚠️ Homebrew not found. "
                "Install Chrome manually: https://www.google.com/chrome/")
            return False

        else:  # Linux
            if os.geteuid() != 0:
                log("   ⚠️ Not running as root — Linux package install "
                    "may fail. Trying sudo-less methods first...")

            # Debian / Ubuntu
            if shutil.which("apt-get"):
                log("   ↳ Trying apt-get install chromium ...")
                try:
                    subprocess.check_call([
                        "sudo", "apt-get", "update", "-y"
                    ])
                    subprocess.check_call([
                        "sudo", "apt-get", "install", "-y", "chromium"
                    ])
                    return True
                except subprocess.CalledProcessError:
                    log("   ↳ apt chromium failed, trying chromium-browser...")
                    try:
                        subprocess.check_call([
                            "sudo", "apt-get", "install", "-y",
                            "chromium-browser"
                        ])
                        return True
                    except subprocess.CalledProcessError:
                        pass

            # Fedora / RHEL
            if shutil.which("dnf"):
                log("   ↳ Trying dnf install chromium ...")
                try:
                    subprocess.check_call([
                        "sudo", "dnf", "install", "-y", "chromium"
                    ])
                    return True
                except subprocess.CalledProcessError:
                    pass

            # Arch
            if shutil.which("pacman"):
                log("   ↳ Trying pacman -S chromium ...")
                try:
                    subprocess.check_call([
                        "sudo", "pacman", "-S", "--noconfirm", "chromium"
                    ])
                    return True
                except subprocess.CalledProcessError:
                    pass

            log("   ⚠️ Could not auto-install Chromium on this Linux distro.")
            return False

    except Exception as e:
        log(f"   ⚠️ Installation attempt failed: {e}")
        return False


def ensure_chrome_binary():
    """Return path to a working Chrome/Chromium binary, installing if needed."""
    path = find_chrome_binary()
    if path:
        log(f"✅ Found Chrome/Chromium at: {path}")
        return path

    # Try to install it
    if try_install_chromium():
        path = find_chrome_binary()
        if path:
            log(f"✅ Installed Chrome/Chromium at: {path}")
            return path

    log("⚠️ Could not locate or install Chrome/Chromium.")
    log("   Selenium Manager will try to fetch one automatically.")
    return None


# ============================================================
#  Driver creation
# ============================================================
def build_chrome_options(chrome_path):
    opts = Options()
    opts.add_argument('--headless=new')   # modern headless mode
    opts.add_argument('--no-sandbox')
    opts.add_argument('--disable-dev-shm-usage')
    opts.add_argument('--disable-gpu')
    opts.add_argument('--window-size=1920,1080')
    opts.add_experimental_option("excludeSwitches", ["enable-automation"])
    opts.add_experimental_option('useAutomationExtension', False)

    # Only set binary_location if we actually found one.
    # Otherwise Selenium Manager will handle it.
    if chrome_path:
        opts.binary_location = chrome_path

    return opts


def create_driver(chrome_path):
    """Create a Chrome driver with ngrok-skip headers injected."""
    try:
        opts = build_chrome_options(chrome_path)
        driver = webdriver.Chrome(options=opts)

        driver.execute_cdp_cmd('Network.enable', {})
        driver.execute_cdp_cmd('Network.setExtraHTTPHeaders', {
            'headers': {
                'ngrok-skip-browser-warning': '1',
                'User-Agent': (
                    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                    'AppleWebKit/537.36 (KHTML, like Gecko) '
                    'Chrome/120.0.0.0 Safari/537.36 MyApp/1.0'
                )
            }
        })
        log("✅ Browser initialized with skip headers")
        return driver
    except Exception as e:
        log(f"❌ Error initializing browser: {e}")
        return None


# ============================================================
#  Visit cycle
# ============================================================
def visit_site(chrome_path):
    driver = create_driver(chrome_path)
    if driver is None:
        return False

    try:
        log(f"🌐 Navigating to {TARGET_URL} ...")
        driver.get(TARGET_URL)
        time.sleep(2)

        log("=" * 60)
        log(f"📄 URL       : {driver.current_url}")
        log(f"🏷️  Title     : {driver.title}")
        page_source = driver.page_source
        log(f"📏 Page size : {len(page_source)} bytes")

        try:
            body_text = driver.find_element(By.TAG_NAME, "body").text
            preview = body_text.strip().replace("\n", " ")[:300]
            log(f"👀 Preview   : {preview}")
        except Exception as e:
            log(f"⚠️ Could not read body text: {e}")

        if 'ERR_NGROK' in page_source:
            log("⚠️ Ngrok interstitial detected, trying to bypass...")
            try:
                btn = WebDriverWait(driver, 5).until(
                    EC.element_to_be_clickable(
                        (By.XPATH, "//button[contains(text(), 'Visit')]")
                    )
                )
                btn.click()
                time.sleep(2)
                log(f"✅ Bypassed! New title: {driver.title}")
            except Exception as e:
                log(f"⚠️ Bypass failed: {e}")

        log(f"✅ Visit successful. Keeping browser open for "
            f"{VISIT_DURATION_MINUTES} min...")
        log("=" * 60)

        end_time = time.time() + VISIT_DURATION_MINUTES * 60
        while time.time() < end_time and running:
            time.sleep(5)

        return True

    except Exception as e:
        log(f"❌ Error during visit: {e}")
        return False
    finally:
        log("🔄 Closing browser...")
        try:
            driver.quit()
        except Exception:
            pass


# ============================================================
#  Main
# ============================================================
def main():
    log("=" * 60)
    log("🚀 Selenium Scheduler Started")
    log(f"   Platform            : {platform.system()} {platform.release()}")
    log(f"   Target URL          : {TARGET_URL}")
    log(f"   Visit duration      : {VISIT_DURATION_MINUTES} minutes")
    log(f"   Wait between visits : {WAIT_BETWEEN_MINUTES} minutes")
    log("=" * 60)

    # Resolve / install Chrome once at startup
    chrome_path = ensure_chrome_binary()

    cycle = 0
    while running:
        cycle += 1
        log(f"\n===== CYCLE #{cycle} =====")
        visit_site(chrome_path)

        if not running:
            break

        log(f"😴 Sleeping for {WAIT_BETWEEN_MINUTES} minutes before next visit...")
        end_wait = time.time() + WAIT_BETWEEN_MINUTES * 60
        while time.time() < end_wait and running:
            time.sleep(5)

    log("👋 Scheduler stopped.")


if __name__ == '__main__':
    main()
