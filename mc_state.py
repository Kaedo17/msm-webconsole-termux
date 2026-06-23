"""Shared state and config for the Minecraft web console.

Multi-server: each server instance is managed by mc_instances.py.
This module holds web-app-level config only.
"""

import os
import shutil
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
HOST = os.environ.get("HOST", "0.0.0.0")
PORT = int(os.environ.get("PORT", 5000))
JAVA_BIN = shutil.which("java") or "java"
CONSOLE_MAX = 500
