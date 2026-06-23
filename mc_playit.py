"""Playit.gg tunnel for Termux.

On Termux, playit is installed via 'pkg install playit' which provides
playit (combined binary), playitd (daemon), and playit-cli (client).
The claim URL appears on first run of ANY of these.  We try each in
order and capture all output.
"""

import os
import re
import shutil
import subprocess
import threading
import time
from pathlib import Path

# Try all possible binary names
_PLAYIT = shutil.which("playit") or ""
_PLAYITD = shutil.which("playitd") or ""
_PLAYIT_CLI = shutil.which("playit-cli") or ""
_PLAYIT_SECRET = Path.home() / ".playit" / "secret"


def is_installed():
    return bool(_PLAYIT) or bool(_PLAYIT_CLI)


def install_commands():
    return ["pkg install tur-repo -y", "pkg install playit -y"]


def get_version():
    for bin in (_PLAYIT, _PLAYIT_CLI):
        if bin:
            try:
                out = subprocess.check_output([bin, "--version"], text=True, timeout=10, stderr=subprocess.STDOUT)
                return out.strip()
            except Exception:
                continue
    return ""


def is_claimed():
    return _PLAYIT_SECRET.exists()


def _capture_output(cmd, timeout=25):
    """Run a command and capture all output (stdout+stderr). Returns (ok, output_str, lines)."""
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


def _find_claim_url(lines):
    """Search all lines for a claim URL."""
    for line in lines:
        m = re.search(r'(https://playit\.gg/(?:claim|account|tunnel)/\S+)', line)
        if m:
            return m.group(1)
        m = re.search(r'(https://[^\s]+playit[^\s]+\S+)', line.lower())
        if m:
            return m.group(1)
    return None


def start_tunnel(timeout=30):
    if not is_installed():
        return False, {"error": "Playit not installed"}

    # Ensure daemon runs (capture output in case claim URL appears there)
    if is_claimed():
        if _PLAYITD:
            subprocess.Popen([_PLAYITD], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL)
        return True, {"message": "Already claimed. Tunnel should be running."}

    all_raw = []
    claim_url = None

    # Step 1: Start playitd — daemon generates the secret + claim URL
    if _PLAYITD:
        ok, out, lines = _capture_output([_PLAYITD], timeout=10)
        all_raw.append(("playitd", out, lines))
        claim_url = _find_claim_url(lines)
        if claim_url:
            return True, {"claim": claim_url, "lines": lines, "raw": all_raw}
        # Keep daemon running — it's needed for playit-cli
        subprocess.Popen([_PLAYITD], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL)
    else:
        all_raw.append(("playitd", "", ["playitd not found"]))

    # Step 2: Try playit-cli (connects to the now-running daemon)
    if _PLAYIT_CLI:
        ok, out, lines = _capture_output([_PLAYIT_CLI], timeout=timeout)
        all_raw.append(("playit-cli", out, lines))
        claim_url = _find_claim_url(lines)
        if claim_url:
            return True, {"claim": claim_url, "lines": lines, "raw": all_raw}

    # Step 3: Try main 'playit' binary as last resort
    if _PLAYIT:
        ok, out, lines = _capture_output([_PLAYIT], timeout=10)
        all_raw.append(("playit", out, lines))
        claim_url = _find_claim_url(lines)
        if claim_url:
            return True, {"claim": claim_url, "lines": lines, "raw": all_raw}

    # No claim URL — return everything
    formatted = []
    for name, out, lines in all_raw:
        formatted.append(f">>> {name} ({len(lines)} lines)")
        for l in lines[-20:]:
            formatted.append(f"  {l}")
    return True, {
        "lines": formatted,
        "raw": "\n".join(f">>> {n}\n{o}" for n, o, _ in all_raw),
        "message": "Could not auto-detect claim URL. Use the manual link below.",
    }


def check_tunnel_status():
    if not is_installed():
        return {"installed": False, "claimed": False, "running": False}

    # Check if playitd is running
    daemon_running = False
    for name in ("playitd", "playit", "playit-cli"):
        try:
            subprocess.run(["pgrep", "-x", name], capture_output=True, timeout=3, check=True)
            daemon_running = True
            break
        except Exception:
            continue

    result = {
        "installed": True,
        "claimed": is_claimed(),
        "version": get_version(),
        "daemon_running": daemon_running,
        "running": False,
    }

    if not daemon_running:
        return result

    # Try 'playit status' or 'playit-cli status'
    for bin_name, bin_path in (("playit", _PLAYIT), ("playit-cli", _PLAYIT_CLI)):
        if not bin_path:
            continue
        try:
            proc = subprocess.Popen(
                [bin_path, "status"],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                stdin=subprocess.DEVNULL, text=True,
            )
            out, _ = proc.communicate(timeout=10)
            out = (out or "").lower()
            result["running"] = "running" in out or "active" in out
            for line in out.splitlines():
                m = re.search(r'(\d+\.\d+\.\d+\.\d+):(\d+)', line)
                if m:
                    result["public_ip"] = m.group(1)
                    result["public_port"] = int(m.group(2))
                    result["running"] = True
            if result.get("status_output"):
                result["status_output"] += "\n" + out
            else:
                result["status_output"] = out
            if result["running"]:
                break
        except Exception:
            continue

    return result
