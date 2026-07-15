"""Playit.gg tunnel — Windows implementation.

On Windows, playit.gg is typically installed via its own installer
(C:\\Program Files\\playit_gg\\bin\\playit.exe) and runs as either:
  - A system tray app (playitd-tray.exe) — auto-starts on boot
  - A Windows service managed via `playit start / stop / status`

The webconsole detects whichever is running and reports status
accordingly.  It does NOT try to compete with the tray app —
if the tray app is active, the webconsole reads the shared
daemon log for tunnel info.

Tunnel addresses are configured through the playit.gg web dashboard
at https://playit.gg/account — the CLI no longer outputs them.
"""

import os
import re
import shutil
import subprocess
import sys
import threading
import time
from collections import deque
from pathlib import Path


_APP_DIR = None
if getattr(sys, "frozen", False):
    _APP_DIR = Path(sys.executable).resolve().parent
else:
    _APP_DIR = Path.cwd()


_PLAYIT = None          # Path to playit.exe (CLI)
_PLAYIT_TOML = None     # Path to playit.toml config
_PLAYIT_LOG = None      # Path to playitd.log

# In-memory log buffer (captures CLI output not yet in log file)
_daemon_logs = deque(maxlen=500)
_lock = threading.Lock()


# ═══════════════════════════════════════════════════════════════════════
#  Initialization
# ═══════════════════════════════════════════════════════════════════════

def _find_playit():
    """Locate playit.exe in PATH or common install locations."""
    p = shutil.which("playit") or shutil.which("playit.exe")
    if p:
        return str(Path(p).resolve())
    for name in ["playit.exe", "playit"]:
        p = _APP_DIR / name
        if p.exists():
            return str(p.resolve())
    for base in ["C:/Program Files", "C:/Program Files (x86)"]:
        p = Path(base) / "playit_gg" / "bin" / "playit.exe"
        if p.exists():
            return str(p.resolve())
    return ""


def _find_toml():
    """Locate playit.toml config file."""
    candidates = [
        Path(os.environ.get("PROGRAMDATA", "")) / "playit_gg" / "playit.toml",
        Path(os.environ.get("LOCALAPPDATA", "")) / "playit_gg" / "playit.toml",
        Path(os.environ.get("APPDATA", "")) / "playit_gg" / "playit.toml",
        Path.home() / ".config" / "playit_gg" / "playit.toml",
        Path.home() / ".playit" / "playit.toml",
    ]
    for p in candidates:
        if p.exists():
            return str(p.resolve())
    return ""


def _find_log():
    """Determine daemon log file path."""
    prog_data = os.environ.get("PROGRAMDATA", "")
    if prog_data:
        return str(Path(prog_data) / "playit_gg" / "logs" / "playitd.log")
    return str(Path.home() / ".playit" / "playitd.log")


def _init():
    global _PLAYIT, _PLAYIT_TOML, _PLAYIT_LOG
    _PLAYIT = _find_playit()
    _PLAYIT_TOML = _find_toml()
    _PLAYIT_LOG = _find_log()


_init()


# ═══════════════════════════════════════════════════════════════════════
#  Helpers
# ═══════════════════════════════════════════════════════════════════════

def _call_playit(args, timeout=30):
    """Run a playit CLI command. Returns (ok, stdout_lines, stderr_lines)."""
    if not _PLAYIT:
        return False, [], ["playit.exe not found"]
    try:
        r = subprocess.run(
            [_PLAYIT] + args,
            capture_output=True, text=True, timeout=timeout,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        out_lines = [l for l in r.stdout.split("\n") if l.strip()] if r.stdout.strip() else []
        err_lines = [l for l in r.stderr.split("\n") if l.strip()] if r.stderr.strip() else []
        ok = r.returncode == 0
        if out_lines:
            _append_logs(out_lines)
        return ok, out_lines, err_lines
    except subprocess.TimeoutExpired:
        return False, [], ["Command timed out"]
    except Exception as e:
        return False, [], [str(e)]


def _append_logs(lines):
    with _lock:
        for line in lines:
            _daemon_logs.append(line)


def _read_log_file(n=100):
    """Read last N lines from the playitd log file."""
    if not _PLAYIT_LOG:
        return []
    try:
        p = Path(_PLAYIT_LOG)
        if not p.exists():
            return []
        content = p.read_text(encoding="utf-8", errors="replace")
        lines = [l for l in content.split("\n") if l.strip()]
        return lines[-n:]
    except Exception:
        return []


def _kill_tray():
    """Kill playitd-tray.exe if running (returns True if killed).

    NOTE: Only call this when the user explicitly asks to stop the
    daemon.  NEVER kill the tray app automatically — it might be
    the user's main way of running playit.gg and killing it mid-claim
    disconnects the agent from the website.
    """
    try:
        r = subprocess.run(
            ["taskkill", "-f", "-im", "playitd-tray.exe"],
            capture_output=True, text=True, timeout=10,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        return r.returncode == 0
    except Exception:
        return False


def _is_tray_running():
    """Check if playitd-tray.exe is running."""
    try:
        r = subprocess.run(
            ["tasklist", "/fi", "imagename eq playitd-tray.exe"],
            capture_output=True, text=True, timeout=10,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        return "playitd-tray.exe" in r.stdout
    except Exception:
        return False


def _tunnel_count_from_logs(lines):
    """Parse tunnel_count from daemon log lines."""
    for line in lines:
        m = re.search(r'tunnel_count=(\d+)', line)
        if m:
            return int(m.group(1))
    return 0


# ═══════════════════════════════════════════════════════════════════════
#  Public API  —  Installation / Status
# ═══════════════════════════════════════════════════════════════════════

def is_installed():
    """Check if playit.exe is available on the system."""
    return bool(_PLAYIT)


def install_commands():
    """Windows: no package-manager install.

    User downloads from https://playit.gg/download/windows.
    """
    return []


def is_claimed():
    """Check if the playit agent has a secret key on disk."""
    if not _PLAYIT_TOML:
        return False
    try:
        content = Path(_PLAYIT_TOML).read_text(encoding="utf-8", errors="replace")
        return "secret_key" in content
    except Exception:
        return False


# ═══════════════════════════════════════════════════════════════════════
#  Public API  —  Daemon Detection / Management
# ═══════════════════════════════════════════════════════════════════════

def _is_service_running():
    """Check if playit Windows service is running via 'playit status'."""
    if not _PLAYIT:
        return False
    ok, out, _ = _call_playit(["status"])
    if not ok and not out:
        return False
    # Look for PID — if present, the service is alive
    for line in out:
        if line.strip().startswith("PID:"):
            return True
    # Phase also indicates it's running
    for line in out:
        if "Phase:" in line and "stopped" not in line.lower():
            return True
    return False


def _is_daemon_running():
    """Check if ANY playit daemon process is active (service or tray)."""
    return _is_service_running() or _is_tray_running()


def start_daemon():
    """Start the playit daemon.

    Kills the tray app first if running, then starts the service
    via 'playit start'.
    """
    if not _PLAYIT:
        return False, "playit.exe not found"

    # If the service is already running, we're good
    if _is_service_running():
        return True, "Service already running"

    # If the tray is running, we can piggyback on it
    if _is_tray_running():
        return True, "Tray app already running"

    # Start the service
    ok, out, err = _call_playit(["start"], timeout=45)
    if ok:
        time.sleep(3)
        if _is_service_running():
            return True, "Service started"
        return True, "Service start initiated (check status in a moment)"
    msg = "; ".join(err[-3:]) if err else "; ".join(out[-3:]) if out else "Failed to start"
    return False, msg


def stop_daemon():
    """Stop the playit daemon.

    Try 'playit stop' for the service, then kill the tray app if still running.
    """
    # Try stopping the service first
    ok, out, err = _call_playit(["stop"], timeout=30)
    if not ok:
        for line in out + err:
            if "not running" in line.lower() or "stopped" in line.lower():
                ok = True
                break

    # Kill the tray app and any background claim agent
    _kill_tray()
    _stop_claim_proc()

    if not _is_daemon_running():
        _append_logs(["[daemon] Stopped by user"])
        return True, "Daemon stopped"

    if not ok:
        msg = "; ".join(err[-3:]) if err else "; ".join(out[-3:]) if out else "Failed to stop"
        return False, msg
    return True, "Daemon stopped"


# ═══════════════════════════════════════════════════════════════════════
#  Public API  —  Logs
# ═══════════════════════════════════════════════════════════════════════

def get_logs(n=100):
    """Return last N log lines from both the log file and in-memory buffer."""
    file_logs = _read_log_file(n)
    with _lock:
        mem_logs = list(_daemon_logs)
    combined = file_logs + mem_logs
    return combined[-n:]


# ═══════════════════════════════════════════════════════════════════════
#  Public API  —  Claim Flow
# ═══════════════════════════════════════════════════════════════════════

_setup_proc = None
_CLAIM_CODE = None


def _stop_setup():
    """Kill the persistent playit setup process if running."""
    global _setup_proc
    if _setup_proc:
        try:
            _setup_proc.kill()
            _setup_proc.wait(timeout=5)
        except Exception:
            pass
        _setup_proc = None


def run_cli(timeout=120):
    """Run 'playit setup' to claim the agent.

    'playit setup' does EVERYTHING in one command:
      1. Generates a claim code
      2. Prints the claim URL
      3. Waits for user to visit the URL and sign in
      4. Detects when the claim completes
      5. Downloads and provisions the secret to the daemon

    The process MUST stay running the whole time — kill it
    before the user claims and it shows 'waiting for agent'.

    Returns (ok, raw_output, lines).
    """
    global _setup_proc, _CLAIM_CODE
    if not _PLAYIT:
        return False, "playit.exe not found", []

    _stop_setup()

    # Daemon must be running
    if not _is_daemon_running():
        ok_start, msg_start = start_daemon()
        if not ok_start:
            return False, f"Daemon required: {msg_start}", []

    # Launch 'playit setup' as a persistent background process
    try:
        proc = subprocess.Popen(
            [_PLAYIT, "setup"],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            text=True,
            bufsize=1,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
    except Exception as e:
        return False, f"Failed: {e}", []

    # Read stdout until we get the claim URL
    collected = []
    url = ""
    code = ""

    def _reader():
        nonlocal url, code
        try:
            for line in iter(proc.stdout.readline, ""):
                clean = line.strip()
                if clean:
                    collected.append(clean)
                    # The URL line looks like: "Open this link to finish setting up playit:\nhttps://..."
                    m = re.search(r'(https?://playit\.gg/(?:claim/)?[A-Za-z0-9_-]+)', clean)
                    if m and not url:
                        url = m.group(1).rstrip(".,;:!?")
                        cm = re.search(r'/claim/(.+)', url)
                        if cm:
                            code = cm.group(1)
        except Exception:
            pass

    thr = threading.Thread(target=_reader, daemon=True)
    thr.start()
    thr.join(timeout=15)

    if not url:
        try:
            proc.kill()
            proc.wait(timeout=3)
        except Exception:
            pass
        msg = "; ".join(collected[-5:]) if collected else "No claim URL from playit setup"
        return False, msg, collected

    # Keep the process alive — this is what makes the website work!
    _setup_proc = proc
    _CLAIM_CODE = code if code else url.split("/claim/")[-1] if "/claim/" in url else ""

    with _lock:
        _daemon_logs.append(f"[playit] 'playit setup' running — visit URL to claim")

    lines = collected
    return True, "\n".join(lines), lines


def complete_claim(code):
    """Finalise the claim.

    'playit setup' handles the exchange & provisioning automatically
    once the user visits the URL.  This function just checks if the
    config now has a secret and restarts the daemon if needed.
    """
    if not _PLAYIT:
        return False, "playit.exe not found"

    # Kill the setup process (it should have already completed)
    _stop_setup()
    time.sleep(1)

    # Check if the claim succeeded — config should have a secret now
    if is_claimed():
        _append_logs(["[playit] Claim confirmed — secret is present"])
        return True, "Agent claimed successfully"
    else:
        _append_logs(["[playit] Setup completed but no secret found"])
        return True, "Setup completed (check daemon status)"


def parse_claim_url(lines):
    """Extract a playit.gg claim URL from text lines."""
    for line in lines:
        m = re.search(r'(https?://playit\.gg/(?:claim/)?[A-Za-z0-9_-]+)', line)
        if m:
            url = m.group(1).rstrip(".,;:!?")
            code_m = re.search(r'/claim/(.+)', url)
            return url, (code_m.group(1) if code_m else "")
    return None, None


def parse_tunnel_urls(lines):
    """Extract tunnel addresses (*.playit.gg) from text lines.

    Modern playit.gg configures tunnels via the web dashboard,
    so addresses rarely appear in CLI output. This is a best-effort scan.
    """
    _EXCLUDE = {"api.playit.gg", "auth.playit.gg", "playit.gg"}
    tunnels = []
    for line in lines:
        m = re.search(r'([a-z0-9-]+\.playit\.gg(?::\d+)?)', line, re.IGNORECASE)
        if m:
            addr = m.group(1).lower()
            host = addr.split(":")[0]
            if addr not in tunnels and host not in _EXCLUDE and 'claim' not in addr:
                tunnels.append(m.group(1))
    return tunnels


# ═══════════════════════════════════════════════════════════════════════
#  Public API  —  Status / Info
# ═══════════════════════════════════════════════════════════════════════

def check_tunnel_status():
    """Return a lightweight status dict (for quick polling)."""
    if not is_installed():
        return {"installed": False, "claimed": False, "running": False}
    daemon_on = _is_daemon_running()
    claimed = is_claimed()
    return {
        "installed": True,
        "claimed": claimed,
        "daemon_running": daemon_on,
        "running": claimed and daemon_on,
    }


def get_tunnel_info():
    logs = get_logs(100)
    url, code = parse_claim_url(logs)
    tunnels = parse_tunnel_urls(logs)
    claimed = is_claimed()
    daemon_on = _is_daemon_running()
    service_on = _is_service_running()
    tray_on = _is_tray_running()

    # If the daemon has tunnels, note the count from logs
    tunnel_count = _tunnel_count_from_logs(logs)

    _append_logs([
        f"[status] daemon={'service' if service_on else 'tray' if tray_on else 'off'} "
        f"claimed={'yes' if claimed else 'no'} "
        f"tunnels={tunnel_count}"
    ])

    return {
        "installed": is_installed(),
        "claimed": claimed,
        "daemon_running": daemon_on,
        "running": claimed and daemon_on,
        "logs": logs,
        "claim_url": url,
        "claim_code": code,
        "tunnels": tunnels,
        "tunnel_count": tunnel_count,
    }
