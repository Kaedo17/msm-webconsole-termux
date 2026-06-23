"""Utility helpers for the Minecraft web console."""

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
