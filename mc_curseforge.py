"""CurseForge integration via HTML scraping (no API key required).

The official CurseForge API requires an API key. This module scrapes the
public website instead. Search works by parsing mod links from search results.
File listings are parsed from the project page's Next.js SSR data.

Note: CurseForge download URLs are protected by Cloudflare, so downloads
are opened in the user's browser rather than proxied server-side.
"""

import re
import urllib.parse
import urllib.request

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
CF_BASE = "https://www.curseforge.com"

CF_CATEGORIES = {
    "modpack": "modpacks",
    "mod": "mc-mods",
    "resourcepack": "texture-packs",
}


def _cf_get_html(url, timeout=20):
    req = urllib.request.Request(url, headers={
        "User-Agent": UA,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
    })
    res = urllib.request.urlopen(req, timeout=timeout)
    return res.read().decode("utf-8", "replace")


def _parse_next_data(html):
    chunks = re.findall(r'self\.__next_f\.push\(\[1,\s*"(.*?)"\]\)', html, re.DOTALL)
    combined = ""
    for c in chunks:
        combined += c.replace("\\n", "\n").replace('\\"', '"').replace("\\\\", "\\")
    return combined


def _category_path(project_type):
    return CF_CATEGORIES.get(project_type, "mc-mods")


def curseforge_search(query, project_type="mod", limit=20):
    """Search CurseForge by scraping the search results page."""
    try:
        cat = _category_path(project_type)
        url = f"{CF_BASE}/minecraft/{cat}/search?search={urllib.parse.quote(query)}"
        html = _cf_get_html(url)

        slugs = []
        seen = set()
        for m in re.finditer(rf'/minecraft/{re.escape(cat)}/([a-zA-Z0-9_-]+)', html):
            slug = m.group(1)
            if slug in seen or slug in ("search", "files", "download"):
                continue
            seen.add(slug)
            slugs.append(slug)

        results = []
        for slug in slugs[:limit]:
            entry = _get_project_summary(slug, cat, project_type, html)
            results.append(entry)

        return results
    except Exception as e:
        return {"error": str(e)}


def _get_project_summary(slug, cat, project_type, search_html=""):
    base = f"{CF_BASE}/minecraft/{cat}/{slug}"
    title = slug.replace("-", " ").title()
    desc = ""
    icon = ""

    if search_html:
        m_title = re.search(
            rf'href="/minecraft/{re.escape(cat)}/{re.escape(slug)}"[^>]*>.*?>([^<]+)<',
            search_html, re.DOTALL
        )
        if m_title:
            title = m_title.group(1).strip()

    try:
        html = _cf_get_html(base)
        nd = _parse_next_data(html)

        m_title = re.search(r'<title>([^<|]+)', html)
        if m_title:
            title = m_title.group(1).strip()

        m_desc = re.search(r'"summary":"([^"]*)"', nd)
        if m_desc:
            desc = m_desc.group(1)

        m_dl = re.search(r'"downloadCount":(\d+)', nd)
        downloads = int(m_dl.group(1)) if m_dl else 0

        m_icon = re.search(r'"avatarUrl":"([^"]*)"', nd)
        if m_icon:
            icon = m_icon.group(1)

        m_author = re.search(r'"username":"([^"]*)"', nd)
        author = m_author.group(1) if m_author else ""

        return {
            "id": slug,
            "title": title,
            "description": desc,
            "icon_url": icon,
            "author": author,
            "downloads": downloads,
            "slug": slug,
            "latest_version": "",
            "project_type": project_type,
            "provider": "curseforge",
            "page_url": base,
        }
    except Exception:
        return {
            "id": slug,
            "title": title,
            "description": desc,
            "icon_url": icon,
            "author": "",
            "downloads": 0,
            "slug": slug,
            "latest_version": "",
            "project_type": project_type,
            "provider": "curseforge",
            "page_url": base,
        }


def curseforge_versions(project_id, project_type="mod", limit=20):
    """Parse available files from the project page's Next.js SSR data."""
    try:
        cat = _category_path(project_type)
        url = f"{CF_BASE}/minecraft/{cat}/{project_id}"
        try:
            html = _cf_get_html(url)
        except Exception:
            return []

        nd = _parse_next_data(html)

        file_ids = re.findall(rf'/minecraft/{re.escape(cat)}/[a-z0-9_-]+/files/(\d+)', html)
        file_names = re.findall(r'"fileName":"([^"]*)"', nd)
        game_vers = re.findall(r'"gameVersions":\[([^\]]*)\]', nd)

        versions = []
        max_len = max(len(file_ids), len(file_names))

        for i in range(min(max_len, limit)):
            fid = file_ids[i] if i < len(file_ids) else ""
            fname = file_names[i] if i < len(file_names) else f"file-{fid}"
            gv_raw = game_vers[i] if i < len(game_vers) else ""
            gv = [v.strip('"') for v in gv_raw.split(",") if v.strip()]

            page_url = f"{CF_BASE}/minecraft/{cat}/{project_id}/download/{fid}" if fid else ""

            versions.append({
                "id": fid or fname,
                "name": fname,
                "version_number": fname,
                "game_versions": gv,
                "loaders": [],
                "files": [{"url": page_url, "filename": fname, "size": 0}],
                "date": "",
            })

        return versions
    except Exception as e:
        return {"error": str(e)}
