"""Build Minecraft Web Manager as a standalone Windows desktop EXE.

The EXE embeds the web UI in a native window (PyWebView) — no browser needed.
Data (servers, config) is stored in %%APPDATA%%/MinecraftWebManager/.

Usage:
    python build_exe.py                    # Build desktop app EXE (no console)
    python build_exe.py --debug            # Build with console window (for testing)
    python build_exe.py --clean            # Clean build artifacts first
"""

import os
import shutil
import subprocess
import sys
from pathlib import Path

# ── Config ────────────────────────────────────────────────────────────
APP_NAME = "MinecraftWebManager"
ENTRY_POINT = "mc_app.py"       # Desktop app entry point (PyWebView window)
CLI_ENTRY = "webconsole.py"     # Fallback CLI entry (browser-based)
OUTPUT_DIR = Path("dist")
BUILD_DIR = Path("build")
SPEC_FILE = Path(f"{APP_NAME}.spec")
VERSION = "1.0.0"

# Base PyInstaller options
PYINSTALLER_OPTS = [
    "--name", APP_NAME,
    "--onedir",                 # Folder mode (no extraction delay, less flash)
    "--noupx",                  # No UPX compression
    "--strip",                  # Strip debug symbols
    # Hidden imports — Flask
    "--hidden-import", "flask",
    "--hidden-import", "werkzeug",
    "--hidden-import", "jinja2",
    "--hidden-import", "markupsafe",
    "--hidden-import", "itsdangerous",
    "--hidden-import", "click",
    # Hidden imports — PyWebView (loaded dynamically)
    "--hidden-import", "webview",
    "--hidden-import", "webview.platforms.edgechromium",
    "--hidden-import", "webview.platforms.win32_edge",
    "--hidden-import", "proxy_tools",
    # Hidden imports — app modules
    "--hidden-import", "mc_state",
    "--hidden-import", "mc_helpers",
    "--hidden-import", "mc_instances",
    "--hidden-import", "mc_server",
    "--hidden-import", "mc_routes",
    "--hidden-import", "mc_downloads",
    "--hidden-import", "mc_properties",
    "--hidden-import", "mc_curseforge",
    "--hidden-import", "mc_modrinth",
    "--hidden-import", "mc_playit",
    "--hidden-import", "mc_playit._unix",
    "--hidden-import", "mc_playit._windows",
    "--hidden-import", "mc_app",
]


# ── Helpers ───────────────────────────────────────────────────────────

def _find_pyinstaller():
    """Locate PyInstaller executable."""
    for candidate in [
        "pyinstaller",
        "pyinstaller.exe",
        os.path.join(os.path.dirname(sys.executable), "Scripts", "pyinstaller.exe"),
        os.path.join(os.path.dirname(sys.executable), "Scripts", "pyinstaller"),
    ]:
        if shutil.which(candidate):
            return candidate
    return [sys.executable, "-m", "PyInstaller"]


def clean():
    """Remove previous build artifacts."""
    for d in [OUTPUT_DIR, BUILD_DIR]:
        if d.exists():
            shutil.rmtree(d)
    for f in [SPEC_FILE]:
        if f.exists():
            f.unlink()
    print("  Cleaned build artifacts.")


def build(debug=False):
    """Run PyInstaller to build the EXE."""
    pyi = _find_pyinstaller()

    opts = list(PYINSTALLER_OPTS)

    # Window mode
    if debug:
        opts.append("--console")    # Show console window (debug builds)
    else:
        opts.append("--windowed")    # No console — proper desktop app

    # Build command
    cmd = (
        [pyi] if isinstance(pyi, str)
        else pyi
    )
    cmd.extend(opts)
    cmd.append(ENTRY_POINT)

    mode = "DESKTOP APP (windowed)" if not debug else "DEBUG (with console)"
    print(f"  Mode:         {mode}")
    print(f"  Entry point:  {ENTRY_POINT}")
    print(f"  PyInstaller:  {pyi}")
    print(f"  Output dir:   {OUTPUT_DIR.resolve()}")
    print(f"  Version:      {VERSION}")
    print()

    result = subprocess.run(cmd, cwd=os.path.dirname(__file__) or ".")
    if result.returncode != 0:
        print(f"\n  Build FAILED (exit code {result.returncode})")
        sys.exit(1)

    # Verify EXE was created (onedir mode: inside the app folder)
    exe_path = OUTPUT_DIR / APP_NAME / f"{APP_NAME}.exe"
    if exe_path.exists():
        size_mb = exe_path.stat().st_size / (1024 * 1024)
        print(f"\n  {'=' * 50}")
        print(f"  SUCCESS: {exe_path} ({size_mb:.1f} MB)")
        print(f"  {'=' * 50}")
    else:
        print(f"\n  Build completed but EXE not found at {exe_path}")
        sys.exit(1)


def build_installer():
    """Build a Windows installer using NSIS (if available)."""
    nsis = shutil.which("makensis") or shutil.which("makensis.exe")
    if not nsis:
        nsis_paths = [
            "C:/Program Files (x86)/NSIS/makensis.exe",
            "C:/Program Files/NSIS/makensis.exe",
        ]
        for p in nsis_paths:
            if os.path.exists(p):
                nsis = p
                break

    if not nsis:
        print("\n  NSIS (makensis) not found. Install from https://nsis.sourceforge.io/")
        print("  Then run: makensis installer.nsi")
        return

    print(f"  Building installer with NSIS...")
    result = subprocess.run([nsis, "installer.nsi"], cwd=os.path.dirname(__file__) or ".")
    if result.returncode == 0:
        print(f"  Installer created: MinecraftWebManager_Setup_{VERSION}.exe")
    else:
        print(f"  Installer build FAILED (exit code {result.returncode})")


# ── Main ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    os.chdir(os.path.dirname(os.path.abspath(__file__)))

    debug = "--debug" in sys.argv
    clean_build = "--clean" in sys.argv
    make_installer = "--installer" in sys.argv

    if clean_build:
        clean()

    print(f"  Building {APP_NAME} v{VERSION}...")
    print()
    build(debug=debug)

    if make_installer:
        build_installer()
    else:
        print()
        print("  Done! Distribute the EXE file in the 'dist/' folder.")
        print("  To build an installer, install NSIS and run: python build_exe.py --installer")
