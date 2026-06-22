"""SourceForge search integration for browsing modpacks / resource packs.

SourceForge has no public search API, so we scrape the HTML search results
page and use the Allura REST API (/rest/p/{shortname}/) for project details.
File listings are scraped from the project files HTML page.
"""

import json
import re
import urllib.parse
import urllib.request

UA = "mcmanage-termux/1.0"
SF_BASE = "https://sourceforge.net"
SF_REST = f"{SF_BASE}/rest/p"


def _sf_get(url, timeout=15):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    res = urllib.request.urlopen(req, timeout=timeout)
    return res.read()


def _sf_get_html(url, timeout=15):
    return _sf_get(url, timeout).decode("utf-8", "replace")


def sourceforge_search(query, project_type="modpack", limit=20):
    """Search SourceForge projects by scraping the directory search page."""
    try:
        url = f"{SF_BASE}/directory/?q={urllib.parse.quote(query)}"
        html = _sf_get_html(url)

        seen = set()
        for m in re.finditer(r'/projects/([a-zA-Z0-9._-]+)/?', html):
            shortname = m.group(1).removesuffix(".mirror")
            if shortname in seen or shortname in ("forge",):
                continue
            seen.add(shortname)

        results = []
        for shortname in list(seen)[:limit]:
            entry = _get_project_info(shortname, project_type)
            if entry:
                results.append(entry)

        return results
    except Exception as e:
        return {"error": str(e)}


def _get_project_info(shortname, project_type="modpack"):
    """Fetch project metadata from Allura REST endpoint."""
    try:
        url = f"{SF_REST}/{shortname}/"
        raw = _sf_get(url)
        data = json.loads(raw)
        title = data.get("name", shortname)
        desc = data.get("short_description", "") or data.get("summary", "")
        dev_obj = data.get("developers", [])
        if isinstance(dev_obj, list):
            author = ", ".join(
                d.get("username", "") if isinstance(d, dict) else str(d)
                for d in dev_obj[:3]
            )
        else:
            author = str(dev_obj)
        icon = data.get("icon_url", "") or f"{SF_BASE}/p/{shortname}/icon"
        return {
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
        }
    except Exception:
        return {
            "id": shortname,
            "title": shortname,
            "description": "",
            "icon_url": f"{SF_BASE}/p/{shortname}/icon",
            "author": "",
            "downloads": 0,
            "slug": shortname,
            "latest_version": "",
            "project_type": project_type,
            "provider": "sourceforge",
        }


def sourceforge_versions(project_id, limit=20):
    """Scrape file/folder listing from the SourceForge project files HTML page."""
    try:
        url = f"{SF_BASE}/projects/{project_id}/files/"
        try:
            html = _sf_get_html(url)
        except Exception:
            return []

        versions = []
        seen = set()

        for m in re.finditer(
            rf'href="/projects/{re.escape(project_id)}/files/([^"]+)"', html
        ):
            path = m.group(1)
            if path in seen or "/stats/" in path or path.endswith("download"):
                continue
            seen.add(path)

            name = path.rstrip("/").rsplit("/", 1)[-1]
            url_path = f"{SF_BASE}/projects/{project_id}/files/{path}download"

            is_folder = path.endswith("/")

            versions.append({
                "id": path,
                "name": name,
                "version_number": name,
                "game_versions": [],
                "loaders": [],
                "files": [{"url": url_path, "filename": name, "size": 0}],
                "date": "",
            })

            if len(versions) >= limit:
                break

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
