"""All API route definitions for the Minecraft web console."""

import json
import queue
import re
import tarfile
import time
from datetime import datetime

from flask import request, Response  # type: ignore

import mc_state
from mc_helpers import (
    ok, fail, is_running, safe_resolve, parse_json_body,
    find_jar, get_props,
)
from mc_server import start_minecraft, stop_minecraft, send_minecraft
from mc_properties import PROPS_SCHEMA, save_props
from mc_modrinth import modrinth_search, modrinth_versions, modrinth_download
from mc_sourceforge import sourceforge_search as sf_search, sourceforge_versions as sf_versions
from mc_modrinth import list_installed_packs


def register_routes(app, html):

    # ═══════════════════════════════════════════════════════════════════
    #  INDEX
    # ═══════════════════════════════════════════════════════════════════

    @app.route("/")
    def index():
        return html

    # ═══════════════════════════════════════════════════════════════════
    #  SERVER LIFECYCLE
    # ═══════════════════════════════════════════════════════════════════

    @app.route("/api/status")
    def api_status():
        with mc_state.get_status_lock():
            players = list(mc_state.status_cache["players"])
            online_count = len(players)
        props = get_props()
        return ok({
            "online": mc_state.status_cache["online"],
            "players": players,
            "online_count": online_count,
            "max_players": int(props.get("max-players", 20)),
            "mem_mb": mc_state.status_cache["mem_mb"],
            "uptime": mc_state.status_cache["uptime"],
            "started_at": mc_state.status_cache["started_at"],
            "jar": str(find_jar() or ""),
            "server_dir": str(mc_state.SERVER_DIR),
            "min_ram": mc_state.MIN_RAM,
            "max_ram": mc_state.MAX_RAM,
        })

    @app.route("/api/ram", methods=["GET", "POST"])
    def api_ram():
        if request.method == "GET":
            return ok({"min_ram": mc_state.MIN_RAM, "max_ram": mc_state.MAX_RAM})
        data = parse_json_body()
        new_min = data.get("min_ram", "").strip().upper()
        new_max = data.get("max_ram", "").strip().upper()
        if not re.match(r"^\d+[MG]$", new_min) or not re.match(r"^\d+[MG]$", new_max):
            return fail("Invalid RAM format. Use e.g. 512M, 1G, 2G, 4G")
        if is_running():
            return fail("Stop the server before changing RAM.")
        mc_state.MIN_RAM = new_min
        mc_state.MAX_RAM = new_max
        mc_state.save_config()
        return ok({"message": f"RAM set to {mc_state.MIN_RAM} min / {mc_state.MAX_RAM} max",
                   "min_ram": mc_state.MIN_RAM, "max_ram": mc_state.MAX_RAM})

    @app.route("/api/start", methods=["POST"])
    def api_start():
        ok_, msg = start_minecraft()
        return ok({"message": msg}) if ok_ else fail(msg)

    @app.route("/api/stop", methods=["POST"])
    def api_stop():
        data = parse_json_body()
        ok_, msg = stop_minecraft(int(data.get("seconds", 15)))
        return ok({"message": msg}) if ok_ else fail(msg)

    @app.route("/api/restart", methods=["POST"])
    def api_restart():
        data = parse_json_body()
        stop_minecraft(int(data.get("seconds", 15)))
        time.sleep(2)
        ok_, msg = start_minecraft()
        return ok({"message": msg}) if ok_ else fail(msg)

    @app.route("/api/command", methods=["POST"])
    def api_command():
        data = parse_json_body()
        cmd = data.get("command", "").strip()
        if not cmd:
            return fail("No command provided.")
        ok_, msg = send_minecraft(cmd)
        return ok({"message": msg}) if ok_ else fail(msg)

    # ═══════════════════════════════════════════════════════════════════
    #  CONSOLE (SSE)
    # ═══════════════════════════════════════════════════════════════════

    _console_connections = 0

    @app.route("/api/console")
    def api_console():
        def stream():
            nonlocal _console_connections
            _console_connections += 1
            q = mc_state.console_queue
            hist = mc_state.console_history
            sent = len(hist)
            # Send full history first
            if sent > 0:
                yield f"data: {json.dumps({'lines': hist[:]})}\n\n"
            try:
                while not request.is_disconnected():
                    try:
                        line = q.get(timeout=1)
                        yield f"data: {json.dumps({'lines': [line]})}\n\n"
                    except queue.Empty:
                        yield f"data: {json.dumps({'lines': []})}\n\n"
            finally:
                _console_connections -= 1

        resp = Response(stream(), mimetype="text/event-stream")
        resp.headers["Cache-Control"] = "no-cache"
        resp.headers["X-Accel-Buffering"] = "no"
        resp.headers["Connection"] = "keep-alive"
        return resp

    # ═══════════════════════════════════════════════════════════════════
    #  FILE MANAGER
    # ═══════════════════════════════════════════════════════════════════

    @app.route("/api/files")
    def api_files():
        path_str = request.args.get("path", "")
        target = safe_resolve(path_str)
        if target is None:
            return fail("Access denied.")
        if target.is_dir():
            items = []
            for entry in sorted(target.iterdir()):
                items.append({
                    "name": entry.name,
                    "path": str(entry.relative_to(mc_state.SERVER_DIR)),
                    "is_dir": entry.is_dir(),
                    "size": entry.stat().st_size if entry.is_file() else 0,
                    "modified": datetime.fromtimestamp(entry.stat().st_mtime).isoformat(),
                })
            return ok({"items": items, "current": str(target.relative_to(mc_state.SERVER_DIR))})
        elif target.is_file():
            try:
                content = target.read_text(encoding="utf-8", errors="replace")
                return ok({"content": content, "path": str(target.relative_to(mc_state.SERVER_DIR)), "name": target.name})
            except Exception as e:
                return fail(str(e))
        return fail("Path not found.")

    @app.route("/api/file/save", methods=["POST"])
    def api_file_save():
        data = parse_json_body()
        target = safe_resolve(data.get("path", ""))
        if target is None:
            return fail("Access denied.")
        try:
            target.write_text(data.get("content", ""), encoding="utf-8")
            return ok({"message": "File saved."})
        except Exception as e:
            return fail(str(e))

    # ═══════════════════════════════════════════════════════════════════
    #  BACKUPS
    # ═══════════════════════════════════════════════════════════════════

    @app.route("/api/backup", methods=["POST"])
    def api_backup():
        worlds = [d for d in mc_state.SERVER_DIR.iterdir()
                  if d.is_dir() and ("world" in d.name.lower() or d.name.endswith("-world"))]
        if not worlds:
            return fail("No world directories found.")
        if is_running():
            try:
                mc_state.server_proc.stdin.write("save-all\n")
                mc_state.server_proc.stdin.flush()
            except Exception:
                pass
            time.sleep(2)
        backup_dir = mc_state.SERVER_DIR / "backups"
        backup_dir.mkdir(exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        archive = backup_dir / f"world-backup-{ts}.tar.gz"
        with tarfile.open(str(archive), "w:gz") as tar:
            for d in worlds:
                tar.add(str(d), arcname=d.name)
        size = archive.stat().st_size
        return ok({"message": f"Backup created ({size // 1024} KB)", "file": archive.name})

    @app.route("/api/backups")
    def api_backups():
        backup_dir = mc_state.SERVER_DIR / "backups"
        if not backup_dir.exists():
            return ok({"backups": []})
        files = []
        for f in sorted(backup_dir.glob("world-backup-*.tar.gz"), reverse=True):
            files.append({
                "name": f.name,
                "size": f.stat().st_size // 1024,
                "date": datetime.fromtimestamp(f.stat().st_mtime).isoformat(),
            })
        return ok({"backups": files})

    @app.route("/api/backup/restore", methods=["POST"])
    def api_backup_restore():
        data = parse_json_body()
        archive = safe_resolve("backups/" + data.get("file", ""))
        if archive is None or not archive.exists():
            return fail("Backup not found.")
        if is_running():
            return fail("Stop the server before restoring a backup.")
        with tarfile.open(str(archive), "r:gz") as tar:
            tar.extractall(path=str(mc_state.SERVER_DIR))
        return ok({"message": f"Restored from {data.get('file')}."})

    # ═══════════════════════════════════════════════════════════════════
    #  PROPERTIES EDITOR
    # ═══════════════════════════════════════════════════════════════════

    @app.route("/api/properties", methods=["GET", "POST"])
    def api_properties():
        if request.method == "GET":
            props = get_props()
            rich = {}
            for k, v in props.items():
                entry = dict(PROPS_SCHEMA.get(k, {"type": "string", "cat": "other", "label": k, "desc": ""}))
                entry["key"] = k
                entry["value"] = v
                rich[k] = entry
            for k, s in PROPS_SCHEMA.items():
                if k not in rich:
                    entry = dict(s)
                    entry["key"] = k
                    entry["value"] = s.get("default", "")
                    rich[k] = entry
            return ok({"properties": list(rich.values())})

        data = parse_json_body()
        changes = data.get("changes", {})
        if not changes:
            return fail("No changes provided.")
        if is_running():
            return fail("Stop the server for some property changes to take effect, or restart after saving.")
        ok_, msg = save_props(changes)
        return ok({"message": msg}) if ok_ else fail(msg)

    # ═══════════════════════════════════════════════════════════════════
    #  MODPACKS / RESOURCE PACKS
    # ═══════════════════════════════════════════════════════════════════

    @app.route("/api/packs/search")
    def api_packs_search():
        q = request.args.get("q", "")
        pt = request.args.get("type", "modpack")
        prov = request.args.get("provider", "modrinth")
        if not q:
            return fail("Search query required.")
        if prov == "modrinth":
            results = modrinth_search(q, pt)
        elif prov == "sourceforge":
            results = sf_search(q, pt)
        else:
            return fail(f"Unknown provider: {prov}")
        if isinstance(results, dict) and "error" in results:
            return fail(results["error"])
        return ok({"results": results, "provider": prov, "type": pt})

    @app.route("/api/packs/versions")
    def api_packs_versions():
        pid = request.args.get("id", "")
        prov = request.args.get("provider", "modrinth")
        if not pid:
            return fail("Project ID required.")
        if prov == "modrinth":
            versions = modrinth_versions(pid)
        elif prov == "sourceforge":
            versions = sf_versions(pid)
        else:
            versions = modrinth_versions(pid)
        if isinstance(versions, dict) and "error" in versions:
            return fail(versions["error"])
        return ok({"versions": versions})

    @app.route("/api/packs/install", methods=["POST"])
    def api_packs_install():
        data = parse_json_body()
        file_url = data.get("file_url", "")
        filename = data.get("filename", "pack.zip")
        pack_type = data.get("type", "modpack")
        if not file_url:
            return fail("No file URL provided.")
        dest_dir = mc_state.SERVER_DIR / ("resourcepacks" if pack_type == "resourcepack" else "mods")
        dest = dest_dir / filename
        try:
            modrinth_download(file_url, dest)
        except Exception as e:
            return fail(f"Download failed: {e}")
        return ok({"message": f"Installed {filename}", "path": str(dest.relative_to(mc_state.SERVER_DIR))})

    @app.route("/api/packs/installed")
    def api_packs_installed():
        return ok({"packs": list_installed_packs()})

    @app.route("/api/packs/remove", methods=["POST"])
    def api_packs_remove():
        data = parse_json_body()
        target = safe_resolve(data.get("path", ""))
        if target is None:
            return fail("Access denied.")
        if not target.exists():
            return fail("File not found.")
        target.unlink()
        return ok({"message": f"Removed {target.name}"})
