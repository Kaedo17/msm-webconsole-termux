"""Utility helpers for the Minecraft web console.

IMPORTANT: Always reference mutable state as ``mc_state.xxx`` rather than
``from mc_state import xxx`` — this ensures you see the latest value
when ``mc_server`` reassigns ``server_proc``, ``console_history``, etc.
"""

import subprocess
from pathlib import Path

from flask import jsonify, request

import mc_state

# ── API response helpers ─────────────────────────────────────────────

def ok(data):
    return jsonify({"ok": True, **data})

def fail(msg, code=400):
    return jsonify({"ok": False, "error": msg}), code

def parse_json_body():
    return request.get_json(silent=True) or {}

# ── Server state checks ──────────────────────────────────────────────

def is_running():
    sp = mc_state.server_proc
    return sp is not None and sp.poll() is None

def safe_resolve(path_str):
    target = (mc_state.SERVER_DIR / path_str).resolve()
    if not str(target).startswith(str(mc_state.SERVER_DIR.resolve())):
        return None
    return target

# ── File helpers ─────────────────────────────────────────────────────

def find_jar():
    jar = mc_state.SERVER_DIR / mc_state.JAR_NAME
    if jar.exists():
        return jar
    for f in sorted(mc_state.SERVER_DIR.glob("*.jar")):
        return f
    return None

def check_eula():
    eula = mc_state.SERVER_DIR / "eula.txt"
    if not eula.exists():
        eula.write_text("eula=false\n")
        return False
    return "eula=true" in eula.read_text().strip()

def get_props():
    pf = mc_state.SERVER_DIR / "server.properties"
    if not pf.exists():
        return {}
    props = {}
    for line in pf.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, _, v = line.partition("=")
            props[k.strip()] = v.strip()
    return props

# ── Process info helpers ─────────────────────────────────────────────

def get_proc_mem(pid):
    try:
        out = subprocess.check_output(["ps", "-o", "rss=", "-p", str(pid)], text=True).strip()
        return round(int(out) / 1024, 1) if out else 0
    except Exception:
        return 0

def get_uptime(pid):
    try:
        out = subprocess.check_output(["ps", "-o", "etime=", "-p", str(pid)], text=True).strip()
        return out
    except Exception:
        return ""
