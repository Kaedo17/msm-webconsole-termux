"""SourceForge search integration for browsing modpacks / resource packs."""

import json
import urllib.parse
import urllib.request

UA = "mcmanage-termux/1.0"


def _sf_get(url, timeout=15):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    res = urllib.request.urlopen(req, timeout=timeout)
    return res.read()


def sourceforge_search(query, project_type="modpack", limit=20):
    """Search SourceForge projects."""
    try:
        url = f"https://sourceforge.net/ajaxsearch.php?q={urllib.parse.quote(query)}&type=projects&limit={limit}"
        raw = _sf_get(url)
        data = json.loads(raw)
        hits = []
        for item in data.get("projects", {}).get("results", [])[:limit]:
            project_id = item.get("shortname", "") or item.get("name", "")
            title = item.get("title", item.get("name", ""))
            desc = item.get("short_description", "") or item.get("description", "")
            author = item.get("authors_display", "") or item.get("developers", "")
            if isinstance(author, list):
                author = ", ".join(author)
            downloads = item.get("downloads_total", 0) or item.get("downloads", 0)
            icon = item.get("icon_url", "")
            if not icon and item.get("logo"):
                icon = f"https://sourceforge.net{item['logo']}"
            hits.append({
                "id": project_id,
                "title": title,
                "description": desc,
                "icon_url": icon,
                "author": author,
                "downloads": downloads,
                "slug": project_id,
                "latest_version": "",
                "project_type": project_type,
                "provider": "sourceforge",
            })
        return hits
    except Exception as e:
        return {"error": str(e)}


def sourceforge_versions(project_id, limit=20):
    """Fetch available files for a SourceForge project."""
    try:
        url = f"https://sourceforge.net/projects/{project_id}/files.json"
        raw = _sf_get(url)
        data = json.loads(raw)
        versions = []
        def walk(node, path=""):
            if isinstance(node, dict):
                for name, child in node.items():
                    child_path = f"{path}/{name}" if path else name
                    if isinstance(child, dict):
                        if child.get("type") == "file":
                            size = child.get("size", 0)
                            url_path = f"https://sourceforge.net/projects/{project_id}/files/{child_path}/download"
                            versions.append({
                                "id": child_path,
                                "name": name,
                                "version_number": name,
                                "game_versions": [],
                                "loaders": [],
                                "files": [{"url": url_path, "filename": name, "size": size}],
                                "date": child.get("mtime", ""),
                            })
                        else:
                            walk(child, child_path)
        walk(data)
        return versions[:limit]
    except Exception as e:
        return {"error": str(e)}


def sourceforge_download(file_url, dest_path):
    """Download a file from SourceForge."""
    req = urllib.request.Request(file_url, headers={"User-Agent": UA})
    res = urllib.request.urlopen(req, timeout=120)
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    with open(dest_path, "wb") as f:
        while True:
            chunk = res.read(8192)
            if not chunk:
                break
            f.write(chunk)
    return dest_path
