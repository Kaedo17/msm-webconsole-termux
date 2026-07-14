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
import time
import urllib.request
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

    # Pre-download JDK bundles for installer
    download_jdks()


_JDK_VERSIONS = ["8", "11", "17", "21", "22", "23", "24", "25"]


def download_jdks():
    """Pre-download Eclipse Temurin JDK zips for all supported versions.

    Saves them to dist/MinecraftWebManager/data/jdk-zips/ so the NSIS
    installer picks them up via File /r.  On first launch the app
    extracts them automatically.
    """
    dest = OUTPUT_DIR / APP_NAME / "data" / "jdk-zips"
    dest.mkdir(parents=True, exist_ok=True)

    version_map = {
        "8": "8", "11": "11", "17": "17", "21": "21",
        "22": "22", "23": "23", "24": "24", "25": "25",
    }

    for ver in _JDK_VERSIONS:
        jver = version_map[ver]
        fname = f"jdk-{ver}_windows-x64_bin.zip"
        fpath = dest / fname

        if fpath.exists():
            size_mb = fpath.stat().st_size / (1024 * 1024)
            print(f"  JDK {ver}:  already present ({size_mb:.0f} MB)")
            continue

        url = f"https://api.adoptium.net/v3/binary/latest/{jver}/ga/windows/x64/jdk/hotspot/normal/eclipse"
        print(f"  JDK {ver}:  downloading from Adoptium API...", end="", flush=True)
        try:
            req = urllib.request.Request(url, headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Accept": "application/octet-stream",
            })
            t0 = time.time()
            with urllib.request.urlopen(req, timeout=600) as resp:
                data = resp.read()
            elapsed = time.time() - t0
            fpath.write_bytes(data)
            size_mb = fpath.stat().st_size / (1024 * 1024)
            print(f"  {size_mb:.0f} MB ({elapsed:.0f}s)")
        except Exception as e:
            print(f"  FAILED ({e})")
            print(f"  Warning: JDK {ver} not bundled — users can install from dashboard.")

    total = sum(f.stat().st_size for f in dest.iterdir() if f.suffix == ".zip")
    total_mb = total / (1024 * 1024)
    print(f"  JDK zips total: {total_mb:.0f} MB")


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
