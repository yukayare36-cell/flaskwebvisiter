import streamlit as st
import subprocess
import sys
import os
import time
import datetime

# ============ CONFIGURATION ============
WORKER_SCRIPT = "visitor_worker.py"
LOG_FILE = "visitor.log"
PID_FILE = "visitor.pid"
# =======================================

st.set_page_config(page_title="Visitor Scheduler", layout="wide")


# ---------- Worker management ----------
def is_worker_running():
    """Check if the background worker process is alive."""
    if not os.path.exists(PID_FILE):
        return False
    try:
        with open(PID_FILE) as f:
            pid = int(f.read().strip())
        # Check if process exists (Linux/macOS/Windows)
        if os.name == "nt":
            out = subprocess.run(
                ["tasklist", "/FI", f"PID eq {pid}"],
                capture_output=True, text=True
            )
            return str(pid) in out.stdout
        else:
            os.kill(pid, 0)
            return True
    except (ValueError, ProcessLookupError, PermissionError):
        return False


def start_worker():
    """Spawn the worker as a detached background process."""
    if is_worker_running():
        return False, "Worker already running"

    # Use the same Python interpreter running Streamlit
    kwargs = {}
    if os.name == "nt":
        # DETACHED_PROCESS on Windows
        kwargs["creationflags"] = 0x00000008 | 0x00000200
    else:
        kwargs["start_new_session"] = True

    # Redirect worker output to the log file
    log_fh = open(LOG_FILE, "a", encoding="utf-8")

    proc = subprocess.Popen(
        [sys.executable, WORKER_SCRIPT],
        stdout=log_fh,
        stderr=log_fh,
        stdin=subprocess.DEVNULL,
        cwd=os.path.dirname(os.path.abspath(__file__)),
        **kwargs,
    )

    with open(PID_FILE, "w") as f:
        f.write(str(proc.pid))

    return True, f"Worker started (PID {proc.pid})"


def stop_worker():
    """Kill the worker if it's running."""
    if not os.path.exists(PID_FILE):
        return False, "No worker to stop"
    try:
        with open(PID_FILE) as f:
            pid = int(f.read().strip())

        if os.name == "nt":
            subprocess.run(["taskkill", "/PID", str(pid), "/F"],
                           capture_output=True)
        else:
            os.kill(pid, 15)  # SIGTERM

        try:
            os.remove(PID_FILE)
        except OSError:
            pass
        return True, f"Stopped worker (PID {pid})"
    except (ValueError, ProcessLookupError) as e:
        try:
            os.remove(PID_FILE)
        except OSError:
            pass
        return False, f"Could not stop worker: {e}"


def read_log_tail(n=200):
    """Read the last N lines of the log file."""
    if not os.path.exists(LOG_FILE):
        return "(no logs yet)"
    try:
        with open(LOG_FILE, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
        return "".join(lines[-n:]) or "(log is empty)"
    except Exception as e:
        return f"(could not read log: {e})"


# ---------- Auto-start on first page load ----------
if "auto_started" not in st.session_state:
    st.session_state.auto_started = True
    if not is_worker_running():
        ok, msg = start_worker()
        print(f"[auto-start] {ok} - {msg}")


# ---------- UI ----------
st.title("🌐 Selenium Visitor Scheduler")

st.caption(
    "The actual work runs in a background process — closing this tab "
    "does **not** stop it. Streamlit's healthcheck is satisfied by "
    "this page, so the container stays alive."
)

running = is_worker_running()

col1, col2, col3 = st.columns(3)
col1.metric("Worker", "🟢 Running" if running else "🔴 Stopped")
col2.metric("Healthcheck", "✅ OK")
col3.metric("Server time", datetime.datetime.now().strftime("%H:%M:%S"))

# Buttons
b1, b2, b3 = st.columns(3)
with b1:
    if st.button("▶️ Start worker"):
        ok, msg = start_worker()
        st.success(msg) if ok else st.warning(msg)
        st.rerun()
with b2:
    if st.button("⏹ Stop worker"):
        ok, msg = stop_worker()
        st.success(msg) if ok else st.warning(msg)
        st.rerun()
with b3:
    if st.button("🧹 Clear log"):
        try:
            open(LOG_FILE, "w").close()
        except Exception:
            pass
        st.rerun()

# ---- Log display ----
st.subheader("📜 Live log (`visitor.log`)")
log_text = read_log_tail(200)
st.code(log_text, language="log")

# ---- Manual auto-refresh via JS (works without extra package) ----
# Rerun the page every 5 seconds so the log updates live
st.markdown(
    """
    <script>
        setTimeout(function() {
            window.parent.location.reload();
        }, 5000);
    </script>
    """,
    unsafe_allow_html=True,
)

st.caption(
    "Page auto-reloads every 5s. Reloading or closing the tab does not "
    "affect the background worker."
)
