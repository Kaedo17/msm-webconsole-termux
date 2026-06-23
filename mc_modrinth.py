"""Modrinth API integration for browsing and installing modpacks / resource packs."""

import json
import urllib.parse
import urllib.request

import mc_state

MODRINTH_API = "https://api.modrinth.com/v2"
UA = "mcmanage-termux/1.0"


def _modrinth_get(url, timeout=15):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    res = urllib.request.urlopen(req, timeout=timeout)
    return json.loads(res.read())


def modrinth_search(query, project_type="modpack", limit=20):
    try:
        url = (f"{MODRINTH_API}/search"
               f"?query={urllib.parse.quote(query)}"
               f"&facets={urllib.parse.quote(json.dumps([[f'project_type:{project_type}']]))}"
               f"&limit={limit}")
        data = _modrinth_get(url)
        return [{
            "id": h["project_id"],
            "title": h["title"],
            "description": h.get("description", ""),
            "icon_url": h.get("icon_url", ""),
            "author": h.get("author", ""),
            "downloads": h.get("downloads", 0),
            "slug": h.get("slug", ""),
            "latest_version": h.get("latest_version", ""),
            "project_type": h.get("project_type", project_type),
        } for h in data.get("hits", [])]
    except Exception as e:
        return {"error": str(e)}


def modrinth_versions(project_id):
    try:
        url = f"{MODRINTH_API}/project/{project_id}/version"
        data = _modrinth_get(url)
        return [{
            "id": v["id"],
            "name": v["name"],
            "version_number": v["version_number"],
            "game_versions": v.get("game_versions", []),
            "loaders": v.get("loaders", []),
            "files": [{"url": f["url"], "filename": f["filename"], "size": f["size"]}
                      for f in v.get("files", [])],
            "date": v.get("date_published", ""),
        } for v in data]
    except Exception as e:
        return {"error": str(e)}


def modrinth_download(file_url, dest_path):
    req = urllib.request.Request(file_url, headers={"User-Agent": UA})
    res = urllib.request.urlopen(req, timeout=60)
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    with open(dest_path, "wb") as f:
        while True:
            chunk = res.read(8192)
            if not chunk:
                break
            f.write(chunk)
    return dest_path


def list_installed_packs(server_dir):
    result = []
    for sub, pack_type in [("mods", "mod"), ("resourcepacks", "resourcepack")]:
        d = server_dir / sub
        if d.exists():
            for f in sorted(d.iterdir()):
                if f.suffix in (".jar", ".zip"):
                    result.append({
                        "name": f.name,
                        "path": str(f.relative_to(server_dir)),
                        "size": f.stat().st_size,
                        "type": pack_type,
                    })
    return result
