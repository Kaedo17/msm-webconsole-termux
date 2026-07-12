"""Utility helpers for the Minecraft web console."""

import threading
import time
import uuid
from pathlib import Path

from flask import jsonify, request  # type: ignore

import mc_state


def ok(data):
    return jsonify({"ok": True, **data})


def fail(msg, code=400):
    return jsonify({"ok": False, "error": msg}), code


def parse_json_body():
    return request.get_json(silent=True) or {}


def safe_resolve(server_dir, path_str):
    target = (server_dir / path_str).resolve()
    if not str(target).startswith(str(server_dir.resolve())):
        return None
    return target


def get_props(server_dir):
    pf = server_dir / "server.properties"
    if not pf.exists():
        return {}
    props = {}
    for line in pf.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, _, v = line.partition("=")
            props[k.strip()] = v.strip()
    return props


# ═══════════════════════════════════════════════════════════════════════
#  Progress tracker — for modpack installs and other long operations
# ═══════════════════════════════════════════════════════════════════════

_progress_tracker = {}
_progress_lock = threading.Lock()


def create_progress():
    """Create a new progress entry and return its ID."""
    tid = uuid.uuid4().hex[:12]
    with _progress_lock:
        _progress_tracker[tid] = {
            "status": "starting",
            "phase": "",
            "current": 0,
            "total": 0,
            "message": "",
            "done": False,
            "error": None,
        }
    return tid


def update_progress(tid, **kwargs):
    """Update progress fields for a task ID."""
    with _progress_lock:
        entry = _progress_tracker.get(tid)
        if entry:
            entry.update(kwargs)


def get_progress(tid):
    """Get current progress for a task ID."""
    with _progress_lock:
        entry = _progress_tracker.get(tid)
        if entry:
            return dict(entry)
    return None


def clear_progress(tid):
    """Remove a progress entry."""
    with _progress_lock:
        _progress_tracker.pop(tid, None)
