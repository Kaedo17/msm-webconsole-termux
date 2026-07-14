"""Playit.gg tunnel — Windows implementation.

Uses the modern playit CLI (playit.exe) as a single binary:
  - playit start / stop / status   — service management
  - playit claim generate / url / exchange — account claim
  - playit setup                   — secret provisioning
  - playit attach                  — live log streaming (via IPC)

The daemon is managed as a Windows service via `playit start/stop`.
Tunnels are configured through the playit.gg web dashboard.
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


_PLAYIT = None          # Path to playit.exe
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
    # App directory (frozen EXE sidecar)
    for name in ["playit.exe", "playit"]:
        p = _APP_DIR / name
        if p.exists():
            return str(p.resolve())
    # Official installer location
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
        p = Path(prog_data) / "playit_gg" / "logs" / "playitd.log"
        return str(p.resolve())
    return str(Path.home() / ".playit" / "playitd.log")


def _init():
    global _PLAYIT, _PLAYIT_TOML, _PLAYIT_LOG
    _PLAYIT = _find_playit()
    _PLAYIT_TOML = _find_toml()
    _PLAYIT_LOG = _find_log()


_init()   # Run at module import


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
        )
        out_lines = [l for l in r.stdout.split("\n") if l.strip()] if r.stdout.strip() else []
        err_lines = [l for l in r.stderr.split("\n") if l.strip()] if r.stderr.strip() else []
        ok = r.returncode == 0
        # Buffer output lines for log viewing
        if out_lines:
            _append_logs(out_lines)
        return ok, out_lines, err_lines
    except subprocess.TimeoutExpired:
        return False, [], ["Command timed out"]
    except Exception as e:
        return False, [], [str(e)]


def _call_playit_bg(args):
    """Launch a playit CLI command in the background (no wait). Returns Popen."""
    if not _PLAYIT:
        return None
    startupinfo = subprocess.STARTUPINFO()
    startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    return subprocess.Popen(
        [_PLAYIT] + args,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        stdin=subprocess.DEVNULL,
        text=True,
        bufsize=1,
        startupinfo=startupinfo,
    )


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


def _parse_status_field(lines, field):
    """Extract a field value from 'playit status' output.

    e.g. _parse_status_field(lines, "Phase:") → "waiting for secret"
    """
    for line in lines:
        if field in line:
            idx = line.find(field)
            return line[idx + len(field):].strip()
    return ""


_CLAIM_PROC = None
_CLAIM_CODE = None


def _stop_claim_proc():
    """Kill any lingering claim-exchange background process."""
    global _CLAIM_PROC
    if _CLAIM_PROC:
        try:
            _CLAIM_PROC.terminate()
            _CLAIM_PROC.wait(timeout=5)
        except Exception:
            pass
        _CLAIM_PROC = None


# ═══════════════════════════════════════════════════════════════════════
#  Public API  —  Installation / Status
# ═══════════════════════════════════════════════════════════════════════

def is_installed():
    """Check if playit.exe is available on the system."""
    return bool(_PLAYIT)


def install_commands():
    """Windows: no package-manager install available.

    Returns empty list — user must download from playit.gg/download/windows.
    """
    return []


def is_claimed():
    """Check if the playit agent has a valid secret key on disk."""
    if not _PLAYIT_TOML:
        return False
    try:
        content = Path(_PLAYIT_TOML).read_text(encoding="utf-8", errors="replace")
        return "secret_key" in content
    except Exception:
        return False


# ═══════════════════════════════════════════════════════════════════════
#  Public API  —  Daemon Management
# ═══════════════════════════════════════════════════════════════════════

def _is_daemon_running():
    """Check if the playit Windows service is running via 'playit status'."""
    if not _PLAYIT:
        return False
    ok, out, _ = _call_playit(["status"])
    if not ok and not out:
        return False
    phase = _parse_status_field(out, "Phase:")
    if phase and phase not in ("", "stopped"):
        # "running", "waiting for secret", etc — any non-empty phase = alive
        pid = _parse_status_field(out, "PID:")
        return bool(pid) or bool(phase)
    return bool(_parse_status_field(out, "PID:"))


def start_daemon():
    """Start the playit Windows service via 'playit start'."""
    if not _PLAYIT:
        return False, "playit.exe not found"
    if _is_daemon_running():
        return True, "Service already running"
    ok, out, err = _call_playit(["start"], timeout=45)
    if ok:
        time.sleep(3)
        return True, "Service started"
    msg = "; ".join(err[-3:]) if err else "; ".join(out[-3:]) if out else "Failed to start"
    return False, msg


def stop_daemon():
    """Stop the playit Windows service via 'playit stop'."""
    ok, out, err = _call_playit(["stop"], timeout=30)
    if ok:
        return True, "Service stopped"
    # "already stopped" / "not running" is not an error
    for line in out + err:
        if "not running" in line.lower() or "stopped" in line.lower():
            return True, "Service already stopped"
    if not _is_daemon_running():
        return True, "Service already stopped"
    msg = "; ".join(err[-3:]) if err else "; ".join(out[-3:]) if out else "Failed to stop"
    return False, msg


# ═══════════════════════════════════════════════════════════════════════
#  Public API  —  Logs
# ═══════════════════════════════════════════════════════════════════════

def get_logs(n=100):
    """Return last N log lines from both the log file and in-memory buffer."""
    file_logs = _read_log_file(n)
    with _lock:
        mem_logs = list(_daemon_logs)
    # File logs are older, mem logs are newer (CLI output)
    combined = file_logs + mem_logs
    return combined[-n:]


# ═══════════════════════════════════════════════════════════════════════
#  Public API  —  Claim Flow
# ═══════════════════════════════════════════════════════════════════════

def run_cli(timeout=120):
    """Generate a playit.gg claim code and URL.

    Modern claim flow (no persistent process needed):
      1. `playit claim generate`  → random claim code
      2. `playit claim url <code>` → URL for the user to visit
      3. Returns immediately with the URL.
      4. User calls complete_claim(<code>) after visiting the URL.

    Returns (ok, raw_output, lines).
    """
    global _CLAIM_CODE
    if not _PLAYIT:
        return False, "playit.exe not found", []

    # Step 1: Generate claim code
    _stop_claim_proc()
    ok, out, err = _call_playit(["claim", "generate"], timeout=15)
    if not ok or not out:
        msg = "; ".join(err[-3:]) if err else ("; ".join(out[-3:]) if out else "No claim code")
        return False, msg, out + err
    code = out[0].strip()
    _CLAIM_CODE = code

    # Step 2: Get the claim URL
    ok2, out2, err2 = _call_playit(["claim", "url", code], timeout=15)
    url = out2[0].strip() if ok2 and out2 else f"https://playit.gg/claim/{code}"

    lines = out + out2
    with _lock:
        _daemon_logs.append(f"[playit] Claim code generated: {code}")
        _daemon_logs.append(f"[playit] Claim URL: {url}")

    return True, "\n".join(lines), lines


def complete_claim(code):
    """Exchange a claim code and provision the secret to the daemon.

    Call this AFTER the user has visited the claim URL in their browser.

    Steps:
      1. `playit claim exchange <code>` — exchange the code for a secret
      2. `playit setup` — provision the secret to the daemon
      3. Restart the daemon so it picks up the new secret
    """
    if not _PLAYIT:
        return False, "playit.exe not found"

    # Step 1: Exchange
    ok, out, err = _call_playit(["claim", "exchange", code], timeout=30)
    if not ok:
        msg = "; ".join(err[-3:]) if err else ("; ".join(out[-3:]) if out else "Exchange failed")
        return False, msg
    _append_logs([f"[playit] Claim code {code} exchanged successfully"])

    # Step 2: Provision secret
    ok2, out2, err2 = _call_playit(["setup"], timeout=30)
    if not ok2:
        msg = "; ".join(err2[-3:]) if err2 else "Setup failed"
        return False, f"Claimed but setup failed: {msg}"
    _append_logs(["[playit] Secret provisioned to daemon"])

    # Step 3: Restart daemon
    stop_daemon()
    time.sleep(2)
    start_daemon()

    _append_logs(["[playit] Claim complete — daemon restarted"])
    return True, "Agent claimed and configured successfully"


def parse_claim_url(lines):
    """Extract a playit.gg claim URL from log/CLI lines."""
    for line in lines:
        m = re.search(r'(https?://playit\.gg/(?:claim/)?[A-Za-z0-9_-]+)', line)
        if m:
            url = m.group(1).rstrip(".,;:!?")
            code_m = re.search(r'/claim/(.+)', url)
            return url, (code_m.group(1) if code_m else "")
    return None, None


def parse_tunnel_urls(lines):
    """Extract tunnel addresses (*.playit.gg) from log lines.

    Modern playit.gg configures tunnels via the web dashboard,
    so tunnel addresses rarely appear in CLI output.  This
    function still scans for them as a best-effort fallback.
    """
    _EXCLUDE = {"api.playit.gg", "auth.playit.gg", "playit.gg"}
    tunnels = []
    for line in lines:
        m = re.search(r'([a-z0-9-]+\.playit\.gg(?::\d+)?)', line, re.IGNORECASE)
        if m:
            addr = m.group(1).lower()
            host = addr.split(":")[0]
            if addr not in tunnels and host not in _EXCLUDE and 'claim' not in addr:
                tunnels.append(m.group(1))  # keep original casing
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
    """Return full tunnel info including logs, claim URL, and tunnel addresses."""
    logs = get_logs(100)
    url, code = parse_claim_url(logs)
    tunnels = parse_tunnel_urls(logs)
    claimed = is_claimed()
    daemon_on = _is_daemon_running()

    # Try to get more details from 'playit status'
    if daemon_on:
        ok, out, _ = _call_playit(["status"])
        status_lines = out if ok else []
    else:
        status_lines = []

    return {
        "installed": is_installed(),
        "claimed": claimed,
        "daemon_running": daemon_on,
        "running": claimed and daemon_on,
        "logs": logs,
        "claim_url": url,
        "claim_code": code,
        "tunnels": tunnels,
    }
