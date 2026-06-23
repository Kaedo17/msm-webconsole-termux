"""Playit.gg tunnel integration for exposing Minecraft servers to the internet.

Checks if playit-cli is installed, provides install instructions, runs the
tunnel, extracts the claim URL, and monitors tunnel status.
"""

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
        out = subprocess.check_output([PLAYIT_BIN, "--version"], text=True, timeout=10, stderr=subprocess.STDOUT)
        return out.strip()
    except Exception:
        return ""


def is_claimed():
    return PLAYIT_SECRET.exists()


def start_tunnel(timeout=15):
    """Start playit-cli and capture claim URL or tunnel info.
    Returns (success, result_string)."""
    if not is_installed():
        return False, "Playit not installed."

    try:
        proc = subprocess.Popen(
            [PLAYIT_BIN],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            stdin=subprocess.PIPE,
            text=True,
        )

        lines = []
        claim_url = None
        tunnel_ip = None
        tunnel_port = None

        for _ in range(timeout):
            try:
                line = proc.stdout.readline()
                if not line:
                    break
                line = line.strip()
                lines.append(line)

                m = re.search(r'https://playit\.gg/claim/(\S+)', line)
                if m:
                    claim_url = m.group(0)

                m = re.search(r'Public:\s*(\d+\.\d+\.\d+\.\d+):(\d+)', line)
                if m:
                    tunnel_ip = m.group(1)
                    tunnel_port = m.group(2)

                if tunnel_ip and claim_url:
                    break

                if "tunnel ready" in line.lower() and not claim_url:
                    break
            except Exception:
                break
            time.sleep(0.5)

        if claim_url:
            return True, jsonify_result(claim=claim_url, lines=lines)

        if tunnel_ip:
            return True, jsonify_result(ip=tunnel_ip, port=tunnel_port, lines=lines)

        # Check process status
        proc.poll()
        if proc.returncode is not None:
            output = "\n".join(lines)
            if "already running" in output.lower():
                return True, jsonify_result(message="Tunnel already running (previous session)", lines=lines)
            return False, f"Playit exited: {output}"

        return True, jsonify_result(message="Started, waiting for claim or tunnel info", lines=lines)

    except FileNotFoundError:
        return False, "Playit not found."
    except Exception as e:
        return False, str(e)


def check_tunnel_status():
    """Check if playit tunnel is currently running."""
    if not is_installed():
        return {"installed": False, "claimed": False, "running": False}

    result = {
        "installed": True,
        "claimed": is_claimed(),
        "version": get_version(),
    }

    try:
        out = subprocess.check_output(
            [PLAYIT_BIN, "status"],
            text=True, timeout=10, stderr=subprocess.STDOUT,
        )
        result["running"] = "running" in out.lower() or "active" in out.lower()
        for line in out.splitlines():
            m = re.search(r'(\d+\.\d+\.\d+\.\d+):(\d+)', line)
            if m:
                result["public_ip"] = m.group(1)
                result["public_port"] = int(m.group(2))
    except subprocess.CalledProcessError:
        result["running"] = False
    except FileNotFoundError:
        result["installed"] = False
    except Exception:
        result["running"] = False

    return result


def jsonify_result(**kwargs):
    return kwargs
