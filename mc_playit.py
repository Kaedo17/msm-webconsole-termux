"""Playit.gg tunnel integration for exposing Minecraft servers to the internet."""

import os
import re
import shutil
import subprocess
import threading
import time
from pathlib import Path

PLAYIT_BIN = shutil.which("playit") or shutil.which("playit-cli") or ""
PLAYIT_SECRET = Path.home() / ".playit" / "secret"


def is_installed():
    return bool(PLAYIT_BIN) and os.access(PLAYIT_BIN, os.X_OK)


def install_commands():
    return [
        "pkg install tur-repo -y",
        "pkg install playit -y",
    ]


def get_version():
    if not is_installed():
        return ""
    try:
        out = subprocess.check_output([PLAYIT_BIN, "--version"], text=True, timeout=10, stderr=subprocess.PIPE)
        return out.strip()
    except Exception:
        return ""


def is_claimed():
    return PLAYIT_SECRET.exists()


def start_tunnel(timeout=30):
    """Start playit-cli, capture claim URL or tunnel info.
    Returns (success, result_dict)."""
    if not is_installed():
        return False, {"error": "Playit not installed."}

    if is_claimed():
        try:
            proc = subprocess.Popen(
                [PLAYIT_BIN],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                stdin=subprocess.DEVNULL, text=True,
            )
            return True, {"message": "Tunnel was already claimed. Check tunnel page.", "proc_pid": proc.pid}
        except Exception as e:
            return False, {"error": str(e)}

    try:
        proc = subprocess.Popen(
            [PLAYIT_BIN],
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
                line_lower = line.lower()
                m = re.search(r'https://playit\.gg/claim/(\S+)', line)
                if m:
                    claim_url = m.group(0)
                    break
                m = re.search(r'claim\s*(?:url|this|at)?\s*:?\s*(https://[^\s]+)', line)
                if m:
                    claim_url = m.group(1)
                    break
                m = re.search(r'public[:\s]+(\d+\.\d+\.\d+\.\d+)[:\s](\d+)', line_lower)
                if m:
                    return True, {"ip": m.group(1), "port": m.group(2), "lines": lines}
                if "already running" in line_lower:
                    return True, {"message": "Tunnel already running.", "lines": lines}
            if ret is not None and not out_line and not err_line:
                break
            time.sleep(0.3)

        proc.kill()
        proc.wait(timeout=5)

        if claim_url:
            return True, {"claim": claim_url, "lines": lines}

        if lines:
            return True, {"message": "Tunnel output captured", "lines": lines, "claimed": is_claimed()}

        return True, {"message": "Tunnel started (no output yet). Run again in a few seconds.", "lines": lines}

    except FileNotFoundError:
        return False, {"error": "Playit not found."}
    except Exception as e:
        return False, {"error": str(e)}


def check_tunnel_status():
    if not is_installed():
        return {"installed": False, "claimed": False, "running": False}

    result = {
        "installed": True,
        "claimed": is_claimed(),
        "version": get_version(),
    }

    try:
        out = subprocess.check_output(
            [PLAYIT_BIN, "status"], text=True, timeout=10,
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
