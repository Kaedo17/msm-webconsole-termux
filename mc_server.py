"""Minecraft server process management for multi-server instances."""

import os
import queue
import shlex
import shutil
import subprocess
import threading
import time
from datetime import datetime, timezone

import mc_state


def _reader_thread(inst):
    try:
        proc = inst.proc
        for line in iter(proc.stdout.readline, ""):
            line = line.rstrip("\n\r")
            if not line:
                continue
            inst.console_history.append(line)
            inst.console_queue.put(line)
            if len(inst.console_history) > mc_state.CONSOLE_MAX:
                inst.console_history.pop(0)
            if "]:" in line and "joined the game" in line:
                with inst.lock:
                    name = line.split("]:")[-1].strip().split(" ")[0].strip()
                    if name and name not in inst.status_cache["players"]:
                        inst.status_cache["players"].append(name)
            if "]:" in line and "left the game" in line:
                with inst.lock:
                    name = line.split("]:")[-1].strip().split(" ")[0].strip()
                    if name in inst.status_cache["players"]:
                        inst.status_cache["players"].remove(name)
    except Exception as e:
        msg = f"[WebConsole] Reader error: {e}"
        inst.console_history.append(msg)
        inst.console_queue.put(msg)


def _poll_thread(inst):
    while True:
        try:
            if inst.is_running() and inst.proc:
                pid = inst.proc.pid
                with inst.lock:
                    inst.status_cache["online"] = True
                    inst.status_cache["mem_mb"] = _get_proc_mem(pid)
                    inst.status_cache["uptime"] = _get_uptime(pid)
            else:
                with inst.lock:
                    if inst.status_cache["online"]:
                        inst.status_cache["online"] = False
                    if not inst.is_running():
                        inst.status_cache["players"] = []
                        inst.status_cache["mem_mb"] = 0
                        inst.status_cache["uptime"] = ""
        except Exception:
            pass
        time.sleep(2)


def _get_proc_mem(pid):
    try:
        out = subprocess.check_output(["ps", "-o", "rss=", "-p", str(pid)], text=True).strip()
        return round(int(out) / 1024, 1) if out else 0
    except Exception:
        return 0


def _get_uptime(pid):
    try:
        out = subprocess.check_output(["ps", "-o", "etime=", "-p", str(pid)], text=True).strip()
        return out
    except Exception:
        return ""


def _load_env():
    env = os.environ.copy()
    env["TERM"] = "dumb"
    return env


def _find_jar(inst):
    for f in sorted(inst.dir.glob("*.jar")):
        fname = f.name.lower()
        if "installer" in fname or "cli" in fname:
            continue
        return f
    return None


def _check_eula(inst):
    eula = inst.dir / "eula.txt"
    if not eula.exists():
        eula.write_text("eula=false\n")
        return False
    return "eula=true" in eula.read_text().strip()


def _make_java_cmd(inst, jar):
    return [
        str(mc_state.JAVA_BIN),
        f"-Xms{inst.min_ram}", f"-Xmx{inst.max_ram}",
        "-Djline.terminal=jline.UnsupportedTerminal",
        "-jar", str(jar), "--nogui",
    ]


def start_server(inst):
    if inst.is_running():
        return False, "Server already running."
    jar = _find_jar(inst)
    if not jar:
        return False, "No server jar found."
    if not _check_eula(inst):
        return False, "EULA not accepted. Edit eula.txt and set eula=true."

    env = _load_env()
    java_cmd = _make_java_cmd(inst, jar)
    script_bin = shutil.which("script")
    if script_bin:
        cmd_str = shlex.join(java_cmd) if hasattr(shlex, 'join') else " ".join(shlex.quote(x) for x in java_cmd)
        cmd = [script_bin, "-q", "-c", cmd_str, "/dev/null"]
    else:
        cmd = java_cmd

    proc = subprocess.Popen(cmd, cwd=str(inst.dir),
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            stdin=subprocess.PIPE, text=True, bufsize=1, env=env)
    inst.proc = proc
    t = threading.Thread(target=_reader_thread, args=(inst,), daemon=True)
    t.start()
    inst._reader_thread = t
    if inst._poll_thread is None or not inst._poll_thread.is_alive():
        pt = threading.Thread(target=_poll_thread, args=(inst,), daemon=True)
        pt.start()
        inst._poll_thread = pt
    with inst.lock:
        inst.status_cache["started_at"] = datetime.now(timezone.utc).isoformat()
        inst.status_cache["online"] = True
    return True, "Server started."


def stop_server(inst, seconds=15):
    if not inst.is_running():
        return False, "Server not running."
    proc = inst.proc
    for i in range(seconds, 0, -5):
        try:
            proc.stdin.write(f"say \xa7cServer shutdown in {i}s...\n")
            proc.stdin.flush()
            time.sleep(min(5, i))
        except Exception:
            break
    try:
        proc.stdin.write("stop\n")
        proc.stdin.flush()
    except Exception:
        pass
    try:
        proc.wait(timeout=30)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait()
    inst.proc = None
    with inst.lock:
        inst.status_cache["online"] = False
    return True, "Server stopped."


def send_server(inst, cmd):
    if not inst.is_running():
        return False, "Server not running."
    try:
        inst.proc.stdin.write(cmd + "\n")
        inst.proc.stdin.flush()
        return True, "Command sent."
    except Exception as e:
        return False, str(e)
