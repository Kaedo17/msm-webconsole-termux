"""Shared state and config for the Minecraft web console.

Multi-server: each server instance is managed by mc_instances.py.
This module holds web-app-level config only.
"""

import json
import os
import re
import shutil
import subprocess
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
HOST = os.environ.get("HOST", "0.0.0.0")
PORT = int(os.environ.get("PORT", 5000))
JAVA_BIN = shutil.which("java") or "java"
CONSOLE_MAX = 500
CONFIG_FILE = SCRIPT_DIR / "webconsole_config.json"

# ── Java version detection ──

# MC version → required Java major version
# Format: (maj, min) or None for "all remaining"
_JAVA_REQUIREMENTS = [
    ((1, 21),  21),   # 1.21+  → Java 21
    ((1, 20, 5), 21), # 1.20.5+ → Java 21
    ((1, 18),  17),   # 1.18+  → Java 17
    ((1, 17),  17),   # 1.17+  → Java 17
    ((1, 13),  11),   # 1.13+  → Java 11 (also works with 8, but 11+ recommended)
    ((0,),      8),   # Everything else → Java 8
]

# Cache: {major_ver: path} e.g. {"17": "/usr/bin/java17", "21": "/usr/bin/java21"}
_java_cache = None


def _parse_mc_version(mc_version):
    """Parse Minecraft version into a tuple of ints for comparison.

    "1.20.4" → (1, 20, 4), "1.21" → (1, 21), "" → None
    """
    if not mc_version:
        return None
    parts = re.findall(r"\d+", mc_version)
    if not parts:
        return None
    return tuple(int(p) for p in parts)


def _get_java_major_version(java_bin):
    """Run `java_bin -version` and return the major version number (e.g. 17, 21).

    Returns None if the binary doesn't exist or can't be run.
    """
    try:
        extra = {}
        if os.name == "nt":
            extra["startupinfo"] = subprocess.STARTUPINFO()
            extra["startupinfo"].dwFlags |= subprocess.STARTF_USESHOWWINDOW
        result = subprocess.run(
            [str(java_bin), "-version"],
            capture_output=True, text=True, timeout=5, **extra
        )
        # java -version outputs to stderr
        output = result.stderr or result.stdout
        # Match patterns: "version \"1.8.0_301\"" → 8; "version \"17.0.1\"" → 17
        m = re.search(r'version\s+"([0-9]+)', output)
        if m:
            ver = int(m.group(1))
            if ver == 1:
                # Java 8 reports as 1.8
                return 8
            return ver
        return None
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return None


def detect_java_versions():
    """Scan for available Java installations and return {major_ver: path}.

    Checks PATH for common Java binary names and runs -version on each.
    Results are cached globally. Call clear_java_cache() to re-scan.
    """
    global _java_cache
    if _java_cache is not None:
        return _java_cache

    candidates = set()

    # 1. Check PATH for versioned Java binaries
    for name in ["java21", "java17", "java11", "java8", "java"]:
        path = shutil.which(name)
        if path:
            candidates.add(path)

    # 2. Check JAVA_HOME
    java_home = os.environ.get("JAVA_HOME", "")
    if java_home:
        jbin = Path(java_home) / "bin" / "java"
        if jbin.exists():
            candidates.add(str(jbin.resolve()))
        else:
            # Maybe JAVA_HOME points to the JDK root without /bin
            jbin = Path(java_home) / "bin" / "java.exe"
            if jbin.exists():
                candidates.add(str(jbin.resolve()))

    # 3. Check the app's own data/jdk directory (shipped/downloaded JDK)
    app_jdk_dir = SCRIPT_DIR / "data" / "jdk"
    if app_jdk_dir.exists():
        # Check for versioned subdirectories (jdk-8, jdk-17, jdk-21)
        for sub in app_jdk_dir.iterdir():
            if sub.is_dir():
                for f in sub.rglob("java.exe") if os.name == "nt" else sub.rglob("java"):
                    candidates.add(str(f.resolve()))
        # Also check directly (legacy location)
        for f in app_jdk_dir.rglob("java.exe") if os.name == "nt" else app_jdk_dir.rglob("java"):
            candidates.add(str(f.resolve()))

    # 4. Check common JVM installation directories
    jvm_dirs = [
        # Linux / Termux
        Path("/usr/lib/jvm"),
        Path(Path.home() / ".local/lib/jvm"),
        Path(Path.home() / ".sdkman/candidates/java/current/bin"),
        Path("/data/data/com.termux/files/usr/lib/jvm"),
    ]

    # Windows Java install locations
    if os.name == "nt":
        for prog_dir in ["C:/Program Files", "C:/Program Files (x86)"]:
            pd = Path(prog_dir)
            if not pd.exists():
                continue
            # Eclipse Adoptium / Temurin
            for vendor in ["Eclipse Adoptium", "Eclipse Foundation", "Temurin"]:
                vd = pd / vendor
                if vd.exists():
                    for jdk in vd.iterdir():
                        jbin = jdk / "bin" / "java.exe"
                        if jbin.exists():
                            candidates.add(str(jbin.resolve()))
            # Microsoft JDK
            md = pd / "Microsoft"
            if md.exists():
                for jdk in md.iterdir():
                    if jdk.name.startswith("jdk-"):
                        jbin = jdk / "bin" / "java.exe"
                        if jbin.exists():
                            candidates.add(str(jbin.resolve()))
            # Amazon Corretto
            cd = pd / "Amazon Corretto"
            if cd.exists():
                for jdk in cd.iterdir():
                    jbin = jdk / "bin" / "java.exe"
                    if jbin.exists():
                        candidates.add(str(jbin.resolve()))
            # Oracle Java
            od = pd / "Java"
            if od.exists():
                for jdk in od.iterdir():
                    if jdk.name.startswith("jdk-") or jdk.name.startswith("jre-"):
                        jbin = jdk / "bin" / "java.exe"
                        if jbin.exists():
                            candidates.add(str(jbin.resolve()))
            # Generic: any dir with bin/java.exe
            for item in pd.iterdir():
                if item.is_dir() and ("jdk" in item.name.lower() or "java" in item.name.lower() or "jre" in item.name.lower()):
                    jbin = item / "bin" / "java.exe"
                    if jbin.exists():
                        candidates.add(str(jbin.resolve()))

    for d in jvm_dirs:
        if d.is_dir():
            java_in_dir = d / "java"
            if java_in_dir.exists():
                candidates.add(str(java_in_dir.resolve()))
            # Also check subdirectories
            for sub in d.iterdir():
                if sub.is_dir():
                    jbin = sub / "bin" / "java"
                    if jbin.exists():
                        candidates.add(str(jbin.resolve()))

    result = {}
    for candidate in sorted(candidates):
        ver = _get_java_major_version(candidate)
        if ver:
            # Prefer newer paths for the same version (last wins, sorted)
            result[str(ver)] = candidate

    _java_cache = result
    return result


def clear_java_cache():
    """Force the next detect_java_versions() call to re-scan."""
    global _java_cache
    _java_cache = None


def get_java_label(java_path, show_path=False):
    """Return a human-readable Java label from a Java binary path or version string.

    Accepts a path or a version string like '8', '17', '21'.
    If show_path is True and a path was detected, includes the path.
    """
    ver = str(java_path)
    if not ver or ver == "java":
        return "Java (default)"
    # If it's just a version number
    if ver.isdigit():
        ver_map = {"8": "Java 8", "11": "Java 11", "17": "Java 17", "21": "Java 21"}
        return ver_map.get(ver, f"Java {ver}")
    # It's a path — extract version from -version output
    major = _get_java_major_version(java_path)
    if major:
        ver_map = {8: "Java 8", 11: "Java 11", 17: "Java 17", 21: "Java 21"}
        label = ver_map.get(major, f"Java {major}")
        if show_path:
            return f"{label} ({java_path})"
        return label
    return str(java_path)


def get_java_label_for_version(mc_version):
    """Return a display label for the Java version suitable for a given MC version."""
    java_bin = select_java_for_version(mc_version)
    if not java_bin:
        return "Java (default)"
    return get_java_label(java_bin)


def select_java_for_version(mc_version):
    """Select the best available Java binary for the given Minecraft version.

    Returns the path to the Java binary, or falls back to JAVA_BIN.
    """
    parsed = _parse_mc_version(mc_version)
    if not parsed:
        # No version info — fall back to the default
        return JAVA_BIN

    # Walk the requirements list to find the first match
    required_major = 17  # default sane fallback
    for ver_tuple, java_ver in _JAVA_REQUIREMENTS:
        if parsed >= ver_tuple:
            required_major = java_ver
            break

    # Try to find the required version
    available = detect_java_versions()
    str_required = str(required_major)
    if str_required in available:
        return available[str_required]

    # Try next-higher available version
    for ver in sorted(available.keys()):
        if int(ver) >= required_major:
            return available[ver]

    # Fall back to default
    return JAVA_BIN

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
    clear_java_cache()
