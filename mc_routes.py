"""All API route definitions for the multi-server web console."""

import json
import queue
import re
import subprocess
import tarfile
import time
from datetime import datetime

from flask import request, Response  # type: ignore
from werkzeug.utils import secure_filename  # type: ignore

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
        inst = mci.create_server(name, jt, mr, mx)
        mc_ver = data.get("mc_version", "")
        if mc_ver:
            forge_ver = data.get("forge_version", "")
            ok_, msg = mc_downloads.download_server_jar(inst.dir, jt, mc_ver, forge_ver)
            if not ok_:
                return ok({"message": f"Server created but download failed: {msg}",
                           "server": inst.to_dict()})
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
                    "path": str(entry.relative_to(inst.dir)),
                    "is_dir": entry.is_dir(),
                    "size": entry.stat().st_size if entry.is_file() else 0,
                    "modified": datetime.fromtimestamp(entry.stat().st_mtime).isoformat(),
                })
            return ok({"items": items, "current": str(target.relative_to(inst.dir))}), None
        elif target.is_file():
            try:
                content = target.read_text(encoding="utf-8", errors="replace")
                return ok({"content": content, "path": str(target.relative_to(inst.dir)), "name": target.name}), None
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
            rel = str(dest.relative_to(inst.dir))
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
        if inst.is_running():
            return fail("Stop the server for some property changes to take effect.")
        ok_, msg = save_props(inst.dir, changes)
        return ok({"message": msg}) if ok_ else fail(msg)

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
        dest_dir = inst.dir / ("resourcepacks" if pack_type == "resourcepack" else "mods")
        dest = dest_dir / filename
        try:
            modrinth_download(file_url, dest)
            return ok({"message": f"Installed {filename}", "path": str(dest.relative_to(inst.dir))})
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
        target = safe_resolve(inst.dir, data.get("path", ""))
        if target is None:
            return fail("Access denied.")
        if not target.exists():
            return fail("File not found.")
        target.unlink()
        return ok({"message": f"Removed {target.name}"})

    # ═══════════════════════════════════════════════════════════════════
    #  PLAYIT.GG TUNNEL
    # ═══════════════════════════════════════════════════════════════════

    @app.route("/api/playit/status")
    def api_playit_status():
        return ok(mc_playit.check_tunnel_status())

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

    @app.route("/api/playit/start", methods=["POST"])
    def api_playit_start():
        ok_, result = mc_playit.start_tunnel()
        if ok_:
            return ok(result)
        return fail(result.get("error", "Tunnel failed to start"))

    @app.route("/api/playit/daemon", methods=["POST"])
    def api_playit_daemon():
        import subprocess as _sp
        if not mc_playit._PLAYITD:
            return fail("playitd not found.")
        try:
            _sp.Popen([mc_playit._PLAYITD], stdout=_sp.DEVNULL, stderr=_sp.DEVNULL, stdin=_sp.DEVNULL)
            return ok({"message": "Daemon started."})
        except Exception as e:
            return fail(str(e))
