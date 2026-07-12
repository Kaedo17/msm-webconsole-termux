"""CurseForge integration via public API proxy (like Prism Launcher).

Uses api.curse.tools — a community proxy that mirrors the official
CurseForge API without requiring an API key. Falls back to optimized
HTML scraping if the proxy is unavailable.

Official CurseForge API reference:
  https://docs.curseforge.com/rest-api/

The proxy mirrors the official API at:
  https://api.curse.tools/v1/cf/
"""

import json
import re
import time
import urllib.parse
import urllib.request

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")

# API proxy base — mirrors official CurseForge API without API key
CF_API = "https://api.curse.tools/v1/cf"
CF_BASE = "https://www.curseforge.com"
GAME_ID = 432  # Minecraft

CF_CATEGORY_IDS = {
    "modpack": 4471,
    "mod": 6,
    "resourcepack": 12,
    "datapack": 4545,
    "shader": 4552,
    "plugin": 5,
}

CF_BASE_PATHS = {
    "modpack": "/minecraft/modpacks",
    "mod": "/minecraft/mc-mods",
    "resourcepack": "/minecraft/texture-packs",
    "datapack": "/minecraft/data-packs",
    "shader": "/minecraft/shaders",
    "plugin": "/bukkit-plugins",
}

# ── Cache ────────────────────────────────────────────────────────────
_cache = {}
_CACHE_TTL = 300


def _cached(key, ttl=None):
    entry = _cache.get(key)
    if entry and (time.time() - entry["time"]) < (ttl or _CACHE_TTL):
        return entry["value"]
    return None


def _set_cache(key, value):
    _cache[key] = {"value": value, "time": time.time()}


# ── HTTP helpers ─────────────────────────────────────────────────────

def _api_get(path, timeout=15):
    """Call the proxy API and return parsed JSON."""
    url = f"{CF_API}{path}"
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    res = urllib.request.urlopen(req, timeout=timeout)
    return json.loads(res.read())


def _cf_get_html(url, timeout=20):
    """Fetch HTML from CurseForge (for scraping fallback)."""
    req = urllib.request.Request(url, headers={
        "User-Agent": UA,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
        "Referer": "https://www.curseforge.com/",
        "DNT": "1",
    })
    res = urllib.request.urlopen(req, timeout=timeout)
    return res.read().decode("utf-8", "replace")


def _base_path(project_type):
    return CF_BASE_PATHS.get(project_type, "/minecraft/mc-mods")


def _parse_download_count(text):
    """Parse strings like '594.1M', '19.5K' or numbers."""
    text = text.strip().upper()
    try:
        if text.endswith("M"):
            return int(float(text[:-1]) * 1_000_000)
        elif text.endswith("K"):
            return int(float(text[:-1]) * 1_000)
        elif text.endswith("B"):
            return int(float(text[:-1]) * 1_000_000_000)
        return int(text.replace(",", ""))
    except (ValueError, IndexError):
        return 0


# ═══════════════════════════════════════════════════════════════════════
#  SEARCH — via API proxy
# ═══════════════════════════════════════════════════════════════════════

def curseforge_search(query, project_type="mod", limit=20):
    """Search CurseForge via API proxy (fast JSON)."""
    cache_key = f"cf_api_search:{project_type}:{query}:{limit}"
    cached = _cached(cache_key, ttl=60)
    if cached:
        return cached

    data = _api_search(query, project_type, limit)
    if data is not None:
        _set_cache(cache_key, data)
        return data

    # API failed — fall back to scraping
    return _scrape_search(query, project_type, limit)


def _api_search(query, project_type, limit):
    """Search via API proxy."""
    try:
        expected_class = CF_CATEGORY_IDS.get(project_type, 6)
        path = (f"/mods/search?gameId={GAME_ID}"
                f"&searchFilter={urllib.parse.quote(query)}"
                f"&pageSize={limit}"
                f"&sortOrder=desc")
        data = _api_get(path)
        results = []
        for hit in data.get("data", []):
            if hit.get("classId") != expected_class:
                continue
            results.append({
                "id": str(hit.get("id", "")),
                "title": hit.get("name", ""),
                "slug": hit.get("slug", ""),
                "description": hit.get("summary", ""),
                "author": (hit.get("authors") or [{}])[0].get("name", "") if hit.get("authors") else "",
                "downloads": hit.get("downloadCount", 0),
                "icon_url": hit.get("logo", {}).get("url", "") if hit.get("logo") else "",
                "latest_version": "",
                "project_type": project_type,
                "provider": "curseforge",
                "page_url": hit.get("links", {}).get("websiteUrl", ""),
            })
        return results
    except Exception:
        return None


def _scrape_search(query, project_type, limit):
    """Fallback: find slugs from search page, fetch details via API."""
    try:
        bp = _base_path(project_type)
        search_url = f"{CF_BASE}{bp}/search?search={urllib.parse.quote(query)}"
        html = _cf_get_html(search_url)

        seen = set()
        slugs = []
        for m in re.finditer(rf'{re.escape(bp)}/([a-zA-Z0-9_-]+)', html):
            slug = m.group(1)
            if slug in seen or slug in ("search", "files", "download"):
                continue
            seen.add(slug)
            slugs.append(slug)

        # Look up each slug via API by fetching project page
        results = []
        for slug in slugs[:limit]:
            result = _scrape_project_card(slug, project_type, html)
            if result:
                results.append(result)
        return results
    except Exception as e:
        return {"error": str(e)}


def _scrape_project_card(slug, project_type, search_html=""):
    """Extract a project's info from search HTML (no extra request)."""
    bp = _base_path(project_type)
    title = slug.replace("-", " ").title()
    desc = ""
    icon_url = ""
    author = ""
    downloads = 0

    if search_html:
        # Find the card block containing this slug
        card = re.search(
            rf'href="{re.escape(bp)}/{re.escape(slug)}"[^>]*>.*?(?=<div[^>]*class="[^"]*project-card)',
            search_html, re.DOTALL)
        if card:
            block = card.group()
        else:
            block = search_html

        mt = re.search(r'<a[^>]*class="name"[^>]*>\s*([^<]+?)\s*</a>', block)
        if mt:
            title = mt.group(1).strip()
        mi = re.search(r'<img[^>]*src="([^"]+)"', block)
        if mi:
            icon_url = mi.group(1)
            if icon_url.startswith("//"):
                icon_url = "https:" + icon_url
        for pat in [r'<span[^>]*class="description"[^>]*>\s*([^<]+?)\s*</span>',
                     r'<p[^>]*>\s*([^<]{15,}?)\s*</p>']:
            md = re.search(pat, block, re.IGNORECASE)
            if md:
                desc = md.group(1).strip()
                break
        ma = re.search(r'href="/members/([^"]+)"', block)
        if ma:
            author = ma.group(1)
        m_dl = re.search(r'"downloadCount":\s*(\d+)', block)
        if not m_dl:
            m_dl = re.search(r'>\s*([\d.]+[KMB]?)\s*</li>', block)
        if m_dl:
            downloads = _parse_download_count(m_dl.group(1))

    return {
        "id": slug, "title": title, "slug": slug,
        "author": author, "downloads": downloads, "icon_url": icon_url,
        "description": desc, "latest_version": "",
        "project_type": project_type, "provider": "curseforge",
        "page_url": f"{CF_BASE}{bp}/{slug}",
    }


# ═══════════════════════════════════════════════════════════════════════
#  VERSIONS — via API proxy
# ═══════════════════════════════════════════════════════════════════════

def curseforge_versions(project_id, project_type="mod", limit=20):
    """Fetch available files for a CurseForge project."""
    cache_key = f"cf_api_versions:{project_type}:{project_id}:{limit}"
    cached = _cached(cache_key, ttl=120)
    if cached:
        return cached

    # Try resolving slug to numeric ID if needed
    resolved = project_id
    if not project_id.isdigit():
        resolved = _slug_to_id(project_id)
    data = _api_versions(resolved, limit)
    if data is not None:
        _set_cache(cache_key, data)
        return data
    return []


def _api_versions(project_id, limit):
    """Fetch files via API proxy."""
    try:
        path = f"/mods/{project_id}/files?pageSize={limit}"
        data = _api_get(path)
        versions = []
        for f_item in data.get("data", []):
            gv = f_item.get("gameVersions", [])
            loaders = [v for v in gv if v.lower() in ("forge", "fabric", "neoforge", "quilt", "rift")]
            mc_vers = [v for v in gv if v.lower() not in ("forge", "fabric", "neoforge", "quilt", "rift")]

            file_entry = {
                "url": f_item.get("downloadUrl", ""),
                "filename": f_item.get("fileName", f"file-{f_item.get('id', '')}"),
                "size": f_item.get("fileLength", 0),
            }

            versions.append({
                "id": str(f_item.get("id", "")),
                "name": f_item.get("displayName", f_item.get("fileName", "")),
                "version_number": f_item.get("fileName", f"file-{f_item.get('id', '')}"),
                "game_versions": mc_vers,
                "loaders": loaders,
                "files": [file_entry],
                "date": f_item.get("fileDate", ""),
            })

        return versions
    except Exception:
        return None


def _slug_to_id(slug):
    """Resolve a CurseForge slug to a numeric project ID via the API."""
    try:
        data = _api_get(f"/mods/search?gameId={GAME_ID}&searchFilter={slug}&slug={slug}&pageSize=1")
        hits = data.get("data", [])
        if hits:
            return str(hits[0].get("id", slug))
    except Exception:
        pass
    return slug


def curseforge_download_url(project_slug, file_id, project_type="mod"):
    """Get the download URL for a specific file (via API proxy)."""
    try:
        data = _api_get(f"/mods/{project_slug}/files/{file_id}/download-url")
        if data and "data" in data:
            url = data["data"]
            if url:
                return url
    except Exception:
        pass
    # Fallback: return the CurseForge page URL
    return f"{CF_BASE}{_base_path(project_type)}/{project_slug}/download/{file_id}"
