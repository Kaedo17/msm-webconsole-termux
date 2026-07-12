"""Desktop application launcher for Minecraft Web Manager.

Uses PyWebView to embed the web UI in a native window — no browser needed.
Data is stored in a "data" folder next to the EXE for easy access.

Usage:
    python mc_app.py                     # Launch desktop app
    python mc_app.py --port 8080         # Use a custom port
    python mc_app.py --data-dir "C:/my-servers"  # Custom data directory
"""

import argparse
import os
import socket
import sys
import threading
import time
from pathlib import Path


# ═══════════════════════════════════════════════════════════════════════
#  Data directory
# ═══════════════════════════════════════════════════════════════════════

def get_default_data_dir():
    """Return the default data directory for the app.

    When running as a packaged EXE: a "data" folder next to the EXE.
    When running as a script: a "data" folder in the current directory.
    """
    if getattr(sys, "frozen", False):
        # Packaged EXE — use the EXE's own directory
        exe_dir = Path(sys.executable).resolve().parent
        return exe_dir / "data"
    else:
        # Running as script — use the current working directory
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
#  Flask server thread
# ═══════════════════════════════════════════════════════════════════════

def start_flask(data_dir, port):
    """Configure paths and start Flask in the current thread (blocking)."""
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
    print(f"  Web port:        {port}")

    if not mci.all_servers():
        print(f"  No servers yet — create one from the app UI.")

    # Start Flask
    from webconsole import app
    app.run(host="127.0.0.1", port=port, debug=False, use_reloader=False)


# ═══════════════════════════════════════════════════════════════════════
#  Main
# ═══════════════════════════════════════════════════════════════════════

def main():
    ap = argparse.ArgumentParser(description="Minecraft Web Manager — Desktop App")
    ap.add_argument("--port", type=int, default=0, help="Web UI port (default: auto)")
    ap.add_argument("--data-dir", type=str, default=None, help="Data directory (default: 'data' folder next to the EXE)")
    args = ap.parse_args()

    # Data directory
    data_dir = Path(args.data_dir).resolve() if args.data_dir else get_default_data_dir()
    data_dir.mkdir(parents=True, exist_ok=True)

    # Port
    port = args.port if args.port else find_free_port(5000)

    # Start Flask in a background thread
    flask_thread = threading.Thread(
        target=start_flask,
        args=(data_dir, port),
        daemon=True,
    )
    flask_thread.start()
    time.sleep(1.5)  # Give Flask a moment to start

    # Open native window with PyWebView
    try:
        import webview

        # Window config
        window = webview.create_window(
            title="Minecraft Web Manager",
            url=f"http://127.0.0.1:{port}",
            width=1200,
            height=800,
            resizable=True,
            min_size=(900, 600),
            confirm_close=True,
            # Use MS Edge WebView2 on Windows (built-in on Win 10+)
            # Falls back to CEF if not available
        )

        # Block until the window is closed
        webview.start(
            debug=False,
            http_server=False,  # We run our own Flask server
        )

    except ImportError:
        print(" PyWebView not available — falling back to browser mode.")
        print(f" Open http://127.0.0.1:{port} in your browser.")
        print(" Press Ctrl+C to stop.")
        try:
            import webbrowser
            webbrowser.open(f"http://127.0.0.1:{port}")
        except Exception:
            pass
        # Keep the main thread alive while Flask runs in the background
        try:
            while True:
                time.sleep(3600)
        except KeyboardInterrupt:
            pass

    print("  Shutting down.")


if __name__ == "__main__":
    main()
