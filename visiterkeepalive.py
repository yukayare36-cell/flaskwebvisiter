"""
Pure Python Selenium visitor.
Runs forever: visit → wait → visit → wait.
No Streamlit, no UI. Just a background worker.
"""

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
import os
import platform
import shutil
import signal

# ============ CONFIGURATION ============
TARGET_URL = "https://freecash.pythonanywhere.com"
VISIT_DURATION_MINUTES = 5
WAIT_BETWEEN_MINUTES = 10
PAGE_LOAD_TIMEOUT_SECONDS = 30
MAX_VISIT_RETRIES = 3
RETRY_DELAY_SECONDS = 20
HEADLESS_REFRESH_SECONDS = 60        # refresh page every N sec during visit
LOG_FILE = "visitor.log"             # where to write logs
# =======================================

running = True


def signal_handler(sig, frame):
    global running
    log("🛑 Shutdown signal received. Will exit after current step.")
    running = False


# Register only on main thread; safe when running as a plain script
try:
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
except (ValueError, OSError):
    pass


# ---------- Logging ----------
def log(msg):
    ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line, flush=True)
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


# ---------- Package installation ----------
def pip_install(package):
    try:
        subprocess.check_call(
            [sys.executable, '-m', 'pip', 'install', package, '--quiet']
        )
        return True
    except subprocess.CalledProcessError as e:
        log(f"⚠️ pip install {package} failed: {e}")
        return False


def ensure_python_deps():
    for pkg in ['selenium']:
        try:
            importlib.import_module(pkg)
        except ImportError:
            log(f"📦 Installing {pkg}...")
            pip_install(pkg)


ensure_python_deps()


# ---------- Chrome detection ----------
def find_chrome_binary():
    system = platform.system()
    if system == "Windows":
        candidates = [
            r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
            os.path.expanduser(
                r"~\AppData\Local\Google\Chrome\Application\chrome.exe"
            ),
        ]
    elif system == "Darwin":
        candidates = [
            "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
            "/Applications/Chromium.app/Contents/MacOS/Chromium",
        ]
    else:
        candidates = [
            "/usr/bin/chromium",
            "/usr/bin/chromium-browser",
            "/usr/bin/google-chrome",
            "/usr/bin/google-chrome-stable",
            "/snap/bin/chromium",
        ]
    for path in candidates:
        if os.path.exists(path):
            return path
    for name in ("chromium", "chromium-browser", "google-chrome",
                 "google-chrome-stable", "chrome"):
        found = shutil.which(name)
        if found:
            return found
    return None


def ensure_chrome_binary():
    path = find_chrome_binary()
    if path:
        log(f"✅ Chrome found: {path}")
        return path
    log("⚠️ Chrome not found. Install it (see notes).")
    return None


# ---------- Driver ----------
def build_chrome_options(chrome_path):
    opts = Options()
    opts.add_argument('--headless=new')
    opts.add_argument('--no-sandbox')
    opts.add_argument('--disable-dev-shm-usage')
    opts.add_argument('--disable-gpu')
    opts.add_argument('--window-size=1920,1080')
    opts.add_argument('--log-level=3')
    opts.add_argument('--disable-logging')
    opts.add_argument('--disable-background-networking')
    opts.add_argument('--disable-sync')
    opts.add_argument('--no-first-run')
    opts.add_experimental_option("excludeSwitches", ["enable-automation"])
    opts.add_experimental_option('useAutomationExtension', False)
    if chrome_path:
        opts.binary_location = chrome_path
    return opts


def create_driver(chrome_path):
    try:
        opts = build_chrome_options(chrome_path)
        driver = webdriver.Chrome(options=opts)
        driver.set_page_load_timeout(PAGE_LOAD_TIMEOUT_SECONDS)
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
        return driver
    except Exception as e:
        log(f"❌ Error initializing browser: {e}")
        return None


# ---------- One visit ----------
def _single_visit_attempt(chrome_path):
    """One attempt. Returns (success, error_message)."""
    driver = create_driver(chrome_path)
    if driver is None:
        return False, "could not create driver"

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
            f"{VISIT_DURATION_MINUTES} min "
            f"(refreshing every {HEADLESS_REFRESH_SECONDS}s)...")

        visit_start = time.time()
        end_time = visit_start + VISIT_DURATION_MINUTES * 60
        last_refresh = visit_start

        while time.time() < end_time and running:
            time.sleep(5)

            # Periodic headless page refresh
            if time.time() - last_refresh >= HEADLESS_REFRESH_SECONDS:
                try:
                    driver.refresh()
                    last_refresh = time.time()
                    log(f"🔄 Refreshed headless page (title: {driver.title})")
                except Exception as e:
                    log(f"⚠️ Refresh failed: {e}")

        return True, None

    except Exception as e:
        return False, str(e)
    finally:
        try:
            driver.quit()
        except Exception:
            pass


def visit_site(chrome_path):
    """Visit with retries. Never raises."""
    for attempt in range(1, MAX_VISIT_RETRIES + 1):
        if not running:
            log("⏹ Shutdown requested — aborting visit.")
            return False

        log(f"🔄 Attempt {attempt}/{MAX_VISIT_RETRIES}")
        ok, err = _single_visit_attempt(chrome_path)
        if ok:
            log("🔄 Closing browser...")
            return True

        log(f"❌ Error during visit: {err}")
        log("🔄 Closing browser...")

        if attempt < MAX_VISIT_RETRIES:
            log(f"⏸ Retrying in {RETRY_DELAY_SECONDS}s ...")
            for _ in range(RETRY_DELAY_SECONDS):
                if not running:
                    return False
                time.sleep(1)

    log(f"❌ All {MAX_VISIT_RETRIES} attempts failed. Will retry next cycle.")
    return False


# ---------- Main loop ----------
def main():
    log("=" * 60)
    log("🚀 Pure Python Selenium Visitor started")
    log(f"   Target URL          : {TARGET_URL}")
    log(f"   Visit duration      : {VISIT_DURATION_MINUTES} min")
    log(f"   Wait between visits : {WAIT_BETWEEN_MINUTES} min")
    log(f"   Headless refresh    : every {HEADLESS_REFRESH_SECONDS}s")
    log(f"   Log file            : {os.path.abspath(LOG_FILE)}")
    log("=" * 60)

    chrome_path = ensure_chrome_binary()

    cycle = 0
    while running:
        cycle += 1
        log(f"\n===== CYCLE #{cycle} =====")

        try:
            visit_site(chrome_path)
        except Exception as e:
            log(f"💥 Unexpected error (recovered): {e}")

        if not running:
            break

        log(f"😴 Sleeping {WAIT_BETWEEN_MINUTES} min before next visit...")
        end_wait = time.time() + WAIT_BETWEEN_MINUTES * 60
        while time.time() < end_wait and running:
            time.sleep(5)

    log("👋 Scheduler stopped.")


if __name__ == "__main__":
    main()
