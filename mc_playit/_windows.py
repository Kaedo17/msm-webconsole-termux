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
    """Kill playitd-tray.exe if running (returns True if killed)."""
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

    # Kill the tray app too
    _kill_tray()

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

_CLAIM_CODE = None


def run_cli(timeout=120):
    """Generate a playit.gg claim code and URL.

    Flow:
      1. Start daemon first (daemon must be running for claim to work)
      2. `playit claim generate` → random claim code
      3. `playit claim url <code>` → URL for the user to visit
      4. Returns immediately.  User visits URL, then calls complete_claim().

    Returns (ok, raw_output, lines).
    """
    global _CLAIM_CODE
    if not _PLAYIT:
        return False, "playit.exe not found", []

    # Daemon MUST be running for the claim to work — the playit.gg website
    # needs to see the connected agent to associate the claim.
    if not _is_daemon_running():
        ok_start, msg_start = start_daemon()
        if not ok_start:
            return False, f"Need daemon running first: {msg_start}", []
        time.sleep(3)

    # Run generate — keeps a background agent alive so the website
    # can detect it during the claim.
    ok, out, err = _call_playit(["claim", "generate"], timeout=timeout)
    if not ok or not out:
        msg = "; ".join(err[-3:]) if err else ("; ".join(out[-3:]) if out else "No claim code")
        return False, msg, out + err
    code = out[0].strip()
    _CLAIM_CODE = code

    ok2, out2, err2 = _call_playit(["claim", "url", code], timeout=15)
    url = out2[0].strip() if ok2 and out2 else f"https://playit.gg/claim/{code}"

    lines = out + out2
    with _lock:
        _daemon_logs.append(f"[playit] Claim code generated: {code}")
        _daemon_logs.append(f"[playit] Claim URL: {url}")

    return True, "\n".join(lines), lines


def complete_claim(code):
    """Exchange claim code and provision the secret.

    Steps:
      1. `playit claim exchange <code>` — exchange claim for secret
      2. Kill tray app so it doesn't interfere
      3. `playit setup` — provision the secret
      4. Start the service with the new secret
    """
    if not _PLAYIT:
        return False, "playit.exe not found"

    ok, out, err = _call_playit(["claim", "exchange", code], timeout=30)
    if not ok:
        msg = "; ".join(err[-3:]) if err else ("; ".join(out[-3:]) if out else "Exchange failed")
        return False, msg
    _append_logs([f"[playit] Claim code {code} exchanged"])

    # Kill the tray app so setup doesn't conflict
    _kill_tray()
    time.sleep(1)

    ok2, out2, err2 = _call_playit(["setup"], timeout=30)
    if not ok2:
        msg = "; ".join(err2[-3:]) if err2 else "Setup failed"
        return False, f"Claimed but setup failed: {msg}"
    _append_logs(["[playit] Secret provisioned to daemon"])

    # Start the daemon
    stop_daemon()
    time.sleep(2)
    start_daemon()

    _append_logs(["[playit] Claim complete"])
    return True, "Agent claimed and configured successfully"


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
