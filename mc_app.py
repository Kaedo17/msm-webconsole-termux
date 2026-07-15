"""Desktop launcher for Minecraft Web Manager — PC browser mode.

Self-contained PC launcher. Handles Flask setup, starts the web server,
and opens your browser. No Termux dependencies.

Usage:
    python mc_app.py                          # Launch with auto port
    python mc_app.py --port 8080              # Custom port
    python mc_app.py --host 0.0.0.0           # Access from other devices on LAN
    python mc_app.py --data-dir "C:/my-servers"  # Custom data directory
    python mc_app.py --no-browser             # Don't auto-open browser
"""

import argparse
import os
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path


# ═══════════════════════════════════════════════════════════════════════
#  Flask setup — handle this first, before importing webconsole
# ═══════════════════════════════════════════════════════════════════════

def _ensure_flask():
    """Make sure Flask is installed before importing webconsole."""
    try:
        import flask  # noqa: F401
        return True
    except ImportError:
        pass

    print(" Flask is required but not installed.")
    print(" Installing Flask via pip...")
    try:
        subprocess.check_call(
            [sys.executable, "-m", "pip", "install", "flask"],
            timeout=120,
        )
        # Verify installation
        import flask  # noqa: F401
        print(" Flask installed successfully.")
        return True
    except subprocess.TimeoutExpired:
        print(" ERROR: pip install timed out.")
        print(" Try running: python -m pip install flask")
        return False
    except subprocess.CalledProcessError as e:
        print(f" ERROR: pip install failed: {e}")
        print(" Try running: python -m pip install flask")
        return False
    except Exception as e:
        print(f" ERROR: {e}")
        print(" Try running: python -m pip install flask")
        return False


# ═══════════════════════════════════════════════════════════════════════
#  Data directory
# ═══════════════════════════════════════════════════════════════════════

def get_default_data_dir():
    """Return the default data directory for the app.

    When running as a packaged EXE: a 'data' folder next to the EXE.
    When running as a script: a 'data' folder in the current directory.
    """
    if getattr(sys, "frozen", False):
        exe_dir = Path(sys.executable).resolve().parent
        return exe_dir / "data"
    else:
        return Path.cwd() / "data"


# ═══════════════════════════════════════════════════════════════════════
#  Port management
# ═══════════════════════════════════════════════════════════════════════

def find_free_port(start=5000, max_attempts=50):
    """Find a free TCP port starting from `start`."""
    for port in range(start, start + max_attempts):
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.bind(("127.0.0.1", port))
            s.close()
            return port
        except OSError:
            continue
    return start  # give up, let Flask handle the error


# ═══════════════════════════════════════════════════════════════════════
#  Main
# ═══════════════════════════════════════════════════════════════════════

def main():
    ap = argparse.ArgumentParser(description="Minecraft Web Manager — PC")
    ap.add_argument("--host", type=str, default="127.0.0.1",
                    help="Bind address (default: 127.0.0.1). Use 0.0.0.0 to allow "
                         "access from other devices on your LAN.")
    ap.add_argument("--port", type=int, default=0,
                    help="Web UI port (default: auto, starts from 5000)")
    ap.add_argument("--data-dir", type=str, default=None,
                    help="Data directory (default: 'data' folder next to this script)")
    ap.add_argument("--no-browser", action="store_true",
                    help="Don't auto-open browser on start")
    args = ap.parse_args()

    # Ensure Flask is available before importing webconsole
    if not _ensure_flask():
        sys.exit(1)

    # Data directory
    data_dir = Path(args.data_dir).resolve() if args.data_dir else get_default_data_dir()
    data_dir.mkdir(parents=True, exist_ok=True)

    # Port
    port = args.port if args.port else find_free_port(5000)
    host = args.host

    # Configure server storage to use the app data directory
    import mc_instances as mci
    servers_dir = data_dir / "servers"
    registry_path = data_dir / "servers.json"
    servers_dir.mkdir(parents=True, exist_ok=True)
    mci.SERVERS_BASE = servers_dir
    mci.REGISTRY_PATH = registry_path
    mci.load_registry()

    # Print status
    print(f" Minecraft Web Manager")
    print(f"  Data directory:  {data_dir}")
    print(f"  Servers:         {servers_dir}")
    print(f"  Web URL:         http://{host}:{port}")

    if not mci.all_servers():
        print(f"  No servers yet — create one from the web UI.")

    # Auto-open browser after a short delay
    if not args.no_browser:
        def _open_browser():
            time.sleep(1.5)
            try:
                import webbrowser
                webbrowser.open(f"http://localhost:{port}")
            except Exception:
                pass
        threading.Thread(target=_open_browser, daemon=True).start()

    # Start Flask
    from webconsole import app
    try:
        app.run(host=host, port=port, debug=False, use_reloader=False, threaded=True)
    except KeyboardInterrupt:
        pass

    print("  Shutting down.")


if __name__ == "__main__":
    main()
