"""Optimized CurseForge integration — fast, no API key needed.

Key optimizations over the old implementation:
  1. Search extracts ALL project data from the search page in ONE request
     (eliminates the N+1 request problem that made it painfully slow)
  2. Version listing uses improved parsing
  3. Results cache to avoid re-fetching the same data
"""

import json
import re
import time
import urllib.parse
import urllib.request

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")
CF_BASE = "https://www.curseforge.com"

CF_BASE_PATHS = {
    "modpack": "/minecraft/modpacks",
    "mod": "/minecraft/mc-mods",
    "resourcepack": "/minecraft/texture-packs",
    "datapack": "/minecraft/data-packs",
    "shader": "/minecraft/shaders",
    "plugin": "/bukkit-plugins",
}

CF_CATEGORIES = {
    "modpack": "modpacks", "mod": "mc-mods",
    "resourcepack": "texture-packs", "datapack": "data-packs",
    "shader": "shaders", "plugin": "bukkit-plugins",
}

# ── Results cache ────────────────────────────────────────────────────
_cache = {}
_CACHE_TTL = 300  # 5 minutes

def _cached(key, ttl=None):
    entry = _cache.get(key)
    if entry and (time.time() - entry["time"]) < (ttl or _CACHE_TTL):
        return entry["value"]
    return None

def _set_cache(key, value):
    _cache[key] = {"value": value, "time": time.time()}

# ── Helpers ──────────────────────────────────────────────────────────

def _cf_get(url, timeout=20):
    req = urllib.request.Request(url, headers={
        "User-Agent": UA,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
        "Referer": "https://www.curseforge.com/",
        "DNT": "1",
    })
    res = urllib.request.urlopen(req, timeout=timeout)
    return res.read().decode("utf-8", "replace")


def _category_path(project_type):
    return CF_CATEGORIES.get(project_type, "mc-mods")

def _base_path(project_type):
    return CF_BASE_PATHS.get(project_type, "/minecraft/mc-mods")

def _parse_download_count(text):
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
#  SEARCH
# ═══════════════════════════════════════════════════════════════════════

def curseforge_search(query, project_type="mod", limit=20):
    """Search CurseForge — parses ALL results from one HTML page."""
    cache_key = f"cf_search:{project_type}:{query}:{limit}"
    cached = _cached(cache_key, ttl=60)
    if cached:
        return cached
    try:
        bp = _base_path(project_type)
        if project_type == "plugin":
            url = f"{CF_BASE}{bp}?search={urllib.parse.quote(query)}"
        else:
            url = f"{CF_BASE}{bp}/search?search={urllib.parse.quote(query)}"
        html = _cf_get(url)
        results = _extract_search_results(html, bp, project_type, limit)
        _set_cache(cache_key, results)
        return results
    except Exception as e:
        return {"error": str(e)}


def _extract_search_results(html, bp, project_type, limit):
    """Parse project cards from search HTML — single pass."""
    results = []
    seen_slugs = set()

    # Split by project-card divs — CurseForge uses <div class="...project-card...">
    cards = re.split(r'<div[^>]*class="[^"]*project-card[^"]*"[^>]*>', html)
    if len(cards) < 2:
        # Fallback: no project-card found
        return results

    for block in cards[1:]:
        if len(results) >= limit:
            break
        if not block.strip():
            continue

        # Get the slug
        m = re.search(r'href="' + re.escape(bp) + r'/([a-zA-Z0-9_-]+)"', block)
        if not m:
            continue
        slug = m.group(1)
        if slug in seen_slugs or slug in ("search", "files", "download"):
            continue
        seen_slugs.add(slug)

        # Title
        title = slug.replace("-", " ").title()
        mt = re.search(r'<a[^>]*class="name"[^>]*>\s*([^<]+?)\s*</a>', block)
        if mt:
            title = mt.group(1).strip()

        # Icon
        icon_url = ""
        mi = re.search(r'<img[^>]*src="([^"]+)"', block)
        if mi:
            icon_url = mi.group(1)
            if icon_url.startswith("//"):
                icon_url = "https:" + icon_url

        # Description
        desc = ""
        for pat in [r'<span[^>]*class="description"[^>]*>\s*([^<]+?)\s*</span>',
                     r'<p[^>]*>\s*([^<]{15,}?)\s*</p>']:
            md = re.search(pat, block, re.IGNORECASE)
            if md:
                desc = md.group(1).strip()
                break

        # Author — from /members/ links in the card block
        author = ""
        ma = re.search(r'href="/members/([^"]+)"', block)
        if ma:
            author = ma.group(1)
        if not author:
            ma = re.search(r'By\s*<a[^>]*>\s*([^<]+?)\s*</a>', block, re.IGNORECASE)
            if ma:
                author = ma.group(1).strip()

        # Downloads
        downloads = 0
        m_dl = re.search(r'"downloadCount":\s*(\d+)', block)
        if not m_dl:
            m_dl = re.search(r'>\s*([\d.]+[KMB]?)\s*</li>', block)
        if m_dl:
            downloads = _parse_download_count(m_dl.group(1))

        results.append({
            "id": slug, "title": title, "slug": slug,
            "author": author, "downloads": downloads, "icon_url": icon_url,
            "description": desc, "latest_version": "",
            "project_type": project_type, "provider": "curseforge",
            "page_url": f"{CF_BASE}{bp}/{slug}",
        })

    return results


# ═══════════════════════════════════════════════════════════════════════
#  VERSIONS
# ═══════════════════════════════════════════════════════════════════════

def curseforge_versions(project_id, project_type="mod", limit=20):
    """Parse available files for a CurseForge project."""
    cache_key = f"cf_versions:{project_type}:{project_id}:{limit}"
    cached = _cached(cache_key, ttl=120)
    if cached:
        return cached
    try:
        bp = _base_path(project_type)
        html = _cf_get(f"{CF_BASE}{bp}/{project_id}")
        versions = _extract_versions(html, bp, project_id, limit)
        _set_cache(cache_key, versions)
        return versions
    except Exception as e:
        return {"error": str(e)}


def _extract_versions(html, bp, project_id, limit):
    """Extract file listings from the project page."""
    versions = []
    seen_ids = set()

    # File IDs from download/file links
    fids = []
    for m in re.finditer(r'/(?:download|files)/(\d+)', html):
        fid = m.group(1)
        if fid not in seen_ids:
            seen_ids.add(fid)
            fids.append(fid)

    fnames = re.findall(r'"fileName":"([^"]*)"', html)
    gvl = re.findall(r'"gameVersions":\[([^\]]*)\]', html)

    for i, fid in enumerate(fids[:limit]):
        fname = fnames[i] if i < len(fnames) else f"file-{fid}"
        gv_raw = gvl[i] if i < len(gvl) else ""
        gv = [v.strip('"') for v in gv_raw.split(",") if v.strip()]
        versions.append({
            "id": fid, "name": fname, "version_number": fname,
            "game_versions": gv, "loaders": [],
            "files": [{"url": f"{CF_BASE}{bp}/{project_id}/download/{fid}",
                       "filename": fname, "size": 0}],
            "date": "",
        })

    return versions


def curseforge_download_url(project_slug, file_id, project_type="mod"):
    bp = _base_path(project_type)
    return f"{CF_BASE}{bp}/{project_slug}/download/{file_id}"
