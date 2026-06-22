"""Minecraft server process management — start, stop, restart, console reader."""

import os
import shlex
import shutil
import subprocess
import threading
import time
from datetime import datetime, timezone

import mc_state
from mc_helpers import is_running, find_jar, check_eula, get_proc_mem, get_uptime


def server_reader(proc):
    try:
        for line in iter(proc.stdout.readline, ""):
            line = line.rstrip("\n\r")
            if not line:
                continue
            mc_state.console_history.append(line)
            mc_state.console_queue.put(line)
            if len(mc_state.console_history) > mc_state.CONSOLE_MAX:
                mc_state.console_history.pop(0)
            if "]:" in line and "joined the game" in line:
                with mc_state.get_status_lock():
                    name = line.split("]:")[-1].strip().split(" ")[0].strip()
                    if name and name not in mc_state.status_cache["players"]:
                        mc_state.status_cache["players"].append(name)
            if "]:" in line and "left the game" in line:
                with mc_state.get_status_lock():
                    name = line.split("]:")[-1].strip().split(" ")[0].strip()
                    if name in mc_state.status_cache["players"]:
                        mc_state.status_cache["players"].remove(name)
    except Exception as e:
        msg = f"[WebConsole] Reader error: {e}"
        mc_state.console_history.append(msg)
        mc_state.console_queue.put(msg)


def poll_status():
    while True:
        with mc_state.get_status_lock():
            running = is_running()
            mc_state.status_cache["online"] = running
            if running and mc_state.server_proc:
                pid = mc_state.server_proc.pid
                mc_state.status_cache["mem_mb"] = get_proc_mem(pid)
                mc_state.status_cache["uptime"] = get_uptime(pid)
            else:
                mc_state.status_cache["players"] = []
                mc_state.status_cache["mem_mb"] = 0
                mc_state.status_cache["uptime"] = ""
        time.sleep(3)


def start_polling():
    t = threading.Thread(target=poll_status, daemon=True)
    t.start()


def _load_env():
    env = os.environ.copy()
    env["TERM"] = "dumb"
    return env


def _make_java_cmd(jar):
    return [
        str(mc_state.JAVA_BIN),
        f"-Xms{mc_state.MIN_RAM}", f"-Xmx{mc_state.MAX_RAM}",
        "-Djline.terminal=jline.UnsupportedTerminal",
        "-jar", str(jar), "--nogui",
    ]


def start_minecraft():
    if is_running():
        return False, "Server already running."
    jar = find_jar()
    if not jar:
        return False, "No server jar found."
    if not check_eula():
        return False, "EULA not accepted. Edit eula.txt and set eula=true."

    env = _load_env()

    if not (mc_state.SERVER_DIR / "server.properties").exists():
        subprocess.run(
            _make_java_cmd(jar),
            cwd=str(mc_state.SERVER_DIR), capture_output=True, timeout=20, env=env)

    java_cmd = _make_java_cmd(jar)
    script_bin = shutil.which("script")
    if script_bin:
        cmd_str = shlex.join(java_cmd) if hasattr(shlex, 'join') else " ".join(shlex.quote(x) for x in java_cmd)
        cmd = [script_bin, "-q", "-c", cmd_str, "/dev/null"]
    else:
        cmd = java_cmd

    proc = subprocess.Popen(cmd, cwd=str(mc_state.SERVER_DIR),
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            stdin=subprocess.PIPE, text=True, bufsize=1, env=env)
    mc_state.server_proc = proc
    threading.Thread(target=server_reader, args=(proc,), daemon=True).start()
    with mc_state.get_status_lock():
        mc_state.status_cache["started_at"] = datetime.now(timezone.utc).isoformat()
        mc_state.status_cache["online"] = True
    return True, "Server started."


def stop_minecraft(seconds=15):
    if not is_running():
        return False, "Server not running."
    proc = mc_state.server_proc
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
    mc_state.server_proc = None
    with mc_state.get_status_lock():
        mc_state.status_cache["online"] = False
    return True, "Server stopped."


def send_minecraft(cmd):
    if not is_running():
        return False, "Server not running."
    try:
        mc_state.server_proc.stdin.write(cmd + "\n")
        mc_state.server_proc.stdin.flush()
        return True, "Command sent."
    except Exception as e:
        return False, str(e)
