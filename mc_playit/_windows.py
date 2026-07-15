"""Playit.gg tunnel — Windows detection only.

On Windows, playit.gg is managed externally by the user through:
  - The system tray app (playitd-tray.exe) — auto-starts on boot
  - The official playit.gg installer / CLI

This module only DETECTS the state of playit.gg on the system:
  - Is playit installed?        (playit.exe found)
  - Is it claimed?              (playit.toml has secret_key)
  - Is the daemon running?      (playitd-tray.exe or service active)
  - Tunnel info from daemon log (tunnel_count, addresses)

It does NOT start/stop the daemon or handle the claim flow.
Users manage playit through the tray icon or playit CLI directly.
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

_PLAYIT = None
_PLAYIT_TOML = None
_PLAYIT_LOG = None

_daemon_logs = deque(maxlen=500)
_lock = threading.Lock()

_MANAGED_EXTERNALLY = True  # Windows: managed through tray app / playit CLI


def _find_playit():
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


def _append_logs(lines):
    with _lock:
        for line in lines:
            _daemon_logs.append(line)


def _read_log_file(n=100):
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


def _is_service_running():
    """Check if playit service is running via 'playit status'."""
    if not _PLAYIT:
        return False
    try:
        r = subprocess.run(
            [_PLAYIT, "status"],
            capture_output=True, text=True, timeout=10,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        out = r.stdout
        return "PID:" in out or ("Phase:" in out and "stopped" not in out.lower())
    except Exception:
        return False


def _is_tray_running():
    """Check if playitd-tray.exe process is running."""
    try:
        r = subprocess.run(
            ["tasklist", "/fi", "imagename eq playitd-tray.exe"],
            capture_output=True, text=True, timeout=10,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        return "playitd-tray.exe" in r.stdout
    except Exception:
        return False


# ═══════════════════════════════════════════════════════════════════════
#  Public API
# ═══════════════════════════════════════════════════════════════════════

def is_installed():
    return bool(_PLAYIT)


def install_commands():
    return []


def is_claimed():
    if not _PLAYIT_TOML:
        return False
    try:
        return "secret_key" in Path(_PLAYIT_TOML).read_text(encoding="utf-8", errors="replace")
    except Exception:
        return False


def _is_daemon_running():
    return _is_service_running() or _is_tray_running()


def start_daemon():
    return False, "Playit is managed externally on Windows — use the tray app or 'playit start' in a terminal."


def stop_daemon():
    return False, "Playit is managed externally on Windows — use the tray app or 'playit stop' in a terminal."


def run_cli():
    return False, "Use the playit tray app or run 'playit setup' in a terminal to claim.", []


def complete_claim(code):
    return False, "Use the playit tray app to claim your agent."


def get_logs(n=100):
    file_logs = _read_log_file(n)
    with _lock:
        mem_logs = list(_daemon_logs)
    combined = file_logs + mem_logs
    return combined[-n:]


def parse_claim_url(lines):
    for line in lines:
        m = re.search(r'(https?://playit\.gg/(?:claim/)?[A-Za-z0-9_-]+)', line)
        if m:
            url = m.group(1).rstrip(".,;:!?")
            code_m = re.search(r'/claim/(.+)', url)
            return url, (code_m.group(1) if code_m else "")
    return None, None


def parse_tunnel_urls(lines):
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


def check_tunnel_status():
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

    tunnel_count = 0
    for line in logs:
        m = re.search(r'tunnel_count=(\d+)', line)
        if m:
            tunnel_count = int(m.group(1))

    return {
        "installed": is_installed(),
        "claimed": claimed,
        "daemon_running": daemon_on,
        "running": claimed and daemon_on,
        "managed_externally": True,
        "logs": logs,
        "claim_url": url,
        "claim_code": code,
        "tunnels": tunnels,
        "tunnel_count": tunnel_count,
    }
