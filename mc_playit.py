"""Playit.gg tunnel for Termux: playitd daemon only (playit-cli runs manually)."""

import os
import re
import shutil
import subprocess
import time
from pathlib import Path

_PLAYITD = shutil.which("playitd") or ""
_PLAYIT_SECRET = Path.home() / ".playit" / "secret"


def is_installed():
    return bool(_PLAYITD) and os.access(_PLAYITD, os.X_OK)


def install_commands():
    return ["pkg install tur-repo -y", "pkg install playit -y"]


def is_claimed():
    return _PLAYIT_SECRET.exists() or (Path.home() / ".config" / "playit_gg" / "playit.toml").exists()


def _is_daemon_running():
    if not _PLAYITD:
        return False
    for name in ("playitd",):
        try:
            subprocess.run(["pgrep", "-x", name], capture_output=True, timeout=3, check=True)
            return True
        except Exception:
            continue
    return False


def start_daemon():
    """Start playitd as a background daemon. Returns (ok, msg)."""
    if not _PLAYITD:
        return False, "playitd not found"
    if _is_daemon_running():
        return True, "Daemon already running"
    try:
        subprocess.Popen(
            [_PLAYITD],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL,
        )
        time.sleep(2)
        return True, "Daemon started"
    except Exception as e:
        return False, str(e)


def check_tunnel_status():
    if not is_installed():
        return {"installed": False, "claimed": False, "running": False}

    daemon_on = _is_daemon_running()
    claimed = is_claimed()
    result = {
        "installed": True,
        "claimed": claimed,
        "daemon_running": daemon_on,
        "running": False,
    }

    if not daemon_on:
        return result

    result["running"] = claimed
    return result
