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
import urllib.request
from collections import deque
from pathlib import Path

_PLAYIT_CLI = shutil.which("playit-cli") or shutil.which("playit") or ""
_PLAYITD = shutil.which("playitd") or ""
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
    return _PLAYIT_SECRET.exists() or (Path.home() / ".config" / "playit_gg" / "playit.toml").exists()


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
        _daemon_proc = subprocess.Popen(
            [_PLAYITD],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            stdin=subprocess.DEVNULL,
            text=True,
            bufsize=1,
            env=env,
        )
        _reader_thread(_daemon_proc)
        time.sleep(4)
        return True, "Daemon started"
    except Exception as e:
        return False, str(e)


def stop_daemon():
    global _daemon_proc
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


def run_cli(timeout=12):
    if not _PLAYIT_CLI:
        return False, "playit-cli not found", []
    try:
        env = dict(os.environ)
        env["TERM"] = "dumb"
        env["NO_COLOR"] = "1"
        proc = subprocess.Popen(
            [_PLAYIT_CLI],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            stdin=subprocess.DEVNULL,
            text=True,
            bufsize=1,
            env=env,
        )
        collected = []

        def reader():
            for line in iter(proc.stdout.readline, ""):
                clean = _strip_ansi(line.rstrip("\n\r"))
                if clean.strip():
                    collected.append(clean)
            for line in iter(proc.stderr.readline, ""):
                clean = _strip_ansi(line.rstrip("\n\r"))
                if clean.strip():
                    collected.append(clean)

        thr = threading.Thread(target=reader, daemon=True)
        thr.start()
        thr.join(timeout=timeout)
        proc.kill()
        proc.wait(timeout=5)
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


def download_windows_portable(dest_dir):
    """Download the playit.gg Windows portable EXE to dest_dir.

    Returns (success, path_or_error).
    If dest_dir is None, uses the directory of the current executable.
    """
    if dest_dir is None:
        if getattr(sys, "frozen", False):
            dest_dir = Path(sys.executable).resolve().parent
        else:
            dest_dir = Path.cwd()
    else:
        dest_dir = Path(dest_dir)

    dest_dir.mkdir(parents=True, exist_ok=True)
    dest_path = dest_dir / "playit.exe"

    # Download from the official redirect
    url = "https://playit.gg/download/windows"
    try:
        req = urllib.request.Request(url, headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "application/octet-stream",
        })
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = resp.read()
            dest_path.write_bytes(data)
        # Make sure it's a valid EXE
        if dest_path.stat().st_size < 100000:
            dest_path.unlink(missing_ok=True)
            return False, "Downloaded file is too small — may not be a valid EXE."
        return True, str(dest_path)
    except Exception as e:
        dest_path.unlink(missing_ok=True)
        return False, str(e)
