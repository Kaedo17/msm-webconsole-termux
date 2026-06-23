"""Playit.gg tunnel for Termux: playitd daemon + playit-cli capture."""

import os
import re
import shlex
import shutil
import subprocess
import threading
import time
from pathlib import Path

_PLAYIT_CLI = shutil.which("playit-cli") or shutil.which("playit") or ""
_PLAYITD = shutil.which("playitd") or ""
_PLAYIT_SECRET = Path.home() / ".playit" / "secret"


def is_installed():
    return bool(_PLAYIT_CLI) and os.access(_PLAYIT_CLI, os.X_OK)


def install_commands():
    return ["pkg install tur-repo -y", "pkg install playit -y"]


def is_claimed():
    return _PLAYIT_SECRET.exists() or (Path.home() / ".config" / "playit_gg" / "playit.toml").exists()


def _is_daemon_running():
    if not _PLAYITD:
        return False
    try:
        subprocess.run(["pgrep", "-x", "playitd"], capture_output=True, timeout=3, check=True)
        return True
    except Exception:
        return False


def start_daemon():
    if not _PLAYITD:
        return False, "playitd not found"
    if _is_daemon_running():
        return True, "Daemon already running"
    try:
        subprocess.Popen([_PLAYITD], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL)
        time.sleep(2)
        return True, "Daemon started"
    except Exception as e:
        return False, str(e)


def run_cli(timeout=25):
    """Run playit-cli with a PTY wrapper and capture output. Returns (ok, output_str, lines)."""
    if not _PLAYIT_CLI:
        return False, "playit-cli not found", []

    script_bin = shutil.which("script")
    if script_bin:
        cmd_str = shlex.join([_PLAYIT_CLI]) if hasattr(shlex, 'join') else _PLAYIT_CLI
        cmd = [script_bin, "-q", "-c", cmd_str, "/dev/null"]
    else:
        cmd = [_PLAYIT_CLI]

    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            stdin=subprocess.DEVNULL, text=True, bufsize=1,
        )
        collected = []
        done = threading.Event()

        def reader():
            for line in iter(proc.stdout.readline, ""):
                collected.append(line)
            for line in iter(proc.stderr.readline, ""):
                collected.append(line)
            done.set()

        thr = threading.Thread(target=reader, daemon=True)
        thr.start()
        thr.join(timeout=timeout)

        proc.kill()
        proc.wait(timeout=5)

        lines = [l.rstrip("\n\r") for l in collected]
        return True, "\n".join(lines), lines
    except Exception as e:
        return False, str(e), []


def parse_claim_url(lines):
    """Parse claim URL from playit-cli output lines. Returns (url, code) or (None, None)."""
    for line in lines:
        m = re.search(r'(https?://playit\.gg/(?:claim/)?\S+)', line)
        if m:
            url = m.group(1).rstrip(".,;:!?")
            code = re.search(r'/claim/(\S+)', url)
            return url, (code.group(1) if code else "")
        m = re.search(r'(playit\.gg/claim/\S+)', line)
        if m:
            url = "https://" + m.group(1).rstrip(".,;:!?")
            code = re.search(r'/claim/(\S+)', url)
            return url, (code.group(1) if code else "")
    return None, None


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
