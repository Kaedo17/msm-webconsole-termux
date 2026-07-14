"""Playit.gg tunnel: daemon with live log capture.

On Termux: uses playitd daemon.
On Windows desktop: user downloads the portable exe alongside the app.
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

def _find_playit_bin():
    """Find a playit binary in PATH or common install locations."""
    # Search in PATH first
    for name in ["playit-cli", "playit", "playitd"]:
        p = shutil.which(name)
        if p:
            return p
    # Search in the app directory
    for pattern in ["playit.exe", "playit-cli.exe", "playitd.exe", "playit-windows-x86_64-signed.exe"]:
        p = _APP_DIR / pattern
        if p.exists():
            return str(p)
    # Search common install locations
    for base in ["C:/Program Files", "C:/Program Files (x86)"]:
        bp = Path(base) / "playit_gg" / "bin"
        if bp.exists():
            for name in ["playit.exe", "playit-cli.exe", "playitd.exe"]:
                p = bp / name
                if p.exists():
                    return str(p)
    return ""

_PLAYIT_BIN = _find_playit_bin()
_PLAYIT_CLI = _PLAYIT_BIN
_PLAYITD = _PLAYIT_BIN
_PLAYIT_SECRET = Path.home() / ".playit" / "secret"

_daemon_proc = None
_daemon_logs = deque(maxlen=500)
_lock = threading.Lock()

_ANSI_RE = re.compile(
    r'\x1b\[[0-9;]*[a-zA-Z]'
    r'|\x1b\][^\x07]*\x07'
    r'|\x1b[()][AB012]'
    r'|\x1b[=>]'
    r'|\x1b\[\?[0-9]+[hl]'
)


def _strip_ansi(text):
    text = _ANSI_RE.sub('', text)
    text = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', text)
    return text


def is_installed():
    return (bool(_PLAYITD) and os.access(_PLAYITD, os.X_OK)) or \
           (bool(_PLAYIT_CLI) and os.access(_PLAYIT_CLI, os.X_OK))


def install_commands():
    return ["pkg install tur-repo -y", "pkg install playit -y"]


def is_claimed():
    if _PLAYIT_SECRET.exists():
        return True
    # Check common playit.gg config locations
    for path in [
        Path.home() / ".config" / "playit_gg" / "playit.toml",
        Path.home() / ".playit" / "playit.toml",
        Path.home() / "AppData" / "Local" / "playit_gg" / "playit.toml",
        Path.home() / "AppData" / "Roaming" / "playit_gg" / "playit.toml",
    ]:
        if path.exists():
            return True
    # Also check from env vars
    for var in ["LOCALAPPDATA", "APPDATA"]:
        base = os.environ.get(var, "")
        if base:
            p = Path(base) / "playit_gg" / "playit.toml"
            if p.exists():
                return True
    return False


def _is_daemon_running():
    global _daemon_proc
    if _daemon_proc and _daemon_proc.poll() is None:
        return True
    try:
        subprocess.run(["pgrep", "-x", "playitd"], capture_output=True, timeout=3, check=True)
        return True
    except Exception:
        return False


def _reader_thread(proc):
    def _read_pipe(pipe):
        try:
            for line in iter(pipe.readline, ""):
                clean = _strip_ansi(line.rstrip("\n\r"))
                if clean.strip():
                    with _lock:
                        _daemon_logs.append(clean)
        except Exception:
            pass

    t1 = threading.Thread(target=_read_pipe, args=(proc.stdout,), daemon=True)
    t2 = threading.Thread(target=_read_pipe, args=(proc.stderr,), daemon=True)
    t1.start()
    t2.start()


def start_daemon():
    global _daemon_proc
    if not _PLAYITD:
        return False, "playitd not found"
    if _is_daemon_running():
        return True, "Daemon already running"
    try:
        env = dict(os.environ)
        env["TERM"] = "dumb"
        env.setdefault("RUST_LOG", "info")
        startupinfo = None
        if os.name == "nt":
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        _daemon_proc = subprocess.Popen(
            [_PLAYITD],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            stdin=subprocess.DEVNULL,
            text=True,
            bufsize=1,
            env=env,
            startupinfo=startupinfo,
        )
        _reader_thread(_daemon_proc)
        time.sleep(4)
        return True, "Daemon started"
    except Exception as e:
        return False, str(e)


def stop_daemon():
    global _daemon_proc
    stop_cli()
    proc = _daemon_proc
    if not proc or proc.poll() is not None:
        try:
            subprocess.run(["pkill", "-x", "playitd"], capture_output=True, timeout=5)
        except Exception:
            pass
    else:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except Exception:
            proc.kill()
            proc.wait(timeout=3)
    _daemon_proc = None
    with _lock:
        _daemon_logs.append("[daemon] Stopped by user")
    return True, "Daemon stopped"


def get_logs(n=100):
    with _lock:
        return list(_daemon_logs)[-n:]


def parse_claim_url(lines):
    for line in lines:
        m = re.search(r'(https?://playit\.gg/(?:claim/)?[A-Za-z0-9_-]+)', line)
        if m:
            url = m.group(1).rstrip(".,;:!?")
            code_m = re.search(r'/claim/(.+)', url)
            return url, (code_m.group(1) if code_m else "")
    return None, None


def parse_tunnel_urls(lines):
    tunnels = []
    for line in lines:
        m = re.search(r'([a-z0-9-]+\.playit\.gg(?::\d+)?)', line, re.IGNORECASE)
        if m:
            addr = m.group(1)
            if addr not in tunnels and 'claim' not in addr.lower():
                tunnels.append(addr)
    return tunnels


_claim_proc = None


def stop_cli():
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

    The process must stay running while the user visits the claim URL,
    so once we find a URL we leave the process running in the background
    and return immediately. It will exit on its own when the claim completes.
    """
    global _claim_proc
    stop_cli()  # Kill any previous claim process
    if not _PLAYIT_CLI:
        return False, "playit-cli not found", []
    try:
        env = dict(os.environ)
        env["TERM"] = "dumb"
        env["NO_COLOR"] = "1"
        startupinfo = None
        if os.name == "nt":
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        proc = subprocess.Popen(
            [_PLAYIT_CLI],
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
                # Check if this line has a claim URL
                if "playit.gg/claim/" in clean:
                    found_claim = True
            for line in iter(proc.stderr.readline, ""):
                clean = _strip_ansi(line.rstrip("\n\r"))
                if clean.strip():
                    collected.append(clean)

        thr = threading.Thread(target=reader, daemon=True)
        thr.start()

        # Wait a few seconds for the claim URL to appear
        thr.join(timeout=8)

        # If we found a claim URL, leave the process running
        # The user needs it alive to complete the claim
        if found_claim:
            _claim_proc = proc
            with _lock:
                for line in collected:
                    _daemon_logs.append(line)
            return True, "\n".join(collected), collected

        # No claim URL found yet — wait a bit more or kill
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


def check_tunnel_status():
    if not is_installed():
        return {"installed": False, "claimed": False, "running": False}

    daemon_on = _is_daemon_running()
    claimed = is_claimed()
    result = {
        "installed": True,
        "claimed": claimed,
        "daemon_running": daemon_on,
        "running": claimed and daemon_on,
    }
    return result


def get_tunnel_info():
    logs = get_logs(100)
    url, code = parse_claim_url(logs)
    tunnels = parse_tunnel_urls(logs)
    claimed = is_claimed()
    daemon_on = _is_daemon_running()
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


