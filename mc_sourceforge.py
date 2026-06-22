"""SourceForge search integration for browsing modpacks / resource packs."""

import json
import urllib.parse
import urllib.request

UA = "mcmanage-termux/1.0"

SF_API = "https://sourceforge.net/rest"


def _sf_get(url, timeout=15):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    res = urllib.request.urlopen(req, timeout=timeout)
    return res.read()


def sourceforge_search(query, project_type="modpack", limit=20):
    """Search SourceForge projects via the Allura REST API."""
    try:
        url = (f"{SF_API}/p/"
               f"?q={urllib.parse.quote(query)}"
               f"&limit={limit}"
               f"&private=false&public=true&deleted=false")
        raw = _sf_get(url)
        data = json.loads(raw)
        hits = []
        for item in data.get("projects", [])[:limit]:
            shortname = item.get("shortname", "")
            title = item.get("name", shortname)
            desc = item.get("short_description", "") or item.get("summary", "")
            dev_obj = item.get("developers", [])
            if isinstance(dev_obj, list):
                author = ", ".join(
                    d.get("username", "") if isinstance(d, dict) else str(d)
                    for d in dev_obj[:3]
                )
            else:
                author = str(dev_obj)
            icon = item.get("icon_url", "")
            if not icon:
                icon = f"https://sourceforge.net/p/{shortname}/icon"
            hits.append({
                "id": shortname,
                "title": title,
                "description": desc,
                "icon_url": icon,
                "author": author,
                "downloads": 0,
                "slug": shortname,
                "latest_version": "",
                "project_type": project_type,
                "provider": "sourceforge",
            })
        return hits
    except Exception as e:
        return {"error": str(e)}


def sourceforge_versions(project_id, limit=20):
    """Fetch available files for a SourceForge project via the Allura REST API."""
    try:
        url = f"{SF_API}/p/{project_id}/files/"
        raw = _sf_get(url)
        data = json.loads(raw)
        versions = []

        def walk(node, path=""):
            if not isinstance(node, dict):
                return
            for entry in node.get("filenames", {}).values() if isinstance(node.get("filenames"), dict) else []:
                _extract_file(entry, project_id, versions)
            for child in node.get("folders", []):
                if isinstance(child, dict):
                    child_path = child.get("path", path)
                    walk(child, child_path)
            for child in node.get("files", []):
                if isinstance(child, dict):
                    _extract_file(child, project_id, versions, path)

        def _extract_file(entry, project_id, versions, path_prefix=""):
            name = entry.get("name", entry.get("filename", ""))
            if not name:
                return
            size = entry.get("size", 0)
            file_path = entry.get("path", f"{path_prefix}/{name}" if path_prefix else name)
            url_path = (f"https://sourceforge.net/projects/{project_id}"
                        f"/files/{file_path}/download")
            versions.append({
                "id": file_path,
                "name": name,
                "version_number": name,
                "game_versions": [],
                "loaders": [],
                "files": [{"url": url_path, "filename": name, "size": size}],
                "date": entry.get("mod_date", entry.get("date", "")),
            })

        walk(data)
        if not versions:
            for entry in data.get("filenames", {}).values():
                _extract_file(entry, project_id, versions)
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
