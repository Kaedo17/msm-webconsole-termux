"""Playit.gg tunnel integration — Termux: playitd + playit-cli."""

import os
import re
import shutil
import subprocess
import time
from pathlib import Path

PLAYITD = shutil.which("playitd") or ""
PLAYIT_CLI = shutil.which("playit-cli") or shutil.which("playit") or ""
PLAYIT_SECRET = Path.home() / ".playit" / "secret"


def is_installed():
    return bool(PLAYIT_CLI) and os.access(PLAYIT_CLI, os.X_OK)


def install_commands():
    return ["pkg install tur-repo -y", "pkg install playit -y"]


def get_version():
    if not is_installed():
        return ""
    try:
        out = subprocess.check_output([PLAYIT_CLI, "--version"], text=True, timeout=10, stderr=subprocess.PIPE)
        return out.strip()
    except Exception:
        return ""


def is_claimed():
    return PLAYIT_SECRET.exists()


def _is_daemon_running():
    """Check if playitd process is running."""
    if not PLAYITD:
        return False
    try:
        import signal
        out = subprocess.check_output(["pgrep", "-x", "playitd"], text=True, timeout=5, stderr=subprocess.DEVNULL)
        return bool(out.strip())
    except Exception:
        return False


def _start_daemon():
    """Start playitd as a background process."""
    if not PLAYITD:
        return False, "playitd not found."
    if _is_daemon_running():
        return True, "Daemon already running."
    try:
        subprocess.Popen(
            [PLAYITD],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL,
        )
        time.sleep(2)
        if _is_daemon_running():
            return True, "Daemon started."
        return True, "Daemon launch attempted (check status)"
    except Exception as e:
        return False, str(e)


def start_tunnel(timeout=30):
    if not is_installed():
        return False, {"error": "Playit not installed."}

    ok, msg = _start_daemon()
    if not ok:
        return False, {"error": f"Failed to start daemon: {msg}"}

    if is_claimed():
        return True, {"message": "Already claimed. Tunnel should be running."}

    try:
        proc = subprocess.Popen(
            [PLAYIT_CLI],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            stdin=subprocess.DEVNULL, text=True, bufsize=1,
        )
        lines = []
        claim_url = None
        start_time = time.time()

        while time.time() - start_time < timeout:
            ret = proc.poll()
            out_line = proc.stdout.readline() if proc.stdout else ""
            err_line = proc.stderr.readline() if proc.stderr else ""
            line = (out_line or err_line).strip()
            if line:
                lines.append(line)
                m = re.search(r'https://playit\.gg/claim/(\S+)', line)
                if m:
                    claim_url = m.group(0)
                    break
                m = re.search(r'claim[:\s]+(https://[^\s]+)', line)
                if m:
                    claim_url = m.group(1)
                    break
                m = re.search(r'public[\s:]+(\d+\.\d+\.\d+\.\d+)[:\s](\d+)', line.lower())
                if m:
                    return True, {"ip": m.group(1), "port": m.group(2), "lines": lines}
                if "already running" in line.lower():
                    return True, {"message": "Already running.", "lines": lines}
            if ret is not None and not out_line and not err_line:
                break
            time.sleep(0.3)

        proc.kill()
        proc.wait(timeout=5)

        if claim_url:
            return True, {"claim": claim_url, "lines": lines}
        if lines:
            return True, {"message": "Output captured", "lines": lines}
        return True, {"message": "Started. Run again in a few seconds.", "lines": lines}

    except FileNotFoundError:
        return False, {"error": "Playit-cli not found."}
    except Exception as e:
        return False, {"error": str(e)}


def check_tunnel_status():
    if not is_installed():
        return {"installed": False, "claimed": False, "running": False}

    result = {
        "installed": True,
        "claimed": is_claimed(),
        "version": get_version(),
        "daemon_running": _is_daemon_running(),
    }

    if not result["daemon_running"]:
        result["running"] = False
        return result

    try:
        out = subprocess.check_output(
            [PLAYIT_CLI, "status"], text=True, timeout=10,
            stderr=subprocess.STDOUT,
        )
        result["running"] = "running" in out.lower() or "active" in out.lower()
        for line in out.splitlines():
            m = re.search(r'(\d+\.\d+\.\d+\.\d+):(\d+)', line)
            if m:
                result["public_ip"] = m.group(1)
                result["public_port"] = int(m.group(2))
                result["running"] = True
    except subprocess.CalledProcessError:
        result["running"] = False
    except FileNotFoundError:
        result["installed"] = False
    except Exception:
        result["running"] = False

    return result
