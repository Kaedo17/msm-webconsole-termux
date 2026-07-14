"""Minecraft server jar downloader for all server types.

Downloads server jars from various providers:
  Paper      — fill.papermc.io (v3 API)
  Purpur     — api.purpurmc.org
  Spigot     — mcjars.app (no official pre-compiled API)
  Vanilla    — launchermeta.mojang.com / piston-data.mojang.com
  Folia      — fill.papermc.io (v3 API) via mcjars.app fallback
  DivineMC   — mcjars.app (no official download API)
  Fabric     — meta.fabricmc.net
  Forge      — maven.minecraftforge.net
  NeoForge   — maven.neoforged.net
"""

import json
import os
import re
import subprocess
import urllib.request
from pathlib import Path

import mc_state

UA = "mcmanage-webconsole/1.0"

SERVER_TYPES = [
    "paper", "purpur", "spigot", "vanilla", "folia", "divinemc",
    "fabric", "forge", "neoforge",
]


def _get_json(url, timeout=20):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    return json.loads(urllib.request.urlopen(req, timeout=timeout).read())


def _get_bytes(url, timeout=120):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    return urllib.request.urlopen(req, timeout=timeout).read()


# ═══════════════════════════════════════════════════════════════════════
#  VERSION LISTING
# ═══════════════════════════════════════════════════════════════════════

def get_minecraft_versions():
    """Fetch all stable Minecraft release versions from Mojang manifest."""
    try:
        manifest = _get_json("https://launchermeta.mojang.com/mc/game/version_manifest.json")
        versions = [v["id"] for v in manifest.get("versions", []) if v.get("type") == "release"]
        return sorted(versions, key=lambda x: [int(p) for p in x.split(".")], reverse=True)
    except Exception:
        return []


def get_latest_minecraft_version():
    """Get the latest stable Minecraft release version."""
    versions = get_minecraft_versions()
    return versions[0] if versions else ""


def get_forge_versions(mc_version):
    """Fetch available Forge versions for a Minecraft version."""
    try:
        url = "https://maven.minecraftforge.net/net/minecraftforge/forge/maven-metadata.xml"
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        data = urllib.request.urlopen(req, timeout=20).read().decode("utf-8", "replace")
        versions = re.findall(rf'<version>{re.escape(mc_version)}-([^<]+)</version>', data)
        return sorted(set(versions), reverse=True)
    except Exception:
        return []


def get_neoforge_versions(mc_version):
    """Fetch available NeoForge versions for a Minecraft version.

    NeoForge versions encode the MC version in their prefix.
    For MC 1.x, it drops the leading '1.':
      - MC 1.21.4  → NeoForge 21.4.x
      - MC 1.20.2  → NeoForge 20.2.x
    For MC 26.x+ (new scheme), versions match directly.
    """
    try:
        url = "https://maven.neoforged.net/releases/net/neoforged/neoforge/maven-metadata.xml"
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        data = urllib.request.urlopen(req, timeout=20).read().decode("utf-8", "replace")
        all_versions = re.findall(r'<version>([^<]+)</version>', data)

        # Build the NeoForge version prefix from MC version
        prefix = _mc_to_neoforge_prefix(mc_version)
        if not prefix:
            return []

        matching = [v for v in all_versions if v.startswith(prefix)]
        return [m for m in sorted(set(matching), reverse=True)][:50]  # newest 50
    except Exception:
        return []


def _mc_to_neoforge_prefix(mc_version):
    """Convert a Minecraft version string to a NeoForge version prefix.

    NeoForge drops the leading '1.' from MC versions:
      1.21.4  → '21.4.'
      1.20.2  → '20.2.'
      1.21    → '21.0.'
      26.2    → '26.2.'  (direct for 26+)
    """
    parts = mc_version.split(".")
    if len(parts) < 2:
        return None

    if parts[0] == "1":
        # MC 1.21.4 → NeoForge 21.4.
        minor = parts[1]
        patch = parts[2] if len(parts) >= 3 else "0"
        return f"{minor}.{patch}."
    else:
        # MC 26.2+ → direct mapping
        major = parts[0]
        minor = parts[1] if len(parts) >= 2 else "0"
        return f"{major}.{minor}."


def get_versions(server_type):
    """Get available Minecraft versions for a server type."""
    return get_minecraft_versions()[:30]


# ═══════════════════════════════════════════════════════════════════════
#  DOWNLOAD URL RESOLUTION — per-type helpers
# ═══════════════════════════════════════════════════════════════════════

def _resolve_mcjars(server_type, mc_version):
    """Resolve jar URL via mcjars.app API (community proxy API).

    Acts as a fallback when a type-specific API isn't available.
    """
    try:
        url = f"https://mcjars.app/api/v1/builds/{server_type.upper()}/{mc_version}/latest?tracking=none"
        data = _get_json(url, timeout=15)
        return data.get("build", {}).get("jarUrl", "")
    except Exception:
        return ""


def _get_paper_url(mc_version):
    """PaperMC download URL via fill.papermc.io v3 API.

    The v2 API (api.papermc.io) is deprecated and returns 410 Gone.
    """
    try:
        builds = _get_json(f"https://fill.papermc.io/v3/projects/paper/versions/{mc_version}/builds")
        if isinstance(builds, list) and builds:
            latest = builds[0]
            download_info = latest.get("downloads", {}).get("server:default", {})
            url = download_info.get("url", "")
            if url:
                return url
    except Exception:
        pass
    return _resolve_mcjars("paper", mc_version)


def _get_purpur_url(mc_version):
    """Purpur download URL via Purpur API."""
    try:
        # First check the version exists and get the latest build number
        data = _get_json(f"https://api.purpurmc.org/v2/purpur/{mc_version}")
        latest = data.get("builds", {}).get("latest")
        if latest:
            return f"https://api.purpurmc.org/v2/purpur/{mc_version}/{latest}/download"
    except Exception:
        pass
    return _resolve_mcjars("purpur", mc_version)


def _get_vanilla_url(mc_version):
    """Vanilla download URL via Mojang's official version manifest.

    Uses the same API the official Minecraft launcher uses.
    """
    try:
        manifest = _get_json("https://launchermeta.mojang.com/mc/game/version_manifest.json")
        for entry in manifest.get("versions", []):
            if entry.get("id") == mc_version and entry.get("type") == "release":
                version_json = _get_json(entry["url"])
                server = version_json.get("downloads", {}).get("server", {})
                url = server.get("url", "")
                if url:
                    return url
    except Exception:
        pass
    return _resolve_mcjars("vanilla", mc_version)


def _get_fabric_url(mc_version):
    """Fabric download URL via Fabric Meta API.

    Uses a two-step resolution:
      1. Get the latest loader version for the MC version
      2. Get the latest installer version (separate endpoint)
    """
    try:
        loaders = _get_json(f"https://meta.fabricmc.net/v2/versions/loader/{mc_version}")
        if not loaders:
            return _resolve_mcjars("fabric", mc_version)
        loader_ver = loaders[0]["loader"]["version"]

        # Fetch the latest stable installer version
        installers = _get_json("https://meta.fabricmc.net/v2/versions/installer")
        installer_ver = "1.0.1"  # conservative fallback
        for inst in installers:
            if inst.get("stable", False):
                installer_ver = inst["version"]
                break
        if not installer_ver and installers:
            installer_ver = installers[0]["version"]

        return (f"https://meta.fabricmc.net/v2/versions/loader/"
                f"{mc_version}/{loader_ver}/{installer_ver}/server/jar")
    except Exception:
        pass
    return _resolve_mcjars("fabric", mc_version)


def _get_forge_url(mc_version, forge_version=None):
    """Forge download URL via Forge maven.

    Returns the installer jar URL which is then used with --installServer.
    """
    if not forge_version:
        return ""
    return (f"https://maven.minecraftforge.net/net/minecraftforge/forge/"
            f"{mc_version}-{forge_version}/forge-{mc_version}-{forge_version}-installer.jar")


def _get_neoforge_url(mc_version, forge_version=None):
    """NeoForge download URL via NeoForged maven.

    Returns the installer jar URL which is then used with --installServer.

    Unlike classic Forge, NeoForge versions are self-contained strings
    like '21.4.73-alpha' or '26.2.0.11-beta' that already encode the
    MC version. The user selects the NeoForge version directly.
    """
    if not forge_version:
        return ""
    return (f"https://maven.neoforged.net/releases/net/neoforged/neoforge/"
            f"{forge_version}/neoforge-{forge_version}-installer.jar")


def get_download_url(server_type, mc_version, forge_version=None):
    """Get the download URL for a specific server type and version."""
    st = server_type.lower()

    if st == "paper":
        return _get_paper_url(mc_version)
    elif st == "purpur":
        return _get_purpur_url(mc_version)
    elif st == "vanilla":
        return _get_vanilla_url(mc_version)
    elif st == "fabric":
        return _get_fabric_url(mc_version)
    elif st == "forge":
        return _get_forge_url(mc_version, forge_version)
    elif st == "neoforge":
        return _get_neoforge_url(mc_version, forge_version)
    else:
        # Spigot, Folia, DivineMC — fallback via mcjars.app
        return _resolve_mcjars(st, mc_version)


# ═══════════════════════════════════════════════════════════════════════
#  DOWNLOAD + INSTALL
# ═══════════════════════════════════════════════════════════════════════

def _find_java():
    """Get the system Java binary path."""
    # Primary: use mc_state.JAVA_BIN (set via shutil.which during import)
    java = getattr(mc_state, "JAVA_BIN", None)
    if java and java != "java":
        return java
    # Fallback: JAVA_HOME
    java_home = os.environ.get("JAVA_HOME", "")
    if java_home:
        candidate = Path(java_home) / "bin" / "java"
        if candidate.exists():
            return str(candidate)
    # Final fallback: let the OS resolve it
    return "java"



def _find_installed_forge_args_file(server_dir):
    """Detect modern Forge (1.18+) by finding the launcher arg file."""
    args_name = "win_args.txt" if os.name == "nt" else "unix_args.txt"
    for p in sorted(server_dir.glob("libraries/net/minecraftforge/forge/*/"), reverse=True):
        if (p / args_name).exists():
            return True
    return False

def _is_valid_jar(path):
    """Check if a file is a valid JAR/ZIP by checking magic bytes."""
    try:
        with open(path, "rb") as f:
            header = f.read(4)
        return header == b"PK\x03\x04"
    except Exception:
        return False


def _get_forge_direct_server_url(mc_version, forge_version):
    """Try possible direct Forge server jar URLs (avoids the installer)."""
    base = (f"https://maven.minecraftforge.net/net/minecraftforge/forge/"
            f"{mc_version}-{forge_version}/forge-{mc_version}-{forge_version}")
    return [
        f"{base}-server.jar",
        f"{base}.jar",
    ]


def download_server_jar(server_dir, server_type, mc_version, forge_version=None):
    """Download the server jar to the given directory.

    For Forge, this first tries to download the server jar directly from maven.
    If that fails, it downloads the installer and runs --installServer.
    For NeoForge, it downloads the installer and runs --installServer.
    For all other types, it downloads the jar directly.

    Returns (success, msg).
    """
    url = get_download_url(server_type, mc_version, forge_version)
    if not url:
        return False, "No download URL available for this type/version combination."

    server_dir.mkdir(parents=True, exist_ok=True)
    st = server_type.lower()

    # ── Forge: try direct server jar first, then installer ──
    if st == "forge":
        if forge_version:
            direct_urls = _get_forge_direct_server_url(mc_version, forge_version)
            for du in direct_urls:
                try:
                    data = _get_bytes(du, timeout=60)
                    jar_path = server_dir / "server.jar"
                    jar_path.write_bytes(data)
                    if jar_path.stat().st_size >= 1000 and _is_valid_jar(jar_path):
                        size_mb = jar_path.stat().st_size // 1024 // 1024
                        return True, f"Downloaded forge server.jar ({size_mb} MB)"
                except Exception:
                    continue

        # Direct download failed — fall back to installer
        ok_, msg, jar_path = _run_forge_installer(server_dir, mc_version, forge_version)
        if ok_ and jar_path:
            # Legacy Forge: found a standalone jar, rename it
            target = server_dir / "server.jar"
            if target.exists():
                target.unlink()
            jar_path.rename(target)
            if _is_valid_jar(target):
                size_mb = target.stat().st_size // 1024 // 1024
                return True, f"Legacy forge installed ({size_mb} MB)"
            target.unlink(missing_ok=True)
            return False, "Legacy forge created an invalid server jar."
        # Modern Forge (1.18+): no standalone jar, uses @arg files
        return ok_, msg
    # ── NeoForge: download installer, run it ──
    if st == "neoforge":
        ok_, msg, jar_path = _run_neoforge_installer(server_dir, mc_version, forge_version)
        if ok_ and jar_path:
            target = server_dir / "server.jar"
            if target.exists():
                target.unlink()
            jar_path.rename(target)
            if _is_valid_jar(target):
                size_mb = target.stat().st_size // 1024 // 1024
                return True, f"NeoForge installed ({size_mb} MB)"
            else:
                target.unlink(missing_ok=True)
                return False, "NeoForge installer created an invalid server jar."
        return ok_, msg

    # ── All other types: direct download ──
    jar_path = server_dir / "server.jar"
    try:
        data = _get_bytes(url, timeout=120)
        jar_path.write_bytes(data)
    except Exception as e:
        return False, f"Download failed: {e}"

    if jar_path.stat().st_size < 1000:
        jar_path.unlink()
        return False, "Downloaded file appears invalid (too small)."

    if not _is_valid_jar(jar_path):
        jar_path.unlink()
        return False, "Downloaded file is not a valid JAR (wrong format)."

    size_mb = jar_path.stat().st_size // 1024 // 1024
    return True, f"Downloaded server.jar ({size_mb} MB)"


def _run_forge_installer(server_dir, mc_version, forge_version):
    """Download a Forge installer jar and run --installServer.

    Returns (success, message, server_jar_path_or_None).
    """
    url = _get_forge_url(mc_version, forge_version)
    if not url:
        return False, "No installer URL available.", None

    return _run_installer(server_dir, url, mc_version, forge_version, "forge")


def _run_neoforge_installer(server_dir, mc_version, forge_version):
    """Download a NeoForge installer jar and run --installServer.

    Returns (success, message, server_jar_path_or_None).
    """
    url = _get_neoforge_url(mc_version, forge_version)
    if not url:
        return False, "No installer URL available.", None

    return _run_installer(server_dir, url, mc_version, forge_version, "neoforge")


def _run_installer(server_dir, url, mc_version, forge_version, st):
    """Download an installer jar and run --installServer.

    st: 'forge' or 'neoforge' (affects jar detection).
    Returns (success, message, server_jar_path_or_None).
    """
    if not url:
        return False, "No installer URL available.", None

    installer_path = server_dir / "forge-installer.jar"
    try:
        data = _get_bytes(url, timeout=120)
        installer_path.write_bytes(data)
    except Exception as e:
        return False, f"Installer download failed: {e}", None

    if installer_path.stat().st_size < 1000:
        installer_path.unlink(missing_ok=True)
        return False, "Downloaded installer is too small (invalid).", None

    if not _is_valid_jar(installer_path):
        installer_path.unlink(missing_ok=True)
        return False, "Downloaded installer is not a valid JAR (check forge version).", None

    try:
        java_bin = _find_java()
        extra = {}
        if os.name == "nt":
            extra["startupinfo"] = subprocess.STARTUPINFO()
            extra["startupinfo"].dwFlags |= subprocess.STARTF_USESHOWWINDOW
        result = subprocess.run(
            [java_bin, "-jar", str(installer_path), "--installServer"],
            cwd=str(server_dir),
            capture_output=True,
            timeout=180,
            **extra
        )

        # Clean up installer log
        for f in server_dir.glob("installer.log"):
            f.unlink(missing_ok=True)

        installer_path.unlink(missing_ok=True)

        # Check if the installer actually succeeded
        if result.returncode != 0:
            err = result.stderr.decode("utf-8", errors="replace")[-500:]
            out = result.stdout.decode("utf-8", errors="replace")[-500:]
            detail = (err or out or "unknown error").strip()
            return False, f"Installer failed (exit {result.returncode}): {detail[:200]}", None

        # Modern Forge (1.18+) doesn't create a standalone jar — uses @arg files
        if st == "forge":
            args_file = _find_installed_forge_args_file(server_dir)
            if args_file:
                return True, "Forge installed (modern launcher).", None
            server_jar = _find_forge_server_jar(server_dir, mc_version, forge_version)
        else:
            server_jar = _find_neoforge_server_jar(server_dir, forge_version)
            if server_jar is None:
                server_jar = _find_neoforge_server_jar_libraries(server_dir, forge_version)

        if server_jar and server_jar.exists():
            return True, "Installer succeeded.", server_jar
        else:
            jars = [j.name for j in server_dir.glob("*.jar")]
            return False, f"Installer ran but no server jar found. Files: {jars[:10]}", None

    except subprocess.TimeoutExpired:
        installer_path.unlink(missing_ok=True)
        return False, "Installer timed out (180s).", None
    except Exception as e:
        installer_path.unlink(missing_ok=True)
        return False, f"Installer failed: {e}", None


def _find_forge_server_jar(server_dir, mc_version, forge_version):
    """Find the actual Forge server jar after running the installer.

    Modern Forge (1.17+) naming: forge-{version}-server.jar
    Older naming: forge-{version}.jar
    Universal naming (very old): forge-{version}-universal.jar
    """
    # Search root directory for forge-*.jar excluding installer/universal
    forge_jars = list(server_dir.glob("forge-*.jar"))
    for f in forge_jars:
        name = f.name
        if "installer" in name:
            continue
        if "universal" in name:
            continue
        return f

    # Fallback: check libraries dir (very old Forge, pre-1.13)
    if forge_version:
        lib_dir = (server_dir / "libraries" / "net" / "minecraftforge"
                   / "forge" / f"{mc_version}-{forge_version}")
        if lib_dir.exists():
            for f in lib_dir.glob("*.jar"):
                if "server" in f.name.lower() or "universal" in f.name.lower():
                    return f

    return None


def _find_neoforge_server_jar(server_dir, forge_version):
    """Find the NeoForge server jar after running the installer.

    NeoForge creates: neoforge-{version}.jar in the server root.
    """
    for f in server_dir.glob("neoforge-*.jar"):
        name = f.name
        if "installer" in name:
            continue
        return f
    return None


def _find_neoforge_server_jar_libraries(server_dir, forge_version):
    """Fallback: check libraries dir for NeoForge server jar."""
    if not forge_version:
        return None
    lib_dir = server_dir / "libraries" / "net" / "neoforged" / "neoforge" / forge_version
    if lib_dir.exists():
        for f in lib_dir.glob("*.jar"):
            if "server" in f.name.lower() and "installer" not in f.name:
                return f
    return None


# ═══════════════════════════════════════════════════════════════════════
#  DISPLAY METADATA
# ═══════════════════════════════════════════════════════════════════════

def install_type_details(server_type):
    """Return display info for a server type."""
    info = {
        "paper":     {"label": "Paper",     "desc": "Plugin Support — High-performance Spigot fork", "needs_forge_ver": False},
        "purpur":    {"label": "Purpur",    "desc": "Plugin Support — Configurable Paper fork", "needs_forge_ver": False},
        "spigot":    {"label": "Spigot",    "desc": "Plugin Support — Bukkit-based server", "needs_forge_ver": False},
        "vanilla":   {"label": "Vanilla",   "desc": "Official Minecraft server", "needs_forge_ver": False},
        "folia":     {"label": "Folia",     "desc": "Some Plugin Support — Multithreaded Paper fork", "needs_forge_ver": False},
        "divinemc":  {"label": "DivineMC",  "desc": "Plugin Support — Optimized Purpur fork", "needs_forge_ver": False},
        "fabric":    {"label": "Fabric",    "desc": "Mod Support — Lightweight modding platform", "needs_forge_ver": False},
        "forge":     {"label": "Forge",     "desc": "Mod Support — Original modding platform", "needs_forge_ver": True},
        "neoforge":  {"label": "NeoForge",  "desc": "Mod Support — Modern Forge fork (MC 1.20+)", "needs_forge_ver": True},
    }
    return info.get(server_type, info["vanilla"])
