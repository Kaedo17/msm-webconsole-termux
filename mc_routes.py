"""All API route definitions for the multi-server web console."""

import json
import queue
import re
import socket
import subprocess
import tarfile
import time
from datetime import datetime

from flask import request, Response  # type: ignore
from pathlib import Path
from werkzeug.utils import secure_filename  # type: ignore

def _get_local_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


import mc_instances as mci
import mc_state
from mc_helpers import ok, fail, parse_json_body, safe_resolve, get_props
from mc_server import start_server, stop_server, send_server
from mc_properties import PROPS_SCHEMA, save_props
from mc_modrinth import modrinth_search, modrinth_versions, modrinth_download, list_installed_packs
from mc_curseforge import curseforge_search as cf_search, curseforge_versions as cf_versions
import mc_downloads
import mc_playit


def _resolve(sid):
    inst = mci.get_server(sid)
    if not inst:
        return None
    return inst


def register_routes(app, html):

    @app.route("/")
    def index():
        return html

    # ═══════════════════════════════════════════════════════════════════
    #  SERVER REGISTRY
    # ═══════════════════════════════════════════════════════════════════

    @app.route("/api/servers", methods=["GET", "POST"])
    def api_servers():
        if request.method == "GET":
            return ok({"servers": [s.to_dict() for s in mci.all_servers()]})
        data = parse_json_body()
        name = data.get("name", "").strip()
        if not name:
            return fail("Server name required.")
        jt = data.get("jar_type", "vanilla")
        mr = data.get("min_ram", "512M").strip().upper()
        mx = data.get("max_ram", "2G").strip().upper()
        if not re.match(r"^\d+[MG]$", mr) or not re.match(r"^\d+[MG]$", mx):
            return fail("Invalid RAM format.")
        mc_ver = data.get("mc_version", "") or mc_downloads.get_latest_minecraft_version()
        inst = mci.create_server(name, jt, mr, mx, mc_version=mc_ver)
        if data.get("eula"):
            (inst.dir / "eula.txt").write_text("eula=true\n")
        seed = data.get("level_seed", "")
        if seed:
            props_path = inst.dir / "server.properties"
            if props_path.exists():
                save_props(inst.dir, {"level-seed": seed})
            else:
                props_path.write_text(f"level-seed={seed}\n")
        if mc_ver:
            forge_ver = data.get("forge_version", "")
            ok_, msg = mc_downloads.download_server_jar(inst.dir, jt, mc_ver, forge_ver)
            if not ok_:
                return ok({"message": f"Server created but download failed: {msg}",
                           "server": inst.to_dict(), "download_error": True})
        return ok({"message": f"Server '{name}' created.", "server": inst.to_dict()})

    @app.route("/api/versions")
    def api_versions():
        st = request.args.get("type", "vanilla")
        versions = mc_downloads.get_versions(st)
        types = [{"id": t, **mc_downloads.install_type_details(t)} for t in mc_downloads.SERVER_TYPES]
        return ok({"versions": versions, "types": types})

    @app.route("/api/versions/forge")
    def api_forge_versions():
        mc_ver = request.args.get("mc_version", "")
        versions = mc_downloads.get_forge_versions(mc_ver) if mc_ver else []
        return ok({"forge_versions": versions})

    @app.route("/api/servers/import", methods=["POST"])
    def api_server_import():
        data = parse_json_body()
        path = data.get("path", "").strip()
        name = data.get("name", "").strip() or None
        if not path:
            return fail("Path required.")
        inst, msg = mci.import_server(path, name)
        if inst is None:
            return fail(msg)
        return ok({"message": msg, "server": inst.to_dict()})

    @app.route("/api/servers/<sid>", methods=["GET", "DELETE"])
    def api_server(sid):
        inst = _resolve(sid)
        if not inst:
            return fail("Server not found.", 404)
        if request.method == "DELETE":
            ok_, msg = mci.delete_server(sid)
            return ok({"message": msg}) if ok_ else fail(msg)
        return ok({"server": inst.to_dict()})

    # ═══════════════════════════════════════════════════════════════════
    #  SERVER LIFECYCLE
    # ═══════════════════════════════════════════════════════════════════

    @app.route("/api/servers/<sid>/status")
    def api_status(sid):
        inst = _resolve(sid)
        if not inst:
            return fail("Server not found.", 404)
        props = get_props(inst.dir)
        s = inst.status_dict()
        s["max_players"] = int(props.get("max-players", 20))
        s["server_port"] = int(props.get("server-port", inst.port))
        s["local_ip"] = _get_local_ip()
        return ok(s)

    @app.route("/api/servers/<sid>/ram", methods=["GET", "POST"])
    def api_ram(sid):
        inst = _resolve(sid)
        if not inst:
            return fail("Server not found.", 404)
        if request.method == "GET":
            return ok({"min_ram": inst.min_ram, "max_ram": inst.max_ram})
        data = parse_json_body()
        new_min = data.get("min_ram", "").strip().upper()
        new_max = data.get("max_ram", "").strip().upper()
        if not re.match(r"^\d+[MG]$", new_min) or not re.match(r"^\d+[MG]$", new_max):
            return fail("Invalid RAM format.")
        if inst.is_running():
            return fail("Stop the server before changing RAM.")
        inst.min_ram = new_min
        inst.max_ram = new_max
        inst.save_config()
        return ok({"message": f"RAM set to {inst.min_ram} min / {inst.max_ram} max"})

    @app.route("/api/servers/<sid>/start", methods=["POST"])
    def api_start(sid):
        inst = _resolve(sid)
        if not inst:
            return fail("Server not found.", 404)
        ok_, msg = start_server(inst)
        return ok({"message": msg}) if ok_ else fail(msg)

    @app.route("/api/servers/<sid>/stop", methods=["POST"])
    def api_stop(sid):
        inst = _resolve(sid)
        if not inst:
            return fail("Server not found.", 404)
        data = parse_json_body()
        ok_, msg = stop_server(inst, int(data.get("seconds", 15)))
        return ok({"message": msg}) if ok_ else fail(msg)

    @app.route("/api/servers/<sid>/java", methods=["GET", "POST"])
    def api_java(sid):
        inst = _resolve(sid)
        if not inst:
            return fail("Server not found.", 404)
        if request.method == "GET":
            java_opts = mc_state.detect_java_versions()
            return ok({
                "java_bin": inst.java_bin if inst.java_bin else "",
                "mc_version": inst.mc_version,
                "java_version": inst.status_dict().get("java_version", "Java (default)"),
                "java_options": [{"ver": k, "path": v} for k, v in sorted(java_opts.items(), key=lambda x: int(x[0]) if x[0].isdigit() else 0)],
            })
        data = parse_json_body()
        new_java_bin = data.get("java_bin", "").strip()
        if new_java_bin and not Path(new_java_bin).exists():
            return fail(f"Java binary not found: {new_java_bin}")
        if inst.is_running():
            return fail("Stop the server before changing Java.")
        inst.java_bin = new_java_bin
        inst.save_config()
        msg = f"Java set to {new_java_bin}" if new_java_bin else "Java set to auto-detect"
        return ok({"message": msg})

    @app.route("/api/servers/<sid>/restart", methods=["POST"])
    def api_restart(sid):
        inst = _resolve(sid)
        if not inst:
            return fail("Server not found.", 404)
        data = parse_json_body()
        stop_server(inst, int(data.get("seconds", 15)))
        time.sleep(2)
        ok_, msg = start_server(inst)
        return ok({"message": msg}) if ok_ else fail(msg)

    @app.route("/api/servers/<sid>/command", methods=["POST"])
    def api_command(sid):
        inst = _resolve(sid)
        if not inst:
            return fail("Server not found.", 404)
        data = parse_json_body()
        cmd = data.get("command", "").strip()
        if not cmd:
            return fail("No command provided.")
        ok_, msg = send_server(inst, cmd)
        return ok({"message": msg}) if ok_ else fail(msg)

    # ═══════════════════════════════════════════════════════════════════
    #  CONSOLE (SSE) — per-server
    # ═══════════════════════════════════════════════════════════════════

    @app.route("/api/servers/<sid>/console")
    def api_console(sid):
        inst = _resolve(sid)
        if not inst:
            return fail("Server not found.", 404)

        def stream():
            q = inst.console_queue
            try:
                hist = inst.console_history
                if hist:
                    try:
                        yield f"data: {json.dumps({'type': 'history', 'lines': hist[:]})}\n\n"
                    except Exception:
                        pass
                while True:
                    try:
                        if request.is_disconnected():
                            break
                    except Exception:
                        break
                    try:
                        line = q.get(timeout=5)
                        yield f"data: {json.dumps({'type': 'new', 'lines': [line]})}\n\n"
                    except queue.Empty:
                        yield ": heartbeat\n\n"
            except Exception:
                pass

        resp = Response(stream(), mimetype="text/event-stream")
        resp.headers["Cache-Control"] = "no-cache"
        resp.headers["X-Accel-Buffering"] = "no"
        resp.headers["Connection"] = "keep-alive"
        return resp

    @app.route("/api/servers/<sid>/console/clear", methods=["POST"])
    def api_console_clear(sid):
        inst = _resolve(sid)
        if not inst:
            return fail("Server not found.", 404)
        with inst.lock:
            inst.console_history.clear()
        return ok({"message": "Console cleared."})

    # ═══════════════════════════════════════════════════════════════════
    #  FILE MANAGER — per-server
    # ═══════════════════════════════════════════════════════════════════

    def _file_list(inst, path_str=""):
        target = safe_resolve(inst.dir, path_str)
        if target is None:
            return None, "Access denied."
        if target.is_dir():
            items = []
            for entry in sorted(target.iterdir()):
                items.append({
                    "name": entry.name,
                    "path": str(entry.relative_to(inst.dir)).replace("\\", "/"),
                    "is_dir": entry.is_dir(),
                    "size": entry.stat().st_size if entry.is_file() else 0,
                    "modified": datetime.fromtimestamp(entry.stat().st_mtime).isoformat(),
                })
            return ok({"items": items, "current": str(target.relative_to(inst.dir)).replace("\\", "/")}), None
        elif target.is_file():
            try:
                content = target.read_text(encoding="utf-8", errors="replace")
                return ok({"content": content, "path": str(target.relative_to(inst.dir)).replace("\\", "/"), "name": target.name}), None
            except Exception as e:
                return None, str(e)
        return None, "Path not found."

    @app.route("/api/servers/<sid>/files")
    def api_files(sid):
        inst = _resolve(sid)
        if not inst:
            return fail("Server not found.", 404)
        r, err = _file_list(inst, request.args.get("path", ""))
        return r if r else fail(err)

    @app.route("/api/servers/<sid>/file/save", methods=["POST"])
    def api_file_save(sid):
        inst = _resolve(sid)
        if not inst:
            return fail("Server not found.", 404)
        data = parse_json_body()
        target = safe_resolve(inst.dir, data.get("path", ""))
        if target is None:
            return fail("Access denied.")
        try:
            target.write_text(data.get("content", ""), encoding="utf-8")
            return ok({"message": "File saved."})
        except Exception as e:
            return fail(str(e))

    @app.route("/api/servers/<sid>/file/copy", methods=["POST"])
    def api_file_copy(sid):
        inst = _resolve(sid)
        if not inst:
            return fail("Server not found.", 404)
        data = parse_json_body()
        src = data.get("source", "")
        dst = data.get("destination", "")
        if not src or not dst:
            return fail("Source and destination required.")
        src_path = safe_resolve(inst.dir, src)
        dst_path = safe_resolve(inst.dir, dst)
        if src_path is None or dst_path is None:
            return fail("Access denied.")
        if not src_path.exists():
            return fail("Source not found.")
        if dst_path.exists():
            return fail("Destination already exists.")
        try:
            import shutil
            if src_path.is_dir():
                shutil.copytree(str(src_path), str(dst_path))
            else:
                shutil.copy2(str(src_path), str(dst_path))
            return ok({"message": f"Copied to {dst}"})
        except Exception as e:
            return fail(str(e))

    @app.route("/api/servers/<sid>/file/move", methods=["POST"])
    def api_file_move(sid):
        inst = _resolve(sid)
        if not inst:
            return fail("Server not found.", 404)
        data = parse_json_body()
        src = data.get("source", "")
        dst = data.get("destination", "")
        if not src or not dst:
            return fail("Source and destination required.")
        src_path = safe_resolve(inst.dir, src)
        dst_path = safe_resolve(inst.dir, dst)
        if src_path is None or dst_path is None:
            return fail("Access denied.")
        if not src_path.exists():
            return fail("Source not found.")
        if dst_path.exists():
            return fail("Destination already exists.")
        try:
            src_path.rename(dst_path)
            return ok({"message": f"Moved to {dst}"})
        except Exception as e:
            return fail(str(e))

    @app.route("/api/servers/<sid>/file/delete", methods=["POST"])
    def api_file_delete(sid):
        inst = _resolve(sid)
        if not inst:
            return fail("Server not found.", 404)
        data = parse_json_body()
        target = safe_resolve(inst.dir, data.get("path", ""))
        if target is None:
            return fail("Access denied.")
        if not target.exists():
            return fail("File or folder not found.")
        if target == inst.dir.resolve():
            return fail("Cannot delete server root.")
        try:
            if target.is_dir():
                import shutil
                shutil.rmtree(str(target))
            else:
                target.unlink()
            return ok({"message": f"Deleted {target.name}"})
        except Exception as e:
            return fail(f"Delete failed: {e}")

    @app.route("/api/servers/<sid>/upload", methods=["POST"])
    def api_upload(sid):
        inst = _resolve(sid)
        if not inst:
            return fail("Server not found.", 404)
        if "file" not in request.files:
            return fail("No file provided.")
        f = request.files["file"]
        if not f.filename:
            return fail("No filename.")
        filename = secure_filename(f.filename)
        if not filename:
            filename = "uploaded_file"
        dest_dir_str = request.form.get("dest", "")
        dest_dir = safe_resolve(inst.dir, dest_dir_str) if dest_dir_str else inst.dir
        if dest_dir is None:
            return fail("Access denied.")
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / filename
        try:
            f.save(str(dest))
            rel = str(dest.relative_to(inst.dir)).replace("\\", "/")
            return ok({"message": f"Uploaded {filename}", "path": rel, "name": filename,
                       "size": dest.stat().st_size})
        except Exception as e:
            return fail(f"Upload failed: {e}")

    # ═══════════════════════════════════════════════════════════════════
    #  BACKUPS — per-server
    # ═══════════════════════════════════════════════════════════════════

    @app.route("/api/servers/<sid>/backup", methods=["POST"])
    def api_backup(sid):
        inst = _resolve(sid)
        if not inst:
            return fail("Server not found.", 404)
        worlds = [d for d in inst.dir.iterdir()
                  if d.is_dir() and ("world" in d.name.lower() or d.name.endswith("-world"))]
        if not worlds:
            return fail("No world directories found.")
        if inst.is_running():
            try:
                inst.proc.stdin.write("save-all\n")
                inst.proc.stdin.flush()
            except Exception:
                pass
            time.sleep(2)
        backup_dir = inst.dir / "backups"
        backup_dir.mkdir(exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        archive = backup_dir / f"world-backup-{ts}.tar.gz"
        with tarfile.open(str(archive), "w:gz") as tar:
            for d in worlds:
                tar.add(str(d), arcname=d.name)
        size = archive.stat().st_size
        return ok({"message": f"Backup created ({size // 1024} KB)", "file": archive.name})

    @app.route("/api/servers/<sid>/backups")
    def api_backups(sid):
        inst = _resolve(sid)
        if not inst:
            return fail("Server not found.", 404)
        backup_dir = inst.dir / "backups"
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

    @app.route("/api/servers/<sid>/backup/restore", methods=["POST"])
    def api_backup_restore(sid):
        inst = _resolve(sid)
        if not inst:
            return fail("Server not found.", 404)
        data = parse_json_body()
        archive = safe_resolve(inst.dir, "backups/" + data.get("file", ""))
        if archive is None or not archive.exists():
            return fail("Backup not found.")
        if inst.is_running():
            return fail("Stop the server before restoring a backup.")
        with tarfile.open(str(archive), "r:gz") as tar:
            tar.extractall(path=str(inst.dir))
        return ok({"message": f"Restored from {data.get('file')}."})

    # ═══════════════════════════════════════════════════════════════════
    #  PLAYER MANAGEMENT — per-server
    # ═══════════════════════════════════════════════════════════════════

    def _read_player_file(inst, filename):
        """Read a Minecraft JSON player file, return list of dicts or []. Handles missing/invalid files."""
        path = inst.dir / filename
        if not path.exists():
            return []
        try:
            data = json.loads(path.read_text())
            return data if isinstance(data, list) else []
        except (json.JSONDecodeError, Exception):
            return []

    def _build_player_list(inst):
        """Merge usercache, whitelist, bans, ops into a unified player list."""
        usercache = _read_player_file(inst, "usercache.json")
        whitelist = _read_player_file(inst, "whitelist.json")
        banned = _read_player_file(inst, "banned-players.json")
        ops = _read_player_file(inst, "ops.json")

        # Preserve original casing: lowercase -> original name
        whitelist_map = {p.get("name", "").lower(): p.get("name", "") for p in whitelist}
        banned_map = {p.get("name", "").lower(): p.get("name", "") for p in banned}
        ops_map = {p.get("name", "").lower(): p.get("name", "") for p in ops}

        online_players = list(inst.status_cache.get("players", []))
        online_set = {p.lower() for p in online_players}

        # Build a name map: lowercase -> (preferred name, uuid)
        # Priority for preferred name: ops > whitelist > banned > usercache
        # This ensures the most authoritative source's casing is used.
        seen = set()
        name_map = {}

        # Collect all known names with their preferred source
        for entry in usercache:
            nl = entry.get("name", "").lower()
            if nl and nl not in name_map:
                name_map[nl] = {"name": entry.get("name", ""), "uuid": entry.get("uuid", "")}
        for entry in whitelist:
            nl = entry.get("name", "").lower()
            if nl:
                name_map[nl] = {"name": entry.get("name", ""), "uuid": entry.get("uuid", "")}
        for entry in banned:
            nl = entry.get("name", "").lower()
            if nl:
                name_map[nl] = {"name": entry.get("name", ""), "uuid": entry.get("uuid", "")}
        for entry in ops:
            nl = entry.get("name", "").lower()
            if nl:
                name_map[nl] = {"name": entry.get("name", ""), "uuid": entry.get("uuid", "")}

        # Also add online players not already known
        for name in online_players:
            nl = name.lower()
            if nl not in name_map:
                name_map[nl] = {"name": name, "uuid": ""}

        # Build the final list
        players = []
        for nl, info in name_map.items():
            players.append({
                "name": info["name"],
                "uuid": info["uuid"],
                "online": nl in online_set,
                "whitelisted": nl in whitelist_map,
                "banned": nl in banned_map,
                "op": nl in ops_map,
            })

        return players

    @app.route("/api/servers/<sid>/players")
    def api_players_list(sid):
        inst = _resolve(sid)
        if not inst:
            return fail("Server not found.", 404)
        players = _build_player_list(inst)
        return ok({"players": players, "online_count": len([p for p in players if p["online"]])})

    def _write_player_file(inst, filename, data):
        """Write a list of dicts to a Minecraft JSON player file."""
        path = inst.dir / filename
        try:
            path.write_text(json.dumps(data, indent=2))
            return True
        except Exception:
            return False

    def _offline_uuid(name):
        """Generate the standard offline-mode UUID for a player name.

        Minecraft's offline UUID = UUID.nameUUIDFromBytes(("OfflinePlayer:" + name).getBytes())
        which is MD5 hash formatted as a version-3 UUID.
        """
        import hashlib
        import uuid
        md5 = hashlib.md5(f"OfflinePlayer:{name}".encode("utf-8")).digest()
        md5_arr = bytearray(md5)
        md5_arr[6] = (md5_arr[6] & 0x0f) | 0x30   # version 3
        md5_arr[8] = (md5_arr[8] & 0x3f) | 0x80   # RFC 4122 variant
        return str(uuid.UUID(bytes=bytes(md5_arr)))

    def _add_whitelist_entry(inst, name):
        entries = _read_player_file(inst, "whitelist.json")
        # Check if already there
        if any(e.get("name", "").lower() == name.lower() for e in entries):
            return False, f"{name} is already whitelisted."
        offline_uuid = _offline_uuid(name)
        entries.append({"uuid": offline_uuid, "name": name})
        if _write_player_file(inst, "whitelist.json", entries):
            return True, f"{name} added to whitelist."
        return False, "Failed to write whitelist.json."

    def _remove_whitelist_entry(inst, name):
        entries = _read_player_file(inst, "whitelist.json")
        filtered = [e for e in entries if e.get("name", "").lower() != name.lower()]
        if len(filtered) == len(entries):
            return False, f"{name} is not whitelisted."
        if _write_player_file(inst, "whitelist.json", filtered):
            return True, f"{name} removed from whitelist."
        return False, "Failed to write whitelist.json."

    def _add_ban_entry(inst, name):
        entries = _read_player_file(inst, "banned-players.json")
        if any(e.get("name", "").lower() == name.lower() for e in entries):
            return False, f"{name} is already banned."
        from datetime import datetime, timezone
        entries.append({
            "uuid": "",
            "name": name,
            "created": datetime.now(timezone.utc).isoformat(),
            "source": "Web Console",
            "expires": "forever",
            "reason": "Banned by an operator."
        })
        if _write_player_file(inst, "banned-players.json", entries):
            # Also remove from whitelist if present
            _remove_whitelist_entry(inst, name)
            return True, f"{name} banned."
        return False, "Failed to write banned-players.json."

    def _remove_ban_entry(inst, name):
        entries = _read_player_file(inst, "banned-players.json")
        filtered = [e for e in entries if e.get("name", "").lower() != name.lower()]
        if len(filtered) == len(entries):
            return False, f"{name} is not banned."
        if _write_player_file(inst, "banned-players.json", filtered):
            return True, f"{name} unbanned."
        return False, "Failed to write banned-players.json."

    def _add_op_entry(inst, name):
        entries = _read_player_file(inst, "ops.json")
        if any(e.get("name", "").lower() == name.lower() for e in entries):
            return False, f"{name} is already an operator."
        offline_uuid = _offline_uuid(name)
        entries.append({"uuid": offline_uuid, "name": name, "level": 4})
        if _write_player_file(inst, "ops.json", entries):
            return True, f"{name} opped."
        return False, "Failed to write ops.json."

    def _remove_op_entry(inst, name):
        entries = _read_player_file(inst, "ops.json")
        filtered = [e for e in entries if e.get("name", "").lower() != name.lower()]
        if len(filtered) == len(entries):
            return False, f"{name} is not an operator."
        if _write_player_file(inst, "ops.json", filtered):
            return True, f"{name} deopped."
        return False, "Failed to write ops.json."

    def _add_usercache_entry(inst, name):
        """Add a player to usercache.json so they appear in the player list."""
        entries = _read_player_file(inst, "usercache.json")
        if any(e.get("name", "").lower() == name.lower() for e in entries):
            return False, f"{name} already in known players."
        offline_uuid = _offline_uuid(name)
        entries.append({"uuid": offline_uuid, "name": name})
        if _write_player_file(inst, "usercache.json", entries):
            return True, f"{name} added to known players."
        return False, "Failed to write usercache.json."

    def _remove_player_completely(inst, name):
        """Remove a player from all server files: usercache, whitelist, ops, banned."""
        removed_from = []
        for filename in ["usercache.json", "whitelist.json", "ops.json", "banned-players.json"]:
            entries = _read_player_file(inst, filename)
            filtered = [e for e in entries if e.get("name", "").lower() != name.lower()]
            if len(filtered) < len(entries):
                if _write_player_file(inst, filename, filtered):
                    removed_from.append(filename)
        if removed_from:
            return True, f"{name} removed from: {', '.join(removed_from)}"
        return False, f"{name} not found in any player files."

    @app.route("/api/servers/<sid>/players/send", methods=["POST"])
    def api_players_send(sid):
        """Generic endpoint to run a command for player management (whitelist, ban, etc.)."""
        inst = _resolve(sid)
        if not inst:
            return fail("Server not found.", 404)
        data = parse_json_body()
        cmd = data.get("command", "").strip()
        name = data.get("name", "").strip()
        add_only = data.get("add_only", False)
        if not cmd:
            return fail("No command provided.")

        # If server is online, send the command via console
        if inst.is_running():
            if name:
                full_cmd = f"{cmd} {name}"
            else:
                full_cmd = cmd
            ok_, msg = send_server(inst, full_cmd)
            return ok({"message": msg}) if ok_ else fail(msg)

        # Server is offline — modify JSON files directly
        cmd_lower = cmd.lower().strip()
        if cmd_lower == "whitelist add":
            ok_, msg = _add_whitelist_entry(inst, name)
        elif cmd_lower == "whitelist remove":
            ok_, msg = _remove_whitelist_entry(inst, name)
        elif cmd_lower == "ban":
            ok_, msg = _add_ban_entry(inst, name)
        elif cmd_lower == "pardon":
            ok_, msg = _remove_ban_entry(inst, name)
        elif cmd_lower == "op":
            ok_, msg = _add_op_entry(inst, name)
        elif cmd_lower == "deop":
            ok_, msg = _remove_op_entry(inst, name)
        elif cmd_lower == "kick":
            return ok({"message": "Cannot kick when server is offline.", "offline": True})
        elif cmd_lower == "remove":
            ok_, msg = _remove_player_completely(inst, name)
        elif add_only or cmd_lower == "add":
            ok_, msg = _add_usercache_entry(inst, name)
        else:
            ok_, msg = _add_usercache_entry(inst, name)

        return ok({"message": msg}) if ok_ else fail(msg)

    # ═══════════════════════════════════════════════════════════════════
    #  PROPERTIES EDITOR — per-server
    # ═══════════════════════════════════════════════════════════════════

    @app.route("/api/servers/<sid>/properties", methods=["GET", "POST"])
    def api_properties(sid):
        inst = _resolve(sid)
        if not inst:
            return fail("Server not found.", 404)
        if request.method == "GET":
            props = get_props(inst.dir)
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
        ok_, msg = save_props(inst.dir, changes)
        resp = {"message": msg}
        if ok_ and inst.is_running():
            resp["restart_required"] = True
        return ok(resp) if ok_ else fail(msg)

    # ═══════════════════════════════════════════════════════════════════
    #  MODPACKS / RESOURCE PACKS — per-server
    # ═══════════════════════════════════════════════════════════════════

    @app.route("/api/servers/<sid>/packs/search")
    def api_packs_search(sid):
        inst = _resolve(sid)
        if not inst:
            return fail("Server not found.", 404)
        q = request.args.get("q", "")
        pt = request.args.get("type", "modpack")
        prov = request.args.get("provider", "modrinth")
        if not q:
            return fail("Search query required.")
        if prov == "modrinth":
            results = modrinth_search(q, pt)
        elif prov == "curseforge":
            results = cf_search(q, pt)
        else:
            return fail(f"Unknown provider: {prov}")
        if isinstance(results, dict) and "error" in results:
            return fail(results["error"])
        return ok({"results": results, "provider": prov, "type": pt})

    @app.route("/api/servers/<sid>/packs/versions")
    def api_packs_versions(sid):
        inst = _resolve(sid)
        if not inst:
            return fail("Server not found.", 404)
        pid = request.args.get("id", "")
        pt = request.args.get("type", "mod")
        prov = request.args.get("provider", "modrinth")
        if not pid:
            return fail("Project ID required.")
        if prov == "modrinth":
            versions = modrinth_versions(pid)
        elif prov == "curseforge":
            versions = cf_versions(pid, pt)
        else:
            versions = modrinth_versions(pid)
        if isinstance(versions, dict) and "error" in versions:
            return fail(versions["error"])
        return ok({"versions": versions})

    @app.route("/api/servers/<sid>/packs/install", methods=["POST"])
    def api_packs_install(sid):
        inst = _resolve(sid)
        if not inst:
            return fail("Server not found.", 404)
        data = parse_json_body()
        file_url = data.get("file_url", "")
        filename = data.get("filename", "pack.zip")
        pack_type = data.get("type", "modpack")
        if not file_url:
            return fail("No file URL provided.")
        pack_dirs = {
            "modpack": "mods",
            "mod": "mods",
            "resourcepack": "resourcepacks",
            "datapack": "datapacks",
            "shader": "shaderpacks",
            "plugin": "plugins",
            "server": ".",
        }
        dest_subdir = pack_dirs.get(pack_type, "mods")
        dest_dir = inst.dir / dest_subdir
        dest = dest_dir / filename
        try:
            downloaded = modrinth_download(file_url, dest)

            if pack_type == "modpack" and dest.suffix == ".zip":
                import threading as _thr
                import json
                import zipfile
                import urllib.request
                import shutil
                from mc_helpers import create_progress, update_progress

                tid = create_progress()

                def _run():
                    try:
                        extracted = []
                        mods_downloaded = 0
                        mods_failed = 0
                        total_mods = 0
                        mods_dir = inst.dir / "mods"
                        mods_dir.mkdir(exist_ok=True)
                        update_progress(tid, status="running", phase="extracting", message="Extracting overrides...")

                        with zipfile.ZipFile(str(dest), "r") as zf:
                            entries = [e for e in zf.infolist() if not e.filename.endswith("/")]

                            # Detect a common root directory wrapper (e.g. "cursed-walking-server/")
                            # so we can strip it and extract content directly to the right places.
                            strip_prefix = ""
                            if entries:
                                first_seg = entries[0].filename.split("/")[0]
                                if first_seg and all(e.filename.startswith(first_seg + "/") for e in entries):
                                    strip_prefix = first_seg + "/"

                            total_entries = len(entries)
                            for idx, entry in enumerate(entries):
                                update_progress(tid, current=idx+1, total=total_entries,
                                                phase="extracting", message=f"Extracting {entry.filename}")
                                # Strip the common root folder for prefix matching and target paths
                                raw = entry.filename
                                rel = raw[len(strip_prefix):] if strip_prefix else raw
                                if rel.startswith("overrides/"):
                                    rel = rel[10:]
                                    if rel:
                                        target = inst.dir / rel
                                        target.parent.mkdir(parents=True, exist_ok=True)
                                        target.write_bytes(zf.read(raw))
                                        extracted.append(rel)
                                elif rel.startswith("server-overrides/"):
                                    rel = rel[17:]
                                    if rel:
                                        target = inst.dir / rel
                                        target.parent.mkdir(parents=True, exist_ok=True)
                                        target.write_bytes(zf.read(raw))
                                        extracted.append(rel)
                                elif rel.startswith("mods/"):
                                    rel = rel[5:]
                                    if rel:
                                        target = mods_dir / rel
                                        target.parent.mkdir(parents=True, exist_ok=True)
                                        target.write_bytes(zf.read(raw))
                                        extracted.append(rel)

                            for fld in ["overrides", "server-overrides", "client-overrides"]:
                                shutil.rmtree(str(inst.dir / fld), ignore_errors=True)

                            # Download mods from manifest
                            if "manifest.json" in zf.namelist():
                                manifest = json.loads(zf.read("manifest.json"))
                                mod_files = manifest.get("files", [])
                                total_mods = len(mod_files)
                                update_progress(tid, phase="downloading", message=f"Downloading 0/{total_mods} mods...")

                                if mod_files:
                                    from mc_curseforge import curseforge_get_files
                                    import concurrent.futures
                                    cf_ua = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                                             "AppleWebKit/537.36")

                                    # Resolve ALL file IDs in one batch call
                                    file_ids = [mf.get("fileID", 0) for mf in mod_files if mf.get("fileID")]
                                    file_map = curseforge_get_files(file_ids)

                                    # Download each file concurrently
                                    _dl_lock = _thr.Lock()

                                    def _dl_one(mf):
                                        fid = mf.get("fileID", 0)
                                        info = file_map.get(fid, {})
                                        du = info.get("downloadUrl", "") if info else ""
                                        fn = info.get("filename", f"file-{fid}.jar") if info else f"file-{fid}"
                                        if not du:
                                            return False, fn  # API returned no URL
                                        try:
                                            dq = urllib.request.Request(du, headers={"User-Agent": cf_ua})
                                            dr = urllib.request.urlopen(dq, timeout=45)
                                            jp = mods_dir / fn
                                            jp.parent.mkdir(parents=True, exist_ok=True)
                                            with open(jp, "wb") as jf:
                                                while True:
                                                    c = dr.read(65536)
                                                    if not c:
                                                        break
                                                    jf.write(c)
                                            return True, fn
                                        except Exception:
                                            return False, fn

                                    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
                                        futs = [pool.submit(_dl_one, mf) for mf in mod_files]
                                        done_count = 0
                                        for f in concurrent.futures.as_completed(futs):
                                            ok_mod, name = f.result()
                                            with _dl_lock:
                                                if ok_mod:
                                                    mods_downloaded += 1
                                                else:
                                                    mods_failed += 1
                                                done_count = mods_downloaded + mods_failed
                                                update_progress(tid, current=done_count,
                                                                total=total_mods, phase="downloading",
                                                                message=f"Downloading mods ({done_count}/{total_mods})")

                        modpacks_ref = inst.dir / "modpacks" / filename
                        modpacks_ref.parent.mkdir(parents=True, exist_ok=True)
                        if dest.exists():
                            dest.rename(modpacks_ref)

                        msg = (f"Installed modpack ({len(extracted)} overrides, "
                               f"{mods_downloaded}/{total_mods} mods")
                        if mods_failed:
                            msg += f", {mods_failed} failed"
                        msg += ")"
                        update_progress(tid, status="done", phase="done", message=msg,
                                        done=True, current=total_entries, total=total_entries)

                    except Exception as e:
                        update_progress(tid, status="error", phase="error",
                                        message=f"Failed: {e}", error=str(e), done=True)

                _thr.Thread(target=_run, daemon=True).start()
                return ok({"task_id": tid, "message": "Modpack install started"})

            return ok({"message": f"Installed {filename}", "path": str(dest.relative_to(inst.dir)).replace("\\", "/")})
        except Exception as e:
            err = str(e)
            if "403" in err or "Forbidden" in err:
                return jsonify({"ok": False, "error": "blocked", "url": file_url, "filename": filename}), 200
            return fail(f"Download failed: {err}")

    @app.route("/api/servers/<sid>/packs/installed")
    def api_packs_installed(sid):
        inst = _resolve(sid)
        if not inst:
            return fail("Server not found.", 404)
        return ok({"packs": list_installed_packs(inst.dir)})

    @app.route("/api/servers/<sid>/packs/remove", methods=["POST"])
    def api_packs_remove(sid):
        inst = _resolve(sid)
        if not inst:
            return fail("Server not found.", 404)
        data = parse_json_body()
        paths = data.get("paths", data.get("path", None))
        if paths is None:
            return fail("No path provided.")
        if isinstance(paths, str):
            paths = [paths]
        if not paths:
            return fail("No paths provided.")
        removed = []
        errors = []
        for p in paths:
            target = safe_resolve(inst.dir, p)
            if target is None:
                errors.append(f"Access denied: {p}")
            elif not target.exists():
                errors.append(f"Not found: {p}")
            else:
                target.unlink()
                removed.append(target.name)
        if removed and errors:
            return ok({"message": f"Removed {len(removed)}, {len(errors)} errors", "removed": removed, "errors": errors})
        if removed:
            return ok({"message": f"Removed {len(removed)} file(s)", "removed": removed})
        return fail(errors[0] if errors else "No files removed.")



    @app.route("/api/packs/install/status/<task_id>")
    def api_packs_install_status(task_id):
        from mc_helpers import get_progress
        p = get_progress(task_id)
        if p is None:
            return fail("Task not found.", 404)
        return ok({"progress": p})

    # ═══════════════════════════════════════════════════════════════════
    #  PLAYIT.GG TUNNEL
    # ═══════════════════════════════════════════════════════════════════

    @app.route("/api/playit/status")
    def api_playit_status():
        return ok(mc_playit.check_tunnel_status())

    @app.route("/api/playit/info")
    def api_playit_info():
        return ok(mc_playit.get_tunnel_info())

    @app.route("/api/playit/logs")
    def api_playit_logs():
        n = int(request.args.get("n", "100"))
        return ok({"logs": mc_playit.get_logs(n)})

    @app.route("/api/playit/install", methods=["POST"])
    def api_playit_install():
        cmds = mc_playit.install_commands()
        results = []
        for cmd in cmds:
            try:
                subprocess.run(cmd, shell=True, check=True, timeout=120)
                results.append({"cmd": cmd, "ok": True})
            except Exception as e:
                results.append({"cmd": cmd, "ok": False, "error": str(e)})
        installed = mc_playit.is_installed()
        return ok({"installed": installed, "steps": results})

    @app.route("/api/playit/daemon", methods=["POST"])
    def api_playit_daemon():
        ok_, msg = mc_playit.start_daemon()
        if ok_:
            return ok({"message": msg})
        return fail(msg)

    @app.route("/api/playit/daemon/stop", methods=["POST"])
    def api_playit_daemon_stop():
        ok_, msg = mc_playit.stop_daemon()
        if ok_:
            return ok({"message": msg})
        return fail(msg)

    @app.route("/api/playit/cli", methods=["POST"])
    def api_playit_cli():
        ok_, out, lines = mc_playit.run_cli()
        if not ok_:
            return fail(out)
        url, code = mc_playit.parse_claim_url(lines)
        tunnels = mc_playit.parse_tunnel_urls(lines)
        result = {"lines": lines, "raw": out}
        if url:
            result["claim_url"] = url
            result["claim_code"] = code
        if tunnels:
            result["tunnels"] = tunnels
        if "already claimed" in out.lower() or "agent" in out.lower():
            result["claimed"] = True
        return ok(result)

    @app.route("/api/config")
    def api_config_get():
        """Return the current webconsole config (no secrets by default)."""
        cfg = mc_state.load_config()
        return ok({
            "has_cf_api_key": bool(cfg.get("curseforge_api_key", "")),
            "curseforge_api_key": cfg.get("curseforge_api_key", ""),
        })

    @app.route("/api/config", methods=["PUT"])
    def api_config_put():
        """Update webconsole config fields."""
        data = parse_json_body()
        if not data:
            return fail("No data provided.")
        allowed = {"curseforge_api_key"}
        changes = {k: v for k, v in data.items() if k in allowed}
        if not changes:
            return fail("No valid fields to update.")
        cfg = mc_state.load_config()
        cfg.update(changes)
        if mc_state.save_config(cfg):
            mc_state.clear_config_cache()
            return ok({"message": "Settings saved."})
        return fail("Failed to save config.")

    # ═══════════════════════════════════════════════════════════════════
    #  JAVA AUTO-INSTALL (Windows desktop)
    # ═══════════════════════════════════════════════════════════════════

    @app.route("/api/java/install", methods=["POST"])
    def api_java_install():
        """Download and install Eclipse Temurin JDK alongside the app."""
        from mc_helpers import create_progress, update_progress, get_progress
        import io, zipfile, urllib.request, uuid

        # Determine install directory (alongside the EXE or in cwd/data)
        app_dir = Path(mc_state.SCRIPT_DIR)
        java_dir = app_dir / "data" / "jdk"
        java_dir.mkdir(parents=True, exist_ok=True)

        tid = create_progress()
        update_progress(tid, status="running", phase="downloading", message="Starting download...", current=0, total=100)

        def _run_install():
            try:
                update_progress(tid, phase="downloading", message="Downloading Eclipse Temurin JDK 21...")

                # Adoptium API redirects to the latest Temurin JDK 21 zip
                dl_url = "https://api.adoptium.net/v3/binary/latest/21/ga/windows/x64/jdk/hotspot/normal/eclipse"
                req = urllib.request.Request(dl_url, headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                    "Accept": "application/octet-stream",
                })
                with urllib.request.urlopen(req, timeout=300) as resp:
                    total_size = int(resp.headers.get("Content-Length", 0))
                    downloaded = 0
                    chunks = []
                    while True:
                        chunk = resp.read(65536)
                        if not chunk:
                            break
                        chunks.append(chunk)
                        downloaded += len(chunk)
                        if total_size > 0:
                            pct = int(downloaded * 100 / total_size)
                            update_progress(tid, current=pct, message=f"Downloading... {downloaded // 1048576} MB / {total_size // 1048576} MB")

                data = b"".join(chunks)
                update_progress(tid, phase="extracting", message="Extracting JDK...", current=90)

                # Extract zip to java_dir
                with zipfile.ZipFile(io.BytesIO(data)) as zf:
                    # Find the root folder name in the zip
                    root_folders = set()
                    for name in zf.namelist():
                        parts = name.split("/")
                        if parts[0]:
                            root_folders.add(parts[0])
                    root = root_folders.pop() if root_folders else "jdk"

                    # Extract
                    zf.extractall(str(java_dir))

                # Find the java.exe inside the extracted JDK
                extracted_jdk = java_dir / root
                java_exe = extracted_jdk / "bin" / "java.exe"
                if not java_exe.exists():
                    # Search for it
                    for f in java_dir.rglob("java.exe"):
                        java_exe = f
                        break

                if java_exe.exists():
                    from mc_state import clear_java_cache
                    clear_java_cache()
                    # Save the installed Java path globally as default
                    java_path_str = str(java_exe.resolve())
                    # Re-scan so the next detect_java_versions call finds it
                    clear_java_cache()
                    update_progress(tid, status="done", phase="done",
                                    message=f"Java installed at {java_path_str}", done=True,
                                    java_path=java_path_str)
                else:
                    update_progress(tid, status="error", phase="error",
                                    message="Extracted JDK but could not find java.exe", done=True)

            except Exception as e:
                update_progress(tid, status="error", phase="error",
                                message=f"Install failed: {e}", error=str(e), done=True)

        import threading as _thr
        _thr.Thread(target=_run_install, daemon=True).start()

        return ok({"task_id": tid, "message": "Java install started"})

    @app.route("/api/java/install/status/<task_id>")
    def api_java_install_status(task_id):
        from mc_helpers import get_progress
        p = get_progress(task_id)
        if p is None:
            return fail("Task not found.", 404)
        return ok({"progress": p})
