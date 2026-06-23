"""Playit.gg tunnel for Termux: playitd daemon + playit-cli client."""

import os
import re
import shutil
import subprocess
import threading
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
        out = subprocess.check_output([PLAYIT_CLI, "--version"], text=True, timeout=10, stderr=subprocess.STDOUT)
        return out.strip()
    except Exception:
        return ""


def is_claimed():
    return PLAYIT_SECRET.exists()


def _ensure_daemon():
    """Ensure playitd daemon is running. Returns (ok, msg)."""
    if not PLAYITD:
        return False, "playitd binary not found."
    try:
        subprocess.run(["pgrep", "-x", "playitd"], capture_output=True, timeout=3)
        return True, "daemon already running"
    except subprocess.TimeoutExpired:
        pass
    except Exception:
        pass
    try:
        subprocess.Popen([PLAYITD], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL)
        for _ in range(10):
            time.sleep(1)
            try:
                subprocess.run(["pgrep", "-x", "playitd"], capture_output=True, timeout=3, check=True)
                return True, "daemon started"
            except Exception:
                continue
        return True, "daemon launch attempted"
    except Exception as e:
        return False, str(e)


def _check_daemon():
    """Check if playitd is running."""
    if not PLAYITD:
        return False
    try:
        subprocess.run(["pgrep", "-x", "playitd"], capture_output=True, timeout=3, check=True)
        return True
    except Exception:
        return False


def run_playit_cli(args=None, timeout=25):
    """Run playit-cli, capture ALL output (stdout+stderr). Returns (ok, output_str, lines)."""
    if not is_installed():
        return False, "playit-cli not found", []
    cmd = [PLAYIT_CLI] + (args or [])
    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            stdin=subprocess.DEVNULL, text=True, bufsize=1,
        )
        collected = []
        done = threading.Event()

        def read_all():
            for line in iter(proc.stdout.readline, ""):
                collected.append(line)
            for line in iter(proc.stderr.readline, ""):
                collected.append(line)
            done.set()

        thr = threading.Thread(target=read_all, daemon=True)
        thr.start()
        thr.join(timeout=timeout)

        proc.kill()
        proc.wait(timeout=5)

        lines = [l.rstrip("\n\r") for l in collected]
        out = "\n".join(lines)
        return True, out, lines
    except Exception as e:
        return False, str(e), []


def start_tunnel(timeout=30):
    if not is_installed():
        return False, {"error": "Playit not installed"}

    ok, msg = _ensure_daemon()
    lines_so_far = [f"[daemon] {msg}"]

    if is_claimed():
        return True, {"message": "Already claimed. Tunnel should be running.", "lines": lines_so_far}

    ok, out, lines = run_playit_cli(timeout=timeout)
    all_lines = lines_so_far + lines

    claim_url = None
    for line in all_lines:
        low = line.lower()
        m = re.search(r'(https?://playit\.gg/\S+)', line)
        if m:
            claim_url = m.group(1)
            break
        m = re.search(r'(https?://[^\s]+claim\S+)', low)
        if m:
            claim_url = m.group(1)
            break
        m = re.search(r'claim[:\s]+(https?://[^\s]+)', line)
        if m:
            claim_url = m.group(1)
            break

    if claim_url:
        return True, {"claim": claim_url, "lines": all_lines}

    if all_lines:
        return True, {"message": "Output captured", "lines": all_lines, "raw": out}

    return True, {"message": "No output from playit-cli. Wait and try again.", "lines": all_lines}


def check_tunnel_status():
    if not is_installed():
        return {"installed": False, "claimed": False, "running": False}

    daemon_running = _check_daemon()
    result = {
        "installed": True,
        "claimed": is_claimed(),
        "version": get_version(),
        "daemon_running": daemon_running,
        "running": False,
    }

    if not daemon_running:
        return result

    ok, out, lines = run_playit_cli(["status"], timeout=10)
    result["running"] = "running" in out.lower() or "active" in out.lower()
    for line in lines:
        m = re.search(r'(\d+\.\d+\.\d+\.\d+):(\d+)', line)
        if m:
            result["public_ip"] = m.group(1)
            result["public_port"] = int(m.group(2))
            result["running"] = True
    if lines:
        result["status_output"] = "\n".join(lines)

    return result
