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

# ============ CONFIGURATION ============
TARGET_URL = "https://userwho.loophole.site"
VISIT_DURATION_MINUTES = 5
WAIT_BETWEEN_MINUTES = 10
PAGE_LOAD_TIMEOUT_SECONDS = 30     # fail fast instead of hanging
MAX_VISIT_RETRIES = 3              # retries within one cycle before giving up
RETRY_DELAY_SECONDS = 20           # wait between retries
# =======================================

st.set_page_config(page_title="Selenium Scheduler", layout="wide")


# ---------- Logging ----------
def log(msg):
    ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line)
    if "log_lines" in st.session_state:
        st.session_state.log_lines.append(line)
        st.session_state.log_lines = st.session_state.log_lines[-300:]


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
    for pkg in ['selenium']:
        try:
            importlib.import_module(pkg)
        except ImportError:
            pip_install(pkg)
    return True


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


@st.cache_resource(show_spinner=False)
def ensure_chrome_binary():
    return find_chrome_binary()


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


# ---------- One visit (with retries) ----------
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
            f"{VISIT_DURATION_MINUTES} min...")

        end_time = time.time() + VISIT_DURATION_MINUTES * 60
        while time.time() < end_time:
            time.sleep(5)
            if not st.session_state.get("scheduler_enabled", True):
                break

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
        if not st.session_state.get("scheduler_enabled", True):
            log("⏹ Scheduler disabled mid-visit — aborting.")
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
                if not st.session_state.get("scheduler_enabled", True):
                    return False
                time.sleep(1)

    log(f"❌ All {MAX_VISIT_RETRIES} attempts failed. Will retry on next cycle.")
    return False


# ---------- Session state ----------
def init_state():
    defaults = {
        "log_lines": [],
        "scheduler_enabled": True,   # AUTO-START
        "next_run_at": 0.0,
        "cycle_count": 0,
        "last_state_load": time.time(),
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v


init_state()


# ---------- Sidebar ----------
with st.sidebar:
    st.header("⚙️ Scheduler (auto-run)")

    st.write(f"**Target URL:** `{TARGET_URL}`")
    st.write(f"**Visit duration:** {VISIT_DURATION_MINUTES} min")
    st.write(f"**Wait between:** {WAIT_BETWEEN_MINUTES} min")
    st.write(f"**Max retries / cycle:** {MAX_VISIT_RETRIES}")

    if st.button("⏹ Stop scheduler"):
        st.session_state.scheduler_enabled = False
        log("⏹ Scheduler disabled")

    if st.button("▶️ Resume scheduler"):
        st.session_state.scheduler_enabled = True
        if st.session_state.next_run_at == 0.0:
            st.session_state.next_run_at = time.time()
        log("▶️ Scheduler enabled")

    if st.button("🧹 Clear logs"):
        st.session_state.log_lines = []

    if st.button("🔄 Force visit now"):
        st.session_state.next_run_at = 0.0
        log("🔄 Forcing next cycle now")
        st.rerun()

    st.divider()
    st.caption(
        "Runs automatically. Reloading the page does NOT stop the "
        "schedule — state is kept in the session. Errors are logged "
        "and retried automatically."
    )


# ---------- Main UI ----------
st.title("🌐 Selenium Visit Scheduler")

chrome_path = ensure_chrome_binary()
if chrome_path:
    st.success(f"✅ Chrome found: `{chrome_path}`")
else:
    st.error(
        "❌ Chrome/Chromium not found. Add a `packages.txt` with:\n"
        "```\nchromium\nchromium-driver\n```"
    )

status_col, cycle_col, next_col = st.columns(3)
status_col.metric(
    "Status",
    "🟢 Running" if st.session_state.scheduler_enabled else "🔴 Stopped"
)
cycle_col.metric("Cycles completed", st.session_state.cycle_count)

if st.session_state.scheduler_enabled and st.session_state.next_run_at:
    remaining = max(0, int(st.session_state.next_run_at - time.time()))
    next_col.metric("Next run in", f"{remaining} s")
else:
    next_col.metric("Next run in", "—")

st.subheader("📜 Logs")
log_box = st.empty()
log_box.code(
    "\n".join(st.session_state.log_lines[-150:]) or "(no logs yet)",
    language="log"
)


# ---------- Scheduler tick (auto-run, self-healing) ----------
if st.session_state.scheduler_enabled:
    now = time.time()

    if now >= st.session_state.next_run_at:
        st.session_state.cycle_count += 1
        log(f"\n===== CYCLE #{st.session_state.cycle_count} =====")

        with st.spinner("Visiting site..."):
            try:
                visit_site(chrome_path)
            except Exception as e:
                # Belt-and-braces: should never happen because visit_site
                # catches everything, but if it does, keep the loop alive.
                log(f"💥 Unexpected scheduler error (recovered): {e}")

        # Schedule next run no matter what happened
        st.session_state.next_run_at = time.time() + WAIT_BETWEEN_MINUTES * 60
        log(f"😴 Next visit scheduled in {WAIT_BETWEEN_MINUTES} min")

        st.rerun()
    else:
        time.sleep(5)
        st.rerun()


# ---------- Notes ----------
with st.expander("ℹ️ How this works"):
    st.markdown("**Behavior**")
    st.markdown(
        "- **Auto-start** — no button needed; the loop begins on load.\n"
        "- **Reload-safe** — refreshing the page does not stop or reset "
        "the schedule (state lives in the Streamlit session).\n"
        "- **Auto-retry** — a failed visit is retried up to "
        f"`{MAX_VISIT_RETRIES}` times with a `{RETRY_DELAY_SECONDS}s` "
        "delay, then the loop moves on to the next cycle.\n"
        "- **Fast-fail** — page load has a "
        f"`{PAGE_LOAD_TIMEOUT_SECONDS}s` timeout so a dead host "
        "(like the `ERR_CONNECTION_CLOSED` you saw) won't hang the app."
    )
    st.markdown("**Required files**")
    st.code(
        "packages.txt:\nchromium\nchromium-driver\n\n"
        "requirements.txt:\nstreamlit\nselenium",
        language="text",
    )
    st.markdown("**Limitations on Streamlit Cloud**")
    st.markdown(
        "- Tab must stay open — the app hibernates after ~15 min idle.\n"
        "- Reload ≠ session reset *only if* the app hasn't hibernated. "
        "If it hibernates, `session_state` resets and the cycle counter "
        "starts over.\n"
        "- For true 24/7 no-tab running, use GitHub Actions / a worker."
    )
