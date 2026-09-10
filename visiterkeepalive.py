import streamlit as st
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
import threading

# ============ CONFIGURATION ============
TARGET_URL = "https://userwho.loophole.site"
VISIT_DURATION_MINUTES = 5
WAIT_BETWEEN_MINUTES = 10
# =======================================

st.set_page_config(page_title="Selenium Scheduler", layout="wide")


# ---------- Logging ----------
def log(msg):
    ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line)
    if "log_lines" in st.session_state:
        st.session_state.log_lines.append(line)
        # Keep only last 200 lines
        st.session_state.log_lines = st.session_state.log_lines[-200:]


# ---------- Package installation ----------
def pip_install(package, quiet=True):
    cmd = [sys.executable, '-m', 'pip', 'install', package]
    if quiet:
        cmd.append('--quiet')
    try:
        subprocess.check_call(cmd)
        return True
    except subprocess.CalledProcessError as e:
        print(f"⚠️ pip install {package} failed: {e}")
        return False


@st.cache_resource(show_spinner=False)
def ensure_python_deps():
    required = ['selenium']
    for pkg in required:
        try:
            importlib.import_module(pkg)
        except ImportError:
            pip_install(pkg)
    return True


# ---------- Chrome detection ----------
def find_chrome_binary():
    system = platform.system()
    candidates = []

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


def try_install_chromium_linux():
    """On Streamlit Cloud (Debian), try apt-get — needs sudo, often fails."""
    if platform.system() != "Linux":
        return False
    if not shutil.which("apt-get"):
        return False
    try:
        subprocess.check_call([
            "sudo", "apt-get", "update", "-y"
        ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        subprocess.check_call([
            "sudo", "apt-get", "install", "-y",
            "chromium", "chromium-driver"
        ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True
    except Exception:
        try:
            subprocess.check_call([
                "sudo", "apt-get", "install", "-y",
                "chromium-browser", "chromium-chromedriver"
            ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return True
        except Exception:
            return False


@st.cache_resource(show_spinner=False)
def ensure_chrome_binary():
    path = find_chrome_binary()
    if path:
        return path
    if try_install_chromium_linux():
        return find_chrome_binary()
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

        # Short sleep so we don't freeze Streamlit too badly
        end_time = time.time() + VISIT_DURATION_MINUTES * 60
        while time.time() < end_time:
            time.sleep(5)
            # Let Streamlit know we're still alive (no rerun, just yield)
            if not st.session_state.get("scheduler_enabled", True):
                break

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


# ---------- Session state init ----------
def init_state():
    defaults = {
        "log_lines": [],
        "scheduler_enabled": False,
        "next_run_at": 0.0,
        "cycle_count": 0,
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v


init_state()


# ---------- Sidebar ----------
with st.sidebar:
    st.header("⚙️ Scheduler")

    st.write(f"**Target URL:** `{TARGET_URL}`")
    st.write(f"**Visit duration:** {VISIT_DURATION_MINUTES} min")
    st.write(f"**Wait between:** {WAIT_BETWEEN_MINUTES} min")

    if st.button("▶️ Start scheduler"):
        st.session_state.scheduler_enabled = True
        st.session_state.next_run_at = 0.0
        log("▶️ Scheduler enabled")

    if st.button("⏹ Stop scheduler"):
        st.session_state.scheduler_enabled = False
        log("⏹ Scheduler disabled")

    if st.button("🧹 Clear logs"):
        st.session_state.log_lines = []

    st.divider()
    st.caption(
        "⚠️ On Streamlit Community Cloud the app sleeps when the tab "
        "is closed. Keep this page open for the scheduler to keep running."
    )


# ---------- Main UI ----------
st.title("🌐 Selenium Visit Scheduler")

chrome_path = ensure_chrome_binary()
if chrome_path:
    st.success(f"✅ Chrome found: `{chrome_path}`")
else:
    st.warning(
        "⚠️ Chrome/Chromium not found. On Streamlit Cloud, add a "
        "`packages.txt` file with:\n\n```\nchromium\nchromium-driver\n```\n\n"
        "and a `requirements.txt` with `selenium`."
    )

status_col, cycle_col, next_col = st.columns(3)
status_col.metric("Status",
                  "🟢 Running" if st.session_state.scheduler_enabled else "🔴 Stopped")
cycle_col.metric("Cycles completed", st.session_state.cycle_count)
if st.session_state.scheduler_enabled and st.session_state.next_run_at:
    remaining = max(0, int(st.session_state.next_run_at - time.time()))
    next_col.metric("Next run in", f"{remaining} s")
else:
    next_col.metric("Next run in", "—")

st.subheader("📜 Logs")
log_box = st.empty()
log_box.code("\n".join(st.session_state.log_lines[-100:]) or "(no logs yet)",
             language="log")


# ---------- Scheduler tick ----------
# Runs on every rerun. If the timer has elapsed, does one visit and
# schedules the next. Uses st.rerun() with a short sleep to keep UI alive.

if st.session_state.scheduler_enabled:
    now = time.time()

    if now >= st.session_state.next_run_at:
        # Time to visit
        st.session_state.cycle_count += 1
        log(f"\n===== CYCLE #{st.session_state.cycle_count} =====")

        with st.spinner("Visiting site (this can take up to "
                        f"{VISIT_DURATION_MINUTES} min)..."):
            visit_site(chrome_path)

        # Schedule next run
        st.session_state.next_run_at = time.time() + WAIT_BETWEEN_MINUTES * 60
        log(f"😴 Next visit scheduled in {WAIT_BETWEEN_MINUTES} min")

        # Refresh UI so the browser stays responsive
        st.rerun()
    else:
        # Not time yet — sleep briefly then rerun
        time.sleep(5)
        st.rerun()


# ---------- Notes ----------
with st.expander("ℹ️ How to make this work on Streamlit Cloud"):
    st.markdown("**Required files in your repo:**")
    st.code(
        "packages.txt:\nchromium\nchromium-driver\n\n"
        "requirements.txt:\nstreamlit\nselenium",
        language="text",
    )
    st.markdown("**Important limitations:**")
    st.markdown(
        "- The browser tab must stay open. Streamlit Community Cloud "
        "sleeps after ~15 min of no activity.\n"
        "- Each `st.rerun()` restarts the script from the top. State "
        "lives only in `st.session_state`.\n"
        "- `time.sleep(5)` blocks the UI during visits."
    )
    st.markdown("**Need 24/7 without an open tab?** Use GitHub Actions, "
                "Render worker, Railway worker, or a VPS instead.")
