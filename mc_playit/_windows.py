"""Playit.gg tunnel — Windows implementation.

Manages the playit CLI (playit.exe) for setup, auth, and monitoring.
The daemon (playitd) can be managed through the CLI or via the system tray app.

On Windows, playit.gg can be managed two ways:
  - CLI mode:  run_cli() / start_daemon() / stop_daemon() via playit.exe
  - Tray app:  playitd-tray.exe in the system tray (auto-starts on boot)
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
    """Check if playit daemon is running via 'playit status'."""
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


def _get_daemon_phase():
    """Get the current daemon phase string from 'playit status'."""
    if not _PLAYIT:
        return "unknown"
    try:
        r = subprocess.run(
            [_PLAYIT, "status"],
            capture_output=True, text=True, timeout=10,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        for line in r.stdout.splitlines():
            if "Phase:" in line:
                return line.split("Phase:")[-1].strip()
        return "unknown"
    except Exception:
        return "unknown"


_ansi_re = re.compile(
    r'\x1b\[[0-9;]*[a-zA-Z]'
    r'|\x1b\][^\x07]*\x07'
    r'|\x1b[()][AB012]'
    r'|\x1b[=>]'
    r'|\x1b\[\?[0-9]+[hl]'
)


def _strip_ansi(text):
    text = _ansi_re.sub('', text)
    text = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', text)
    return text


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
    """Start the playit daemon. Tries CLI first, then falls back to info message."""
    if _is_daemon_running():
        return True, "Daemon already running."

    phase = _get_daemon_phase()

    # If daemon service exists but is waiting for secret, no need to "start" it
    if _is_service_running() and phase == "waiting for secret":
        return True, "Daemon is running but waiting for authentication. Run the tunnel setup."

    # Try starting via CLI
    if _PLAYIT:
        try:
            r = subprocess.run(
                [_PLAYIT, "start"],
                capture_output=True, text=True, timeout=15,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
            if r.returncode == 0:
                time.sleep(2)
                if _is_daemon_running():
                    _append_logs(["[WebConsole] Daemon started via CLI"])
                    return True, "Daemon started."
                else:
                    # Started but not detected — check phase
                    new_phase = _get_daemon_phase()
                    if new_phase == "waiting for secret":
                        return True, "Daemon started but needs authentication. Run tunnel setup."
                    return True, "Daemon start command issued."
            # Return the CLI output as info
            msg = r.stderr.strip() or r.stdout.strip() or "Unknown error"
            # If it says already running, treat as success
            if "already running" in msg.lower() or "already started" in msg.lower():
                return True, "Daemon already running."
            return False, f"playit start failed: {msg}"
        except subprocess.TimeoutExpired:
            return False, "playit start timed out after 15s."
        except Exception as e:
            return False, f"playit start error: {e}"

    # If no playit CLI found, guide the user
    if _is_tray_running():
        return True, "Daemon running via tray app."
    return False, ("Playit not running. Open the playit.gg tray app from the Start Menu, "
                   "or run 'playit start' in a terminal.")


def stop_daemon():
    """Stop the playit daemon via CLI."""
    if _PLAYIT:
        try:
            r = subprocess.run(
                [_PLAYIT, "stop"],
                capture_output=True, text=True, timeout=15,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
            _append_logs(["[WebConsole] Daemon stopped via CLI"])
            return True, "Daemon stop command issued."
        except subprocess.TimeoutExpired:
            return False, "playit stop timed out after 15s."
        except Exception as e:
            return False, f"playit stop error: {e}"
    return False, ("Playit not found. Stop it via the tray app or "
                   "run 'playit stop' in a terminal.")


_claim_proc = None


def _stop_cli():
    """Kill any running claim CLI process."""
    global _claim_proc
    if _claim_proc:
        try:
            _claim_proc.kill()
            _claim_proc.wait(timeout=3)
        except Exception:
            pass
        _claim_proc = None


def run_cli(timeout=120):
    """Run playit CLI to get a claim URL.

    On Windows, runs 'playit' which enters the setup/claim flow.
    The process must stay running while the user visits the claim URL,
    so once we find a URL we leave the process running in the background.
    It will exit on its own when the claim completes.
    """
    global _claim_proc
    _stop_cli()
    if not _PLAYIT:
        return False, "playit not found.", []

    try:
        env = dict(os.environ)
        env["TERM"] = "dumb"
        env["NO_COLOR"] = "1"
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW

        proc = subprocess.Popen(
            [_PLAYIT],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            stdin=subprocess.DEVNULL,
            text=True,
            bufsize=1,
            env=env,
            startupinfo=startupinfo,
        )
        collected = []
        found_claim = False

        def reader():
            nonlocal found_claim
            for line in iter(proc.stdout.readline, ""):
                clean = _strip_ansi(line.rstrip("\n\r"))
                if clean.strip():
                    collected.append(clean)
                if "playit.gg/claim/" in clean:
                    found_claim = True
            for line in iter(proc.stderr.readline, ""):
                clean = _strip_ansi(line.rstrip("\n\r"))
                if clean.strip():
                    collected.append(clean)

        thr = threading.Thread(target=reader, daemon=True)
        thr.start()

        # Wait for the claim URL to appear (up to 8 seconds)
        thr.join(timeout=8)

        # If we found a claim URL, leave the process running
        if found_claim:
            _claim_proc = proc
            with _lock:
                for line in collected:
                    _daemon_logs.append(line)
            return True, "\n".join(collected), collected

        # No claim URL yet — wait a bit more or kill
        thr.join(timeout=5)
        try:
            proc.kill()
            proc.wait(timeout=3)
        except Exception:
            pass
        with _lock:
            for line in collected:
                _daemon_logs.append(line)
        return True, "\n".join(collected), collected

    except Exception as e:
        return False, str(e), []


def complete_claim(code):
    """Finalise claim after user visits the claim URL (Windows only)."""
    if not _PLAYIT:
        return False, "playit not found."
    try:
        # After the user visits the URL, the running playit process
        # should detect the claim and save the secret automatically.
        # If the process already exited, try running claim command.
        if _claim_proc and _claim_proc.poll() is None:
            # Still running — wait for it to detect the claim
            try:
                _claim_proc.wait(timeout=60)
            except subprocess.TimeoutExpired:
                _claim_proc.kill()
            _stop_cli()
            # Check if the secret was saved
            if is_claimed():
                _append_logs(["[WebConsole] Claim completed successfully"])
                return True, "Claim completed!"
            # If not claimed yet, try using the exchange code
        if code:
            proc = subprocess.run(
                [_PLAYIT, "setup", "--claim", code],
                capture_output=True, text=True, timeout=30,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
            out = (proc.stdout + proc.stderr).strip()
            if proc.returncode == 0 or "success" in out.lower() or "claimed" in out.lower():
                _append_logs(["[WebConsole] Claim completed via exchange code"])
                return True, "Claim completed!"
            return False, f"Claim failed: {out}"
        return False, "No claim code provided."
    except Exception as e:
        return False, str(e)


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
        "logs": logs,
        "claim_url": url,
        "claim_code": code,
        "tunnels": tunnels,
        "tunnel_count": tunnel_count,
    }
