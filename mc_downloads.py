"""Minecraft server jar downloader for all server types.

Downloads server jars from various providers:
  Paper, Purpur, Spigot, Vanilla, Folia, DivineMC —
      via mcjars.app API (unified)
  Fabric — via Fabric meta API
  Forge — via Forge maven
  Paper — also directly via fill.papermc.io (more up-to-date)
  Purpur — also directly via api.purpurmc.org
"""

import json
import os
import re
import subprocess
import urllib.parse
import urllib.request

UA = "mcmanage-termux/1.0"

SERVER_TYPES = [
    "paper", "purpur", "spigot", "vanilla", "folia", "divinemc",
    "fabric", "forge",
]

def _get_json(url, timeout=20):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    return json.loads(urllib.request.urlopen(req, timeout=timeout).read())


def _get_bytes(url, timeout=60):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    return urllib.request.urlopen(req, timeout=timeout).read()


# ═══════════════════════════════════════════════════════════════════════
#  VERSION LISTING
# ═══════════════════════════════════════════════════════════════════════

def get_minecraft_versions():
    """Fetch all stable Minecraft release versions from Mojang manifest."""
    try:
        manifest = _get_json("https://launchermeta.mojang.com/mc/game/version_manifest.json")
        versions = []
        for v in manifest.get("versions", []):
            if v.get("type") == "release":
                versions.append(v["id"])
        return sorted(versions, key=lambda x: [int(p) for p in x.split(".")], reverse=True)
    except Exception as e:
        return []


def get_latest_minecraft_version():
    """Get the latest stable Minecraft release version."""
    versions = get_minecraft_versions()
    return versions[0] if versions else ""


def get_forge_versions(mc_version):
    """Fetch available Forge versions for a Minecraft version."""
    try:
        url = f"https://maven.minecraftforge.net/net/minecraftforge/forge/maven-metadata.xml"
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        data = urllib.request.urlopen(req, timeout=20).read().decode("utf-8", "replace")
        versions = re.findall(rf'<version>{re.escape(mc_version)}-([^<]+)</version>', data)
        return sorted(set(versions))
    except Exception:
        return []


def get_versions(server_type):
    """Get available Minecraft versions for a server type."""
    if server_type == "forge":
        return get_minecraft_versions()[:30]
    return get_minecraft_versions()[:30]


# ═══════════════════════════════════════════════════════════════════════
#  DOWNLOAD URL RESOLUTION
# ═══════════════════════════════════════════════════════════════════════

def _resolve_mcjars(server_type, mc_version):
    """Resolve jar URL via mcjars.app API."""
    url = f"https://mcjars.app/api/v1/builds/{server_type.upper()}/{mc_version}/latest?tracking=none"
    data = _get_json(url)
    return data.get("build", {}).get("jarUrl", "")


def get_download_url(server_type, mc_version, forge_version=None):
    """Get the download URL for a specific server type and version."""
    st = server_type.lower()
    
    if st == "paper":
        try:
            data = _get_json(f"https://api.papermc.io/v2/projects/paper/versions/{mc_version}")
            builds = data.get("builds", [])
            if builds:
                latest = builds[-1]
                return (f"https://api.papermc.io/v2/projects/paper/versions/{mc_version}"
                        f"/builds/{latest}/downloads/paper-{mc_version}-{latest}.jar")
        except Exception:
            pass
        return _resolve_mcjars("paper", mc_version)

    elif st == "purpur":
        return f"https://api.purpurmc.org/v2/purpur/{mc_version}/latest/download"

    elif st == "fabric":
        loader_url = "https://meta.fabricmc.net/v2/versions/loader"
        loader_ver = "0.16.10"
        installer_ver = "1.0.1"
        try:
            loaders = _get_json(f"{loader_url}/{mc_version}")
            if loaders:
                loader_ver = loaders[0]["loader"]["version"]
        except Exception:
            pass
        try:
            installers = _get_json("https://meta.fabricmc.net/v2/versions/installer")
            if installers:
                installer_ver = installers[0]["version"]
        except Exception:
            pass
        return f"{loader_url}/{mc_version}/{loader_ver}/{installer_ver}/server/jar"

    elif st == "forge":
        if not forge_version:
            return ""
        url = (f"https://maven.minecraftforge.net/net/minecraftforge/forge/"
               f"{mc_version}-{forge_version}/forge-{mc_version}-{forge_version}-installer.jar")
        return url

    else:
        return _resolve_mcjars(st, mc_version)


def download_server_jar(server_dir, server_type, mc_version, forge_version=None):
    """Download the server jar to the given directory. Returns (success, msg)."""
    url = get_download_url(server_type, mc_version, forge_version)
    if not url:
        return False, "No download URL available for this type/version combination."

    server_dir.mkdir(parents=True, exist_ok=True)
    jar_path = server_dir / "server.jar"

    try:
        data = _get_bytes(url, timeout=120)
        jar_path.write_bytes(data)
    except Exception as e:
        return False, f"Download failed: {e}"

    if jar_path.stat().st_size < 1000:
        jar_path.unlink()
        return False, "Downloaded file appears invalid (too small)."

    # For Forge, run the installer
    if server_type.lower() == "forge":
        try:
            subprocess.run(
                [str(subprocess.check_output(["which", "java"], text=True).strip()),
                 "-jar", str(jar_path), "--installServer"],
                cwd=str(server_dir), capture_output=True, timeout=120
            )
            # Clean up installer files
            for f in server_dir.glob("installer.log"):
                f.unlink()
            # Find the actual forge jar
            forge_jars = list(server_dir.glob("forge-*.jar"))
            for f in forge_jars:
                if "installer" not in f.name and "universal" not in f.name:
                    f.rename(server_dir / "server.jar")
                    break
        except subprocess.TimeoutExpired:
            return False, "Forge installer timed out."
        except Exception as e:
            return False, f"Forge installation failed: {e}"

    return True, f"Downloaded {jar_path.name} ({jar_path.stat().st_size // 1024 // 1024} MB)"


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
    }
    return info.get(server_type, info["vanilla"])
