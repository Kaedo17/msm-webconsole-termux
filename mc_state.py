"""Shared state and config for the Minecraft web console.

Multi-server: each server instance is managed by mc_instances.py.
This module holds web-app-level config only.
"""

import json
import os
import shutil
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
HOST = os.environ.get("HOST", "0.0.0.0")
PORT = int(os.environ.get("PORT", 5000))
JAVA_BIN = shutil.which("java") or "java"
CONSOLE_MAX = 500
CONFIG_FILE = SCRIPT_DIR / "webconsole_config.json"

# ── Global settings (loaded from config file) ──

_config_cache = None


def load_config():
    """Load the webconsole config JSON file (cached)."""
    global _config_cache
    if _config_cache is not None:
        return _config_cache
    try:
        if CONFIG_FILE.exists():
            with open(CONFIG_FILE, "r") as f:
                _config_cache = json.load(f)
        else:
            _config_cache = {}
    except Exception:
        _config_cache = {}
    return _config_cache


def save_config(data):
    """Save a dict to the config file and update the cache."""
    global _config_cache
    try:
        CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(CONFIG_FILE, "w") as f:
            json.dump(data, f, indent=2)
        _config_cache = data
        return True
    except Exception as e:
        _config_cache = None
        return False


def get_cf_api_key():
    """Return the CurseForge API key from config (or empty string)."""
    cfg = load_config()
    return cfg.get("curseforge_api_key", "")


def clear_config_cache():
    """Force the next load_config() call to re-read from disk."""
    global _config_cache
    _config_cache = None
