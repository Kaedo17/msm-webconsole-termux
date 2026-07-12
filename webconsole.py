#!/data/data/com.termux/files/usr/bin/python3
"""
webconsole.py — Minecraft Web Manager for Termux
Usage:  python webconsole.py [--dir /path/to/servers] [--port 5000]

Modules:
  mc_state.py       — web app config
  mc_helpers.py     — utility helpers
  mc_instances.py   — per-server instance management
  mc_server.py      — server process management
  mc_routes.py      — all API route definitions
"""

import argparse
import sys
from pathlib import Path

_SCRIPT_DIR = str(Path(__file__).resolve().parent)
if _SCRIPT_DIR not in sys.path:
    sys.path.insert(0, _SCRIPT_DIR)

try:
    from flask import Flask
except ImportError:
    import subprocess
    print("Installing Flask...")
    subprocess.check_call([sys.executable, "-m", "pip", "install", "flask"])
    from flask import Flask

import mc_state

# ═══════════════════════════════════════════════════════════════════════
#  Create Flask app — MUST come before route imports
# ═══════════════════════════════════════════════════════════════════════

app = Flask(__name__)

# ═══════════════════════════════════════════════════════════════════════
#  HTML template (single-page app, embedded for zero-dependency deploy)
# ═══════════════════════════════════════════════════════════════════════

HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Minecraft Web Console</title>
<style>
  *{margin:0;padding:0;box-sizing:border-box}
  :root{--bg:#0f0f0f;--bg2:#1a1a1a;--bg3:#111;--border:#2a2a2a;--text:#e0e0e0;--text2:#888;--green:#5ced73;--red:#ff4444;--blue:#1565c0;--radius:6px}
  html,body{height:100%}
  body{font-family:'Segoe UI',system-ui,sans-serif;background:var(--bg);color:var(--text);display:flex;overflow:hidden}
  ::-webkit-scrollbar{width:6px}
  ::-webkit-scrollbar-track{background:#1a1a1a}
  ::-webkit-scrollbar-thumb{background:#333;border-radius:3px}
  .sidebar{width:260px;background:var(--bg2);border-right:1px solid var(--border);display:flex;flex-direction:column;flex-shrink:0;z-index:40;transition:transform .25s}
  .sidebar h2{padding:18px 16px;font-size:15px;font-weight:600;color:#aaa;text-transform:uppercase;letter-spacing:1px;border-bottom:1px solid var(--border)}
  .sidebar nav{flex:1;overflow-y:auto;padding:8px 0}
  .sidebar nav a{display:flex;align-items:center;gap:10px;padding:10px 18px;color:#bbb;text-decoration:none;font-size:14px;transition:.15s;border-left:3px solid transparent;min-height:44px}
  .sidebar nav a:hover{background:#222;color:#fff}
  .sidebar nav a.active{background:#1e2a1e;color:var(--green);border-left-color:var(--green)}
  .sidebar-overlay{display:none;position:fixed;inset:0;background:rgba(0,0,0,.5);z-index:35}
  .main{flex:1;display:flex;flex-direction:column;min-width:0}
  .topbar{display:flex;align-items:center;gap:8px;padding:8px 16px;background:var(--bg2);border-bottom:1px solid var(--border);flex-shrink:0;min-height:48px}
  .menu-toggle{display:none;align-items:center;justify-content:center;background:none;border:none;cursor:pointer;border-radius:4px;flex-shrink:0;width:36px;height:36px;position:relative}
  .menu-toggle:hover{background:#222}
  .menu-toggle .bar{position:absolute;left:8px;right:8px;height:2px;background:var(--text);border-radius:2px;transition:transform .2s}
  .menu-toggle .bar:nth-child(1){top:11px}
  .menu-toggle .bar:nth-child(2){top:17px}
  .menu-toggle .bar:nth-child(3){top:23px}
  .topbar .dot{width:10px;height:10px;border-radius:50%;display:inline-block;flex-shrink:0}
  .dot.green{background:var(--green);box-shadow:0 0 6px #5ced7380}
  .dot.red{background:var(--red);box-shadow:0 0 6px #ff444480}
  .topbar .stat{padding:4px 10px;border-radius:4px;font-size:12px;white-space:nowrap}
  .topbar .stat.mem{background:#1e3a2e;color:var(--green)}
  .topbar .stat.players{background:#2a1e3a;color:#b388ff}
  .topbar .stat.uptime{background:#1e2a3a;color:#64b5f6}
  .content{flex:1;overflow-y:auto;overflow-x:hidden;padding:20px;-webkit-overflow-scrolling:touch;overscroll-behavior:contain}
  .page{display:none}
  .page.active{display:block}
  .server-actions{display:flex;gap:8px;margin-bottom:16px;flex-wrap:wrap}
  .btn{padding:10px 20px;border:none;border-radius:var(--radius);font-size:14px;font-weight:600;cursor:pointer;transition:.15s;display:inline-flex;align-items:center;gap:6px;white-space:nowrap}
  .btn:disabled{opacity:.4;cursor:not-allowed}
  .btn-start{background:#2e7d32;color:#fff}.btn-start:hover{background:#388e3c}
  .btn-stop{background:#c62828;color:#fff}.btn-stop:hover{background:#d32f2f}
  .btn-restart{background:#e65100;color:#fff}.btn-restart:hover{background:#ef6c00}
  .btn-cmd{background:var(--blue);color:#fff}.btn-cmd:hover{background:#1976d2}
  .btn-backup{background:#4a148c;color:#fff}.btn-backup:hover{background:#6a1b9a}
  .btn-save{background:#00695c;color:#fff}.btn-save:hover{background:#00796b}
  .btn-secondary{background:#333;color:#ccc}.btn-secondary:hover{background:#444;color:#fff}
  .btn-danger{background:#7f0000;color:#fff}.btn-danger:hover{background:#b71c1c}
  .console-wrap{background:#0a0a0a;border:1px solid var(--border);border-radius:8px;overflow:hidden}
  .console-header{display:flex;justify-content:space-between;align-items:center;padding:8px 12px;background:var(--bg3);border-bottom:1px solid var(--border);font-size:12px;color:var(--text2)}
  .console{height:400px;overflow-y:auto;padding:12px 16px;font-family:'JetBrains Mono','Cascadia Code','Fira Code',monospace;font-size:13px;line-height:1.5;white-space:pre-wrap;word-break:break-all;color:#ccc}
  .console .ts{color:#666;margin-right:8px}
  .console .info{color:#4fc3f7}
  .console .warn{color:#ffd54f}
  .console .err,.console .error{color:#ef5350}
  .console .done{color:#69f0ae}
  .console .say{color:#ce93d8}
  .cmd-bar{display:flex;gap:8px;padding:10px 12px;background:var(--bg3);border-top:1px solid var(--border)}
  .cmd-bar input{flex:1;padding:8px 12px;background:var(--bg2);border:1px solid #333;border-radius:4px;color:var(--text);font-family:monospace;font-size:13px;outline:none;min-width:0}
  .cmd-bar input:focus{border-color:var(--green)}
  .file-browser{display:flex;gap:1px;height:calc(100vh - 180px);min-height:300px;background:var(--bg2);border:1px solid var(--border);border-radius:8px;overflow:hidden}
  .file-tree{width:220px;overflow-y:auto;background:var(--bg3);padding:8px 0;flex-shrink:0}
  .file-tree .fi{padding:8px 14px;font-size:13px;cursor:pointer;color:#aaa;transition:.1s;min-height:36px;display:flex;align-items:center;gap:4px;overflow:hidden}
  .file-tree .fi:hover{background:#222;color:#fff}
  .file-tree .fi.folder{color:#fdd835}
  .file-tree .fi.file{color:#90caf9}
  .file-tree .fi.active{background:#1e2a1e;color:var(--green)}
  .file-tree .fi-act{margin-left:auto;display:inline-flex;gap:2px;opacity:0;transition:.15s;flex-shrink:0}
  .file-tree .fi:hover .fi-act{opacity:1}
  .file-tree .fi-act span{padding:2px 5px;border-radius:3px;cursor:pointer;color:#555;font-size:11px;line-height:1}
  .file-tree .fi-act span:hover{color:#4fc3f7;background:#1a2a3a}
  .file-tree .fi-act span.fi-mv:hover{color:#ffd54f;background:#2a2a1a}
  .file-tree .fi-name{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
  .file-editor{flex:1;display:flex;flex-direction:column;min-width:0}
  .file-editor .fe-header{padding:8px 12px;background:#151515;border-bottom:1px solid var(--border);font-size:13px;color:var(--text2);display:flex;justify-content:space-between;align-items:center;gap:8px;flex-wrap:wrap}
  .file-editor textarea{flex:1;background:#0d0d0d;border:none;color:var(--text);font-family:monospace;font-size:13px;padding:12px;resize:none;outline:none;tab-size:2;width:100%}
  .file-editor .fe-actions{padding:8px 12px;background:#151515;border-top:1px solid var(--border);display:flex;gap:8px}
  .backups-list{display:grid;gap:8px}
  .backup-item{display:flex;justify-content:space-between;align-items:center;padding:12px 16px;background:var(--bg2);border:1px solid var(--border);border-radius:var(--radius);gap:8px}
  .backup-item .bi-info{font-size:13px;min-width:0}
  .backup-item .bi-info strong{color:#ccc}
  .backup-item .bi-info span{color:var(--text2);margin-left:8px}
  .toast{position:fixed;bottom:16px;left:50%;transform:translateX(-50%);padding:12px 20px;border-radius:var(--radius);font-size:14px;z-index:100;opacity:0;transition:opacity .3s;pointer-events:none;text-align:center;max-width:90vw}
  .toast.show{opacity:1}
  .toast.success{background:#2e7d32;color:#fff}
  .toast.error{background:#b71c1c;color:#fff}
  .toast.info{background:var(--blue);color:#fff}
  .loading{text-align:center;padding:40px;color:#666}
  .status-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px;margin-bottom:20px}
  .stat-card{padding:14px;background:var(--bg2);border:1px solid var(--border);border-radius:8px;text-align:center}
  .stat-card .sc-val{font-size:22px;font-weight:700;margin-top:4px}
  .stat-card .sc-label{font-size:11px;color:var(--text2);text-transform:uppercase;letter-spacing:1px}
  .modal{display:none;position:fixed;inset:0;background:rgba(0,0,0,.7);z-index:50;align-items:center;justify-content:center;padding:12px}
  .modal.show{display:flex}
  .modal-box{background:var(--bg2);border:1px solid #333;border-radius:8px;padding:20px;min-width:320px;max-width:100%;max-height:90vh;overflow-y:auto}
  .modal-box h3{margin-bottom:14px;font-size:16px}
  .modal-box input{width:100%;padding:8px 12px;background:var(--bg3);border:1px solid #333;border-radius:4px;color:var(--text);margin-bottom:10px;outline:none}
  .modal-box input:focus{border-color:var(--green)}
  .modal-box select{width:100%;padding:8px 12px;background:var(--bg3);border:1px solid #333;border-radius:4px;color:var(--text);outline:none}
  .modal-box select:focus{border-color:var(--green)}
  .modal-actions{display:flex;gap:8px;justify-content:flex-end;flex-wrap:wrap}
  .props-cat{margin-bottom:16px}
  .props-cat h4{font-size:12px;color:var(--text2);text-transform:uppercase;letter-spacing:1px;margin-bottom:8px;padding-bottom:5px;border-bottom:1px solid var(--border)}
  .prop-row{display:flex;align-items:center;justify-content:space-between;padding:8px 10px;background:#151515;border:1px solid var(--border);border-radius:4px;margin-bottom:5px;gap:8px}
  .prop-row .pr-label{font-size:13px;min-width:0;flex-shrink:1}
  .prop-row .pr-label small{display:block;font-size:11px;color:#666;margin-top:1px}
  .toggle{position:relative;width:44px;height:24px;flex-shrink:0}
  .toggle input{opacity:0;width:0;height:0}
  .toggle .slider{position:absolute;cursor:pointer;inset:0;background:#333;border-radius:12px;transition:.2s}
  .toggle .slider::before{content:"";position:absolute;width:18px;height:18px;border-radius:50%;background:#888;top:3px;left:3px;transition:.2s}
  .toggle input:checked+.slider{background:#2e7d32}
  .toggle input:checked+.slider::before{background:#fff;transform:translateX(20px)}
  .prop-row select,.prop-row input[type=number],.prop-row input[type=text]{padding:6px 8px;background:var(--bg3);border:1px solid #333;border-radius:4px;color:var(--text);font-size:13px;outline:none;max-width:160px;min-width:80px}
  .prop-row select:focus,.prop-row input:focus{border-color:var(--green)}
  .pack-search-bar{display:flex;gap:8px;margin-bottom:12px;flex-wrap:wrap}
  .pack-search-bar input{flex:1;min-width:180px;padding:10px 12px;background:var(--bg3);border:1px solid #333;border-radius:var(--radius);color:var(--text);font-size:14px;outline:none}
  .pack-search-bar input:focus{border-color:var(--green)}
  .pack-search-bar select{padding:10px 12px;background:var(--bg3);border:1px solid #333;border-radius:var(--radius);color:var(--text);font-size:14px;outline:none}
  .pack-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(260px,1fr));gap:10px}
  .pack-card{background:var(--bg2);border:1px solid var(--border);border-radius:8px;padding:12px;display:flex;gap:10px;transition:.15s}
  .pack-card:hover{border-color:#444}
  .pack-card img{width:48px;height:48px;border-radius:6px;flex-shrink:0;object-fit:cover;background:var(--bg3)}
  .pack-card .pc-body{flex:1;min-width:0}
  .pack-card .pc-body h4{font-size:14px;margin-bottom:4px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
  .pack-card .pc-body p{font-size:12px;color:var(--text2);display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}
  .pack-card .pc-body .pc-meta{font-size:11px;color:#666;margin-top:5px}
  .pack-card .pc-body .pc-meta span{margin-right:8px}
  .pack-subnav{display:flex;gap:8px;margin-bottom:12px;flex-wrap:wrap}
  .pack-subnav button{padding:8px 16px;border:1px solid #333;border-radius:var(--radius);background:var(--bg2);color:#aaa;font-size:13px;cursor:pointer}
  .pack-subnav button.active{background:#2e7d32;color:#fff;border-color:#2e7d32}
  .installed-list{display:grid;gap:8px}
  .installed-item{display:flex;justify-content:space-between;align-items:center;padding:10px 12px;background:var(--bg2);border:1px solid var(--border);border-radius:var(--radius);gap:8px}
  .installed-item .ii-info{font-size:13px;min-width:0}
  .installed-item .ii-info strong{color:#ccc}
  .installed-item .ii-info span{color:var(--text2);margin-left:8px}
  .search-status{padding:12px;text-align:center;color:#666;font-size:13px}
  .dropzone{border:2px dashed #444;border-radius:8px;padding:20px;text-align:center;color:var(--text2);cursor:pointer;transition:.2s;margin-bottom:12px}
  .dropzone:hover,.dropzone.dragover{border-color:var(--green);color:var(--green);background:#1a2a1a}
  .dropzone input{display:none}
  .upload-progress{font-size:12px;color:var(--text2);margin-top:6px}
  .server-picker{padding:10px 12px;border-bottom:1px solid var(--border)}
  .server-picker select{width:100%;padding:8px 10px;background:var(--bg3);border:1px solid #333;border-radius:4px;color:var(--text);font-size:13px;outline:none}
  .server-picker select:focus{border-color:var(--green)}
  .server-picker .sp-dot{display:inline-block;width:8px;height:8px;border-radius:50%;margin-right:6px}
  .server-picker .sp-dot.green{background:var(--green);box-shadow:0 0 4px #5ced7380}
  .server-picker .sp-dot.red{background:var(--red);box-shadow:0 0 4px #ff444480}
  .servers-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(260px,1fr));gap:10px}
  .server-card{background:var(--bg2);border:1px solid var(--border);border-radius:8px;padding:14px;transition:.15s}
  .server-card:hover{border-color:#444}
  .server-card h3{font-size:15px;margin-bottom:6px}
  .server-card .sc-meta{font-size:12px;color:var(--text2)}
  .server-card .sc-meta span{margin-right:10px}
  .server-card .sc-actions{margin-top:10px;display:flex;gap:6px;flex-wrap:wrap}
  /* ── Responsive (tablets & smaller) ── */
  @media(max-width:768px){
    .menu-toggle{display:flex}
    .sidebar{position:fixed;top:0;left:0;bottom:0;width:280px;padding-top:env(safe-area-inset-top,0px);padding-bottom:env(safe-area-inset-bottom,0px);transform:translateX(-100%);will-change:transform;transition:transform .2s cubic-bezier(.4,0,.2,1);box-shadow:2px 0 12px rgba(0,0,0,.4)}
    .sidebar.open{transform:translateX(0)}
    .sidebar-overlay{display:block;transition:opacity .2s;opacity:0;pointer-events:none}
    .sidebar-overlay.open{opacity:1;pointer-events:auto}
    .sidebar h2{font-size:14px;padding:14px 16px;padding-top:calc(14px + env(safe-area-inset-top,0px))}
    .sidebar nav a{padding:14px 18px;font-size:15px}
    .sidebar nav{-webkit-overflow-scrolling:touch}
    .content{padding:16px;-webkit-overflow-scrolling:touch;overscroll-behavior:contain}
    .topbar{padding:8px 12px;gap:6px;overflow:hidden}
    .topbar .stat{padding:3px 8px;font-size:11px}
    .topbar .stat.players,.topbar .stat.uptime{display:none}
    .topbar #statusLabel{font-size:13px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;max-width:80px}
    .btn{padding:12px 18px;font-size:14px}
    .server-actions{gap:8px;margin-bottom:14px}
    .modal-box{min-width:0!important;width:100%!important;margin:0;border-radius:12px;padding:20px;max-height:85vh}
    .file-browser{flex-direction:column;height:auto;min-height:auto;border-radius:0;border-left:none;border-right:none}
    .file-tree{width:100%;max-height:180px;border-bottom:1px solid var(--border);border-radius:0}
    .file-editor{min-height:40vh}
    .file-editor textarea{min-height:25vh;font-size:14px;padding:14px}
    .console{height:35vh;padding:10px 14px;font-size:13px}
    .console-header{padding:6px 12px;flex-wrap:wrap;gap:4px}
    .cmd-bar{padding:8px 12px}
    .cmd-bar input{font-size:16px;padding:10px 12px}
    .prop-row{flex-direction:column;align-items:stretch;gap:8px;padding:10px 12px}
    .prop-row .pr-label{font-size:14px}
    .prop-row .pr-label small{display:inline;margin-left:6px;font-size:11px}
    .prop-row select,.prop-row input[type=number],.prop-row input[type=text]{max-width:100%;width:100%;padding:10px 12px;font-size:14px}
    .pack-search-bar input{min-width:140px}
    .pack-search-bar select{flex:1;min-width:0}
    .pack-search-bar input,.pack-search-bar select{padding:12px 14px;font-size:14px}
    .pack-grid{grid-template-columns:1fr}
    .servers-grid{grid-template-columns:1fr}
    .status-grid{grid-template-columns:repeat(2,1fr);gap:8px}
    .stat-card{padding:14px}
    .stat-card .sc-val{font-size:20px}
    .stat-card .sc-label{font-size:11px}
    .backup-item{flex-direction:column;gap:10px;align-items:stretch;padding:14px 16px}
    .backup-item .bi-info{text-align:center;font-size:14px}
    .backup-item .bi-info span{display:block;margin:4px 0 0}
    .installed-item{flex-direction:column;gap:10px;align-items:stretch;text-align:center;padding:14px 16px}
    .installed-item .ii-info{font-size:14px}
    .installed-item .ii-info span{display:block;margin:4px 0 0}
    .backups-list{grid-template-columns:1fr}
    .pack-card{padding:14px}
    .pack-card .pc-body h4{font-size:15px}
    .pack-card .pc-body p{font-size:13px}
    .server-card{padding:16px}
    .server-card h3{font-size:15px}
    .server-card .sc-meta{font-size:13px}
    .server-picker select{font-size:15px;padding:10px 12px}
    .dropzone{padding:20px}
    .toast{bottom:16px;left:16px;right:16px;transform:none;max-width:none;font-size:14px;padding:14px 18px;border-radius:10px}
    table{word-break:break-word}
    td{display:block;padding:6px 0!important}
    td:first-child{color:var(--text2)}
    td+td{padding-left:0!important}
    [style*="display:flex"][style*="margin-top:10px"]:not(.server-actions):not(.pack-search-bar):not(.pack-subnav){flex-wrap:wrap!important}
    [style*="display:flex"][style*="gap:12px"]{flex-wrap:wrap!important}
    #versionFilters{flex-direction:column!important}
    .pack-subnav button{flex:1;text-align:center;padding:10px}
    .server-actions .btn{flex:1;justify-content:center}
    .props-cat h4{font-size:13px}
    .toggle{width:48px;height:28px}
    .toggle .slider::before{width:22px;height:22px;top:3px;left:3px}
    .toggle input:checked+.slider::before{transform:translateX(20px)}
    .fe-header{flex-direction:column;align-items:flex-start!important;gap:4px}
    .fe-header span:last-child{font-size:11px;color:#555}
    .pack-subnav{margin-bottom:8px}
    .search-status{padding:20px;font-size:14px}
  }
  /* ── Responsive (phones) ── */
  @media(max-width:480px){
    .menu-toggle{padding:4px 8px;font-size:22px}
    .topbar #statusLabel{max-width:50px;font-size:12px}
    .topbar .stat{padding:2px 6px;font-size:10px}
    .content{padding:12px}
    .status-grid{gap:6px;grid-template-columns:repeat(2,1fr)}
    .stat-card{padding:12px}
    .stat-card .sc-val{font-size:17px}
    .modal-box{padding:16px;border-radius:10px}
    .modal-box textarea{font-size:13px;padding:10px}
    ::-webkit-scrollbar{width:3px}
    .tunnel-addr{flex-direction:column;text-align:center;gap:8px}
    .console{height:30vh}
    .file-editor{min-height:35vh}
    .file-editor textarea{min-height:20vh}
    .loading{padding:24px;font-size:14px}
    .server-actions .btn{padding:10px 12px;font-size:13px}
    .sidebar{width:100%}
    .sidebar h2{padding:12px 16px;padding-top:calc(12px + env(safe-area-inset-top,0px))}
    .sidebar nav a{padding:16px 18px}
  }
</style>
</head>
<body>
<div class="sidebar">
  <div class="server-picker">
    <select id="serverSelect" onchange="onServerChange()">
      <option value="">— No server selected —</option>
    </select>
  </div>
  <h2>Minecraft Console</h2>
  <nav>
    <a href="#" class="active" data-page="dashboard">Dashboard</a>
    <a href="#" data-page="servers">Servers</a>
    <a href="#" data-page="console">Console</a>
    <a href="#" data-page="properties">Settings</a>
    <a href="#" data-page="packs">Mods & Packs</a>
    <a href="#" data-page="files">File Manager</a>
    <a href="#" data-page="backups">Backups</a>
    <a href="#" data-page="tunnel">Tunnel</a>
  </nav>
</div>
<div class="sidebar-overlay" id="sidebarOverlay" onclick="toggleSidebar()"></div>
<div class="main">
  <div class="topbar">
    <button class="menu-toggle" id="menuToggle" onclick="toggleSidebar()" aria-label="Toggle menu"><span class="bar"></span><span class="bar"></span><span class="bar"></span></button>
    <span class="dot" id="statusDot"></span>
    <span id="statusLabel" style="font-weight:600;font-size:14px">Loading...</span>
    <span class="stat mem" id="memStat">— MB</span>
    <span class="stat players" id="playerStat">0 online</span>
    <span class="stat uptime" id="uptimeStat">—</span>
  </div>
  <div class="content" id="mainContent">
    <div class="page active" id="page-dashboard"></div>
    <div class="page" id="page-servers">
      <div class="server-actions">
        <button class="btn btn-cmd" onclick="showCreateServerModal()">Create Server</button>
        <button class="btn btn-secondary" onclick="showImportModal()">Import Server</button>
        <button class="btn btn-secondary" onclick="loadServers()">&#x21bb;</button>
      </div>
      <div id="serversList" class="loading">Loading servers...</div>
    </div>
    <div class="page" id="page-console">
      <div class="server-actions">
        <button class="btn btn-start" onclick="api('start')">Start</button>
        <button class="btn btn-stop" onclick="showStopModal()">Stop</button>
        <button class="btn btn-restart" onclick="showRestartModal()">Restart</button>
      </div>
      <div class="console-wrap">
        <div class="console-header"><span>Server Console</span><span><button class="btn btn-secondary" style="padding:4px 10px;font-size:12px" onclick="copyConsoleLogs()">Copy Logs</button><button class="btn btn-secondary" style="padding:4px 10px;font-size:12px" onclick="clearConsole()">Clear</button></span></div>
        <div class="console" id="consoleOutput"><span style="color:#555">Server not running — start it to see console output</span></div>
        <form class="cmd-bar" onsubmit="return sendCmd(event)">
          <input type="text" id="cmdInput" placeholder="Type a command..." autocomplete="off">
          <button class="btn btn-cmd" type="submit">Send</button>
        </form>
      </div>
    </div>
    <div class="page" id="page-files">
      <div class="server-actions">
        <button class="btn btn-cmd" onclick="openUploadModal('file')">Upload File</button>
      </div>
      <div id="fileBrowser" class="loading">Loading files...</div>
    </div>
    <div class="page" id="page-properties"></div>
    <div class="page" id="page-packs">
      <div class="pack-subnav">
        <button class="active" id="packBrowseBtn" onclick="showPackTab('browse')">Browse</button>
        <button id="packInstalledBtn" onclick="showPackTab('installed')">Installed</button>
      </div>
      <div id="packBrowse">
        <div class="pack-search-bar">
          <input type="text" id="packSearchInput" placeholder="Search mods, packs & plugins..." onkeydown="if(event.key==='Enter')searchPacks()">
          <select id="packProviderSelect" onchange="onProviderChange()"><option value="modrinth">Modrinth</option><option value="curseforge">CurseForge</option></select>
          <select id="packTypeSelect" onchange="searchPacks(true)">
            <option value="modpack">Modpacks</option>
            <option value="mod">Mods</option>
            <option value="resourcepack">Resource Packs</option>
            <option value="datapack">Data Packs</option>
            <option value="shader">Shaders</option>
            <option value="plugin">Plugins</option>
            <option value="server">Servers</option>
          </select>
          <button class="btn btn-cmd" onclick="searchPacks()">Search</button>
          <button class="btn btn-secondary" onclick="searchPacks()" title="Refresh results">&#x21bb;</button>
        </div>
        <div id="packResults"></div>
      </div>
            <div id="packInstalled" style="display:none">
        <div class="server-actions">
          <button class="btn btn-cmd" onclick="openUploadModal('mod')">Import Mod</button>
          <button class="btn btn-cmd" onclick="openUploadModal('modpack')">Import Modpack</button>
          <button class="btn btn-cmd" onclick="openUploadModal('resourcepack')">Import Resource Pack</button>
          <button class="btn btn-cmd" onclick="openUploadModal('datapack')">Import Data Pack</button>
          <button class="btn btn-cmd" onclick="openUploadModal('shader')">Import Shader</button>
          <button class="btn btn-cmd" onclick="openUploadModal('plugin')">Import Plugin</button>
          <button class="btn btn-cmd" onclick="openUploadModal('server')">Import Server Jar</button>
        </div>
        <div style="display:flex;gap:8px;margin-bottom:10px">
          <input type="text" id="packSearchInput" oninput="filterInstalledPacks()" placeholder="Search installed..." style="flex:1;padding:8px 12px;background:#111;border:1px solid #333;border-radius:6px;color:#e0e0e0;font-size:14px;outline:none">
          <button class="btn btn-secondary" onclick="loadInstalledPacks()" style="padding:4px 12px;font-size:13px">&#x21bb;</button>
        </div>
        <div id="packSelectBar" style="display:none;margin-bottom:10px;padding:10px 14px;background:#1a2a1a;border:1px solid #3a5a3a;border-radius:6px;align-items:center;gap:10px;flex-wrap:wrap">
          <button class="btn btn-secondary" style="padding:4px 12px;font-size:12px" onclick="toggleSelectAllPacks()" id="packSelectAllBtn">Select All</button>
          <button class="btn btn-danger" style="padding:4px 12px;font-size:12px" onclick="deleteSelectedPacks()" id="packDeleteSelectedBtn" disabled>Delete Selected (0)</button>
          <span id="packSelectedCount" style="font-size:13px;color:#888"></span>
          <button class="btn btn-secondary" style="padding:4px 12px;font-size:12px;margin-left:auto" onclick="clearPackSelection()">Clear</button>
        </div>
        <div id="packInstalledList"></div>
      </div><div class="page" id="page-backups">
      <div class="server-actions">
        <button class="btn btn-backup" onclick="createBackup()">Create Backup</button>
      </div>
      <div id="backupsList"></div>
    </div>
    <div class="page" id="page-tunnel">
      <div id="tunnelContent" class="loading">Checking tunnel status...</div>
    </div>
  </div>
</div>

<div class="modal" id="stopModal">
  <div class="modal-box">
    <h3>Stop Server</h3>
    <label style="font-size:13px;color:#888">Warning time (seconds):</label>
    <input type="number" id="stopSeconds" value="15" min="0" max="120">
    <div class="modal-actions">
      <button class="btn btn-secondary" onclick="closeModal('stopModal')">Cancel</button>
      <button class="btn btn-stop" onclick="doStop()">Stop</button>
    </div>
  </div>
</div>
<div class="modal" id="restartModal">
  <div class="modal-box">
    <h3>Restart Server</h3>
    <label style="font-size:13px;color:#888">Warning time (seconds):</label>
    <input type="number" id="restartSeconds" value="15" min="0" max="120">
    <div class="modal-actions">
      <button class="btn btn-secondary" onclick="closeModal('restartModal')">Cancel</button>
      <button class="btn btn-restart" onclick="doRestart()">Restart</button>
    </div>
  </div>
</div>
<div class="modal" id="versionModal">
  <div class="modal-box">
    <h3 id="versionModalTitle">Select Version</h3>
    <div id="versionFilters" style="display:flex;gap:8px;margin:10px 0">
      <select id="verFilterGameVer" onchange="applyVersionFilters()" style="flex:1;padding:6px 8px;background:#111;border:1px solid #333;border-radius:4px;color:#e0e0e0;font-size:12px;outline:none">
        <option value="">All game versions</option>
      </select>
      <select id="verFilterLoader" onchange="applyVersionFilters()" style="flex:1;padding:6px 8px;background:#111;border:1px solid #333;border-radius:4px;color:#e0e0e0;font-size:12px;outline:none">
        <option value="">All platforms</option>
      </select>
    </div>
    <div id="versionList"></div>
    <div class="modal-actions" style="margin-top:12px">
      <button class="btn btn-secondary" onclick="closeModal('versionModal')">Cancel</button>
    </div>
  </div>
</div>
<div class="modal" id="uploadModal">
  <div class="modal-box" style="min-width:420px">
    <h3 id="uploadModalTitle">Upload</h3>
    <div id="uploadDropzone" class="dropzone" style="margin:12px 0">
      Drag & drop files here, or click to browse
      <input type="file" id="uploadFileInput" multiple>
    </div>
    <div id="uploadFileList" style="max-height:150px;overflow-y:auto"></div>
    <div id="uploadDestHint" style="font-size:12px;color:#666;margin:6px 0"></div>
    <div class="modal-actions" style="margin-top:12px">
      <button class="btn btn-secondary" onclick="closeModal('uploadModal')">Cancel</button>
      <button class="btn btn-save" id="uploadStartBtn" onclick="doUpload()">Upload</button>
    </div>
  </div>
</div>
<div class="modal" id="createServerModal">
  <div class="modal-box" style="min-width:450px">
    <h3>Create Server</h3>
    <label style="font-size:13px;color:#888;display:block;margin-top:10px">Server Name</label>
    <input type="text" id="csName" placeholder="My Server" style="width:100%;padding:8px 12px;background:#111;border:1px solid #333;border-radius:4px;color:#e0e0e0;outline:none">
    <label style="font-size:13px;color:#888;display:block;margin-top:10px">Server Type</label>
    <select id="csType" onchange="onCsTypeChange()" style="width:100%;padding:8px 12px;background:#111;border:1px solid #333;border-radius:4px;color:#e0e0e0;outline:none">
    </select>
    <label style="font-size:13px;color:#888;display:block;margin-top:10px">Minecraft Version</label>
    <select id="csVersion" onchange="onCsVersionChange()" style="width:100%;padding:8px 12px;background:#111;border:1px solid #333;border-radius:4px;color:#e0e0e0;outline:none">
      <option value="">Loading...</option>
    </select>
    <div id="forgeVersionRow" style="display:none">
      <label style="font-size:13px;color:#888;display:block;margin-top:10px">Forge Version</label>
      <select id="csForgeVersion" style="width:100%;padding:8px 12px;background:#111;border:1px solid #333;border-radius:4px;color:#e0e0e0;outline:none">
        <option value="">Select Forge version...</option>
      </select>
    </div>
    <div style="display:flex;gap:12px;margin-top:10px">
      <div style="flex:1"><label style="font-size:13px;color:#888">Min RAM</label><input type="range" id="csMinRam" min="512" max="8192" step="256" value="512" style="width:100%;accent-color:#5ced73" oninput="document.getElementById('csMinRamVal').textContent=fmtRamMb(parseInt(this.value))"><span id="csMinRamVal" style="font-size:14px;color:#5ced73;font-weight:bold;display:block;text-align:center;margin-top:2px">512 MB</span></div>
      <div style="flex:1"><label style="font-size:13px;color:#888">Max RAM</label><input type="range" id="csMaxRam" min="512" max="8192" step="256" value="2048" style="width:100%;accent-color:#5ced73" oninput="document.getElementById('csMaxRamVal').textContent=fmtRamMb(parseInt(this.value))"><span id="csMaxRamVal" style="font-size:14px;color:#5ced73;font-weight:bold;display:block;text-align:center;margin-top:2px">2 GB</span></div>
    </div>
    <div style="display:flex;align-items:center;margin-top:10px">
      <input type="checkbox" id="csEula" style="margin-right:6px;width:auto">
      <label style="font-size:13px;color:#888">I accept the <a href="https://minecraft.net/eula" target="_blank" style="color:#5ced73">Minecraft EULA</a></label>
    </div>
    <label style="font-size:13px;color:#888;display:block;margin-top:10px">World Seed <span style="color:#666">(optional)</span></label>
    <input type="text" id="csSeed" placeholder="Leave blank for random" style="width:100%;padding:8px 12px;background:#111;border:1px solid #333;border-radius:4px;color:#e0e0e0;outline:none">
    <div class="modal-actions" style="margin-top:14px">
      <button class="btn btn-secondary" onclick="closeModal('createServerModal')">Cancel</button>
      <button class="btn btn-start" id="csCreateBtn" onclick="doCreateServer()">Create & Download</button>
    </div>
  </div>
</div>
<div class="modal" id="importModal">
  <div class="modal-box" style="min-width:400px">
    <h3>Import Server</h3>
    <label style="font-size:13px;color:#888;display:block;margin-top:10px">Server Folder Path</label>
    <input type="text" id="impPath" placeholder="/path/to/server/folder" style="width:100%;padding:8px 12px;background:#111;border:1px solid #333;border-radius:4px;color:#e0e0e0;outline:none">
    <label style="font-size:13px;color:#888;display:block;margin-top:10px">Name (optional)</label>
    <input type="text" id="impName" placeholder="My Server" style="width:100%;padding:8px 12px;background:#111;border:1px solid #333;border-radius:4px;color:#e0e0e0;outline:none">
    <div style="font-size:12px;color:#666;margin-top:6px">The folder should contain a server .jar file.</div>
    <div class="modal-actions" style="margin-top:14px">
      <button class="btn btn-secondary" onclick="closeModal('importModal')">Cancel</button>
      <button class="btn btn-save" onclick="doImportServer()">Import</button>
    </div>
  </div>
</div>
<div class="modal" id="installProgressModal">
  <div class="modal-box" style="min-width:420px">
    <h3 id="ipTitle">Installing...</h3>
    <div style="margin:16px 0">
      <div style="display:flex;justify-content:space-between;font-size:13px;color:#888;margin-bottom:4px">
        <span id="ipPhase">Starting...</span>
        <span id="ipCount"></span>
      </div>
      <div style="width:100%;height:20px;background:#111;border-radius:10px;overflow:hidden">
        <div id="ipBar" style="width:0%;height:100%;background:linear-gradient(90deg,#2e7d32,#5ced73);border-radius:10px;transition:width .3s"></div>
      </div>
      <div id="ipDetail" style="margin-top:8px;font-size:12px;color:#666;word-break:break-all"></div>
    </div>
    <div class="modal-actions">
      <button class="btn btn-secondary" onclick="closeModal('installProgressModal')" id="ipCloseBtn">Close</button>
    </div>
  </div>
</div>
<div class="toast" id="toast"></div>

<script>
let statusPoll = null;
let consoleStream = null;
let currentFile = null;
let currentFilePath = null;
let _currentServer = '';
let _serverStartedAt = null;

function $(id){return document.getElementById(id)}

// ── Sidebar ──
function toggleSidebar() {
  document.querySelector('.sidebar').classList.toggle('open');
  document.getElementById('sidebarOverlay').classList.toggle('open');
}

function closeSidebar() {
  document.querySelector('.sidebar').classList.remove('open');
  document.getElementById('sidebarOverlay').classList.remove('open');
}

// ── Navigation ──
document.querySelectorAll('.sidebar nav a').forEach(a => {
  a.onclick = e => {
    e.preventDefault();
    document.querySelectorAll('.sidebar nav a').forEach(x => x.classList.remove('active'));
    a.classList.add('active');
    showPage(a.dataset.page);
    closeSidebar();
  };
});

function showPage(name) {
  document.querySelectorAll('.page').forEach(p => p.classList.remove('active'));
  $(`page-${name}`).classList.add('active');
  if (name === 'console') setupConsole();
  if (name === 'files') loadFileTree();
  if (name === 'backups') loadBackups();
  if (name === 'dashboard') loadDashboard();
  if (name === 'properties') loadProperties();
  if (name === 'servers') loadServers();
  if (name === 'packs') { loadInstalledPacks(); if (!window._packsLoaded) { window._packsLoaded = true; searchPacks(true); } }
  if (name === 'tunnel') loadTunnel();
  else stopTunnelPoll();
}

// ── Toast ──
function toast(msg, type='info') {
  const t = $('toast');
  t.textContent = msg;
  t.className = `toast ${type} show`;
  setTimeout(() => t.classList.remove('show'), 3000);
}

// ── Fetch helpers ──
async function api(method, body) {
  const opts = {method:'POST'};
  if (body) opts.body = JSON.stringify(body), opts.headers = {'Content-Type':'application/json'};
  const globalApis = {'servers':1, 'versions':1, 'servers/import':1};
  const prefix = (_currentServer && !globalApis[method]) ? `/api/servers/${_currentServer}/` : '/api/';
  const r = await fetch(`${prefix}${method}`, opts);
  const d = await r.json();
  if (!d.ok) toast(d.error, 'error');
  else if (d.message) toast(d.message, 'success');
  return d;
}

async function get(path) {
  const globalPaths = ['/api/servers', '/api/versions', '/api/playit'];
  const isGlobal = globalPaths.some(p => path.startsWith(p));
  if (path.startsWith('/api/') && !isGlobal && _currentServer) {
    path = `/api/servers/${_currentServer}/${path.replace('/api/', '')}`;
  }
  const r = await fetch(path);
  return r.json();
}

async function uploadFile(file, dest) {
  const fd = new FormData();
  fd.append('file', file);
  if (dest) fd.append('dest', dest);
  const url = _currentServer ? `/api/servers/${_currentServer}/upload` : '/api/upload/app';
  const r = await fetch(url, {method:'POST', body: fd});
  const d = await r.json();
  if (!d.ok) toast(d.error || 'Upload failed', 'error');
  else toast(d.message || 'Uploaded', 'success');
  return d;
}

function initDropzone(zoneId, inputId, onFiles) {
  const zone = document.getElementById(zoneId);
  if (!zone) return;
  const input = document.getElementById(inputId);
  zone.addEventListener('click', () => input.click());
  input.addEventListener('change', () => {
    if (input.files.length) onFiles(input.files);
    input.value = '';
  });
  zone.addEventListener('dragover', e => { e.preventDefault(); zone.classList.add('dragover'); });
  zone.addEventListener('dragleave', () => zone.classList.remove('dragover'));
  zone.addEventListener('drop', e => {
    e.preventDefault();
    zone.classList.remove('dragover');
    if (e.dataTransfer.files.length) onFiles(e.dataTransfer.files);
  });
}

let _uploadMode = 'file';
let _uploadPending = [];

function openUploadModal(mode) {
  _uploadMode = mode;
  _uploadPending = [];
  const titles = {file:'Upload File', modpack:'Import Modpack', resourcepack:'Import Resource Pack', mod:'Import Mod', datapack:'Import Data Pack', shader:'Import Shader', plugin:'Import Plugin', server:'Import Server Jar'};
  const accepts = {file:'', modpack:'.zip,.jar', resourcepack:'.zip', mod:'.jar,.litemod', datapack:'.zip', shader:'.zip', plugin:'.jar', server:'.jar'};
  const dests = {file:'current directory', modpack:'mods/', resourcepack:'resourcepacks/', mod:'mods/', datapack:'datapacks/', shader:'shaderpacks/', plugin:'plugins/', server:'server root/'};
  $('uploadModalTitle').textContent = titles[mode] || 'Upload';
  $('uploadDestHint').textContent = `Destination: ${dests[mode] || ''}`;
  $('uploadFileList').innerHTML = '';
  const inp = $('uploadFileInput');
  inp.accept = accepts[mode] || '';
  $('uploadModal').classList.add('show');
}

function renderUploadFileList() {
  const c = $('uploadFileList');
  if (!_uploadPending.length) { c.innerHTML = ''; return; }
  let html = '';
  for (let i = 0; i < _uploadPending.length; i++) {
    const f = _uploadPending[i];
    const sz = f.size >= 1048576 ? (f.size/1048576).toFixed(1)+' MB' : (f.size/1024).toFixed(0)+' KB';
    html += `<div style="display:flex;justify-content:space-between;align-items:center;padding:6px 8px;background:#151515;border:1px solid #2a2a2a;border-radius:4px;margin-bottom:4px">
      <span style="font-size:13px">${escapeHtml(f.name)}</span>
      <span style="font-size:12px;color:#888">${sz} <a href="#" onclick="removeUploadFile(${i});return false" style="color:#ff4444;margin-left:8px">remove</a></span>
    </div>`;
  }
  c.innerHTML = html;
}

function removeUploadFile(i) {
  _uploadPending.splice(i, 1);
  renderUploadFileList();
}

window.addEventListener('DOMContentLoaded', () => {
  initDropzone('uploadDropzone', 'uploadFileInput', (files) => {
    for (const f of files) _uploadPending.push(f);
    renderUploadFileList();
  });
});

function _getUploadDest(filename) {
  const name = filename.toLowerCase();
  if (_uploadMode === 'modpack' || _uploadMode === 'mod') return 'mods';
  if (_uploadMode === 'resourcepack') return 'resourcepacks';
  if (_uploadMode === 'datapack') return 'datapacks';
  if (_uploadMode === 'shader') return 'shaderpacks';
  if (_uploadMode === 'plugin') return 'plugins';
  if (_uploadMode === 'server') return '.';
  return _fileUploadDest;
}

async function doUpload() {
  if (!_uploadPending.length) { toast('No files selected', 'info'); return; }
  const btn = $('uploadStartBtn');
  btn.disabled = true;
  btn.textContent = 'Uploading...';
  for (const f of _uploadPending) {
    const dest = _getUploadDest(f.name);
    await uploadFile(f, dest);
  }
  btn.disabled = false;
  btn.textContent = 'Upload';
  _uploadPending = [];
  closeModal('uploadModal');
  if (_uploadMode === 'file') loadFileTree(_fileUploadDest);
  else loadInstalledPacks();
}

// ── Status bar ──
let _lastStatus = null;
let _uptimeStart = null;

function updateStatus(data) {
  _lastStatus = data;
  const dot = $('statusDot');
  const label = $('statusLabel');
  if (data && data.online) {
    dot.className = 'dot green';
    label.textContent = 'Running';
    label.style.color = '#5ced73';
  } else {
    dot.className = 'dot red';
    label.textContent = 'Stopped';
    label.style.color = '#ff4444';
    hideRestartBanner();
  }
  $('memStat').textContent = (data && data.mem_mb) ? `${data.mem_mb} MB` : '— MB';
  $('playerStat').textContent = (data && data.online != null) ? `${data.online_count}/${data.max_players} online` : '—';
  if (data && data.online && data.started_at) {
    _uptimeStart = new Date(data.started_at).getTime();
  } else {
    _uptimeStart = null;
  }
  updateUptime();
  updateDashboardLive(data);
}

function formatUptime(ms) {
  if (!ms || ms < 0) return '—';
  const s = Math.floor(ms / 1000);
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const sec = s % 60;
  if (h > 0) return `${h}h ${m}m ${sec}s`;
  if (m > 0) return `${m}m ${sec}s`;
  return `${sec}s`;
}

function updateUptime() {
  const val = _uptimeStart ? formatUptime(Date.now() - _uptimeStart) : '—';
  $('uptimeStat').textContent = val;
  const du = document.getElementById('dashUptime');
  if (du) du.textContent = val;
}

setInterval(updateUptime, 1000);

function updateDashboardLive(data) {
  const pg = document.getElementById('page-dashboard');
  if (!pg || !pg.classList.contains('active')) return;
  const ds = document.getElementById('dashStatus');
  if (ds) ds.textContent = data.online ? 'Running' : 'Stopped';
  if (ds) ds.style.color = data.online ? '#5ced73' : '#ff4444';
  const dp = document.getElementById('dashPlayers');
  if (dp) dp.textContent = `${data.online_count} / ${data.max_players}`;
  const dm = document.getElementById('dashMem');
  if (dm) dm.textContent = `${data.mem_mb || '—'} MB`;
}

async function pollStatus() {
  if (!_currentServer) { updateStatus(null); return; }
  try {
    const d = await get('/api/status');
    updateStatus(d);
  } catch(e) {}
}

function parseRamMb(v) {
  let n = parseInt(v);
  return v.toUpperCase().endsWith('G') ? n * 1024 : n;
}
function fmtRamMb(mb) {
  return mb >= 1024 ? (mb / 1024) + ' GB' : mb + ' MB';
}
function valToRam(v) {
  let n = parseInt(v);
  return n >= 1024 ? (n / 1024) + 'G' : n + 'M';
}

// ── Server Management ──

async function loadServers() {
  const d = await get('/api/servers');
  const container = $('serversList');
  if (!d.ok || !d.servers) { container.innerHTML = '<div class="search-status">Failed to load servers.</div>'; return; }
  const sel = $('serverSelect');
  sel.innerHTML = '';
  let html = '<div class="servers-grid">';
  for (const s of d.servers) {
    const dot = s.online ? '<span class="sp-dot green"></span>' : '<span class="sp-dot red"></span>';
    const onlineTxt = s.online ? 'Running' : 'Stopped';
    sel.innerHTML += `<option value="${s.id}" ${s.id===_currentServer?'selected':''}>${dot}${s.name}</option>`;
    html += `<div class="server-card">
      <h3>${dot}${escapeHtml(s.name)}</h3>
      <div class="sc-meta">
        <span>${s.jar_type}</span>
        <span>Port ${s.port}</span>
        <span>${onlineTxt}</span>
      </div>
      <div class="sc-actions">
        <button class="btn btn-start" style="padding:4px 12px;font-size:12px" onclick="selectServer('${s.id}')">Manage</button>
        <button class="btn btn-danger" style="padding:4px 12px;font-size:12px" onclick="deleteServer('${s.id}','${escapeHtml(s.name)}')">Delete</button>
      </div>
    </div>`;
  }
  html += '</div>';
  container.innerHTML = html;
  if (!d.servers.length) container.innerHTML = '<div class="search-status">No servers yet. Create or import one above.</div>';
}

function selectServer(sid) {
  _currentServer = sid;
  $('serverSelect').value = sid;
  if (consoleStream) { consoleStream.close(); consoleStream = null; }
  if (!$('page-servers').classList.contains('active')) {
    showPage('dashboard');
  }
  pollStatus();
  loadServers();
  toast(`Selected server`, 'success');
}

function onServerChange() {
  const sid = $('serverSelect').value;
  if (!sid) return;
  _currentServer = sid;
  if (consoleStream) { consoleStream.close(); consoleStream = null; }
  showPage('dashboard');
  pollStatus();
  loadServers();
}

function showCreateServerModal() {
  $('csType').innerHTML = '<option value="">Loading...</option>';
  $('csVersion').innerHTML = '<option value="">Loading versions...</option>';
  $('csVersion').disabled = true;
  $('forgeVersionRow').style.display = 'none';
  $('csCreateBtn').disabled = true;
  $('createServerModal').classList.add('show');

  const controller = new AbortController();
  setTimeout(() => controller.abort(), 15000);

  fetch('/api/versions', {signal: controller.signal}).then(r => r.json()).then(d => {
    let sel = '';
    const fallbackTypes = [
      {id:'paper',label:'Paper',desc:'Plugin Support — High-performance Spigot fork'},
      {id:'purpur',label:'Purpur',desc:'Plugin Support — Configurable Paper fork'},
      {id:'spigot',label:'Spigot',desc:'Plugin Support — Bukkit-based server'},
      {id:'vanilla',label:'Vanilla',desc:'Official Minecraft server'},
      {id:'folia',label:'Folia',desc:'Some Plugin Support — Multithreaded Paper fork'},
      {id:'divinemc',label:'DivineMC',desc:'Plugin Support — Optimized Purpur fork'},
      {id:'fabric',label:'Fabric',desc:'Mod Support — Lightweight modding platform'},
      {id:'forge',label:'Forge',desc:'Mod Support — Original modding platform'},
    ];
    const types = (d && d.ok && d.types) ? d.types : fallbackTypes;
    let firstType = '';
    for (const t of types) {
      const s = t.id === 'paper' ? 'selected' : '';
      if (!firstType || t.id === 'paper') firstType = t.id;
      sel += `<option value="${t.id}" ${s}>${t.label}</option>`;
    }
    $('csType').innerHTML = sel;
    $('csType').value = firstType;
    const versions = (d && d.ok && d.versions) ? d.versions : [];
    if (versions.length) {
      let vhtml = '';
      for (const v of versions) vhtml += `<option>${v}</option>`;
      $('csVersion').innerHTML = vhtml;
      $('csVersion').disabled = false;
    } else {
      $('csVersion').innerHTML = '<option value="">Enter version manually below</option>';
      $('csVersion').disabled = false;
      $('csVersion').style.background = '#1a1a1a';
    }
    $('csCreateBtn').disabled = false;
    onCsTypeChange();
  }).catch(err => {
    const fallbackTypes = 'paper|Purpur|Spigot|Vanilla|Folia|DivineMC|Fabric|Forge'.split('|');
    let sel = '';
    for (const t of fallbackTypes) {
      sel += `<option value="${t.toLowerCase()}" ${t.toLowerCase()==='paper'?'selected':''}>${t}</option>`;
    }
    $('csType').innerHTML = sel;
    $('csVersion').innerHTML = '<option value="">Enter version manually</option>';
    $('csVersion').disabled = false;
    $('csCreateBtn').disabled = false;
    onCsTypeChange();
  });
}

function onCsTypeChange() {
  const type = $('csType').value;
  $('forgeVersionRow').style.display = (type === 'forge' || type === 'neoforge') ? 'block' : 'none';
  if (type === 'forge' || type === 'neoforge') loadForgeVersions();
}

function onCsVersionChange() {
  const type = $('csType').value;
  if (type === 'forge' || type === 'neoforge') loadForgeVersions();
}

async function loadForgeVersions() {
  const mcVer = $('csVersion').value;
  if (!mcVer) return;
  const d = await get(`/api/versions/forge?mc_version=${mcVer}`);
  if (!d.ok || !d.forge_versions || !d.forge_versions.length) {
    $('csForgeVersion').innerHTML = '<option value="">No versions available</option>';
    return;
  }
  let html = '';
  let first = '';
  for (const v of d.forge_versions) {
    if (!first) first = v;
    html += `<option>${v}</option>`;
  }
  $('csForgeVersion').innerHTML = html;
  $('csForgeVersion').value = first;
}

async function doCreateServer() {
  const name = $('csName').value.trim();
  if (!name) { toast('Enter a server name', 'error'); return; }
  const jt = $('csType').value;
  const mcVer = $('csVersion').value;
  const forgeVer = $('csForgeVersion')?.value || '';
  if (jt === 'forge' && !forgeVer) { toast('No Forge version available. Check MC version or internet.', 'error'); closeModal('createServerModal'); return; }
  const minRam = valToRam($('csMinRam').value);
  const maxRam = valToRam($('csMaxRam').value);
  if ($('csEula') && !$('csEula').checked) { toast('You must accept the EULA', 'error'); return; }
  closeModal('createServerModal');
  const body = {name, jar_type: jt, min_ram: minRam, max_ram: maxRam};
  if (mcVer) body.mc_version = mcVer;
  if (forgeVer && jt === 'forge') body.forge_version = forgeVer;
  body.eula = true;
  const seed = $('csSeed')?.value.trim();
  if (seed) body.level_seed = seed;
  const d = await api('servers', body);
  loadServers();
  if (d && d.ok && d.server) {
    if (d.download_error) {
      toast('Download failed: ' + (d.message || 'unknown error'), 'error');
    }
    selectServer(d.server.id);
  }
}

function showImportModal() { $('importModal').classList.add('show'); }

async function doImportServer() {
  const path = $('impPath').value.trim();
  if (!path) { toast('Enter a folder path', 'error'); return; }
  const name = $('impName').value.trim() || undefined;
  closeModal('importModal');
  try {
    const r = await fetch('/api/servers/import', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({path, name})});
    const rd = await r.json();
    if (rd.ok) { toast(rd.message || 'Imported', 'success'); loadServers(); }
    else { toast(rd.error || 'Import failed — check that the path exists and contains a .jar file', 'error'); console.error('Import error:', rd); }
  } catch(e) {
    toast('Network error during import', 'error');
  }
}

async function deleteServer(sid, name) {
  if (!confirm(`Delete server '${name}'? This will delete all files permanently!`)) return;
  const r = await fetch(`/api/servers/${sid}`, {method:'DELETE'});
  const d = await r.json();
  if (d.ok) {
    toast(`Deleted '${name}'`, 'success');
    if (_currentServer === sid) {
      _currentServer = '';
      _lastStatus = null;
      updateStatus(null);
    }
    loadServers();
  } else toast(d.error, 'error');
}

// Init
(async function init() {
  const d = await get('/api/servers');
  if (d.ok && d.servers && d.servers.length) {
    _currentServer = d.servers[0].id;
    const sel = $('serverSelect');
    if (sel) sel.value = _currentServer;
  }
  setInterval(pollStatus, 2000);
  pollStatus();
  loadServers();
  loadDashboard();
  setInterval(async () => {
    if (document.getElementById('dashTunnel')) {
      const td = await get('/api/playit/info');
      updateTunnelDashboard(td);
    }
  }, 10000);
})();
async function loadDashboard() {
  if (!_currentServer) {
    $('page-dashboard').innerHTML = '<div class="search-status" style="padding:40px;font-size:16px">Select a server from the sidebar to view its dashboard.</div>';
    return;
  }
  const d = _lastStatus || await get('/api/status');
  const pg = $('page-dashboard');
  if (!d || !d.ok) { pg.innerHTML = '<div class="search-status">No status available.</div>'; return; }
  pg.innerHTML = `
    <div class="status-grid">
      <div class="stat-card"><div class="sc-label">Status</div><div class="sc-val" id="dashStatus" style="color:${d.online?'#5ced73':'#ff4444'}">${d.online?'Running':'Stopped'}</div></div>
      <div class="stat-card"><div class="sc-label">Players</div><div class="sc-val" id="dashPlayers" style="color:#b388ff">${d.online_count} / ${d.max_players}</div></div>
      <div class="stat-card"><div class="sc-label">Memory</div><div class="sc-val" id="dashMem" style="color:#5ced73">${d.mem_mb||'—'} MB</div></div>
      <div class="stat-card"><div class="sc-label">Uptime</div><div class="sc-val" id="dashUptime" style="color:#64b5f6;font-size:18px">—</div></div>
      <div class="stat-card"><div class="sc-label">Address</div><div class="sc-val" id="dashAddr" style="font-size:14px;color:#64b5f6">${d.local_ip||'—'}:${d.server_port||'25565'}</div></div>
      <div class="stat-card"><div class="sc-label">Tunnel</div><div class="sc-val" id="dashTunnel" style="font-size:14px;color:#888">—</div></div>
    </div>
    <div class="server-actions">
      <button class="btn btn-start" onclick="api('start')">Start Server</button>
      <button class="btn btn-stop" onclick="showStopModal()">Stop Server</button>
      <button class="btn btn-restart" onclick="showRestartModal()">Restart Server</button>
    </div>
    <div style="margin-top:20px;padding:16px;background:#1a1a1a;border:1px solid #2a2a2a;border-radius:8px">
      <h3 style="margin-bottom:8px;font-size:14px;color:#888;text-transform:uppercase">Server Info</h3>
      <table style="width:100%;font-size:13px;border-collapse:collapse">
        <tr><td style="padding:6px 0;color:#888">Jar</td><td style="padding:6px 0">${d.jar||'—'}</td></tr>
        <tr><td style="padding:6px 0;color:#888">Directory</td><td style="padding:6px 0">${d.server_dir}</td></tr>
        <tr><td style="padding:6px 0;color:#888">Players</td><td style="padding:6px 0">${d.players.length ? d.players.join(', ') : 'None'}</td></tr>
      </table>
    </div>
    <div style="margin-top:16px;padding:16px;background:#1a1a1a;border:1px solid #2a2a2a;border-radius:8px">
      <h3 style="margin-bottom:8px;font-size:14px;color:#888;text-transform:uppercase">RAM Allocation</h3>
      <div style="display:flex;gap:16px;align-items:end;flex-wrap:wrap">
        <div style="flex:1;min-width:120px">
          <label style="font-size:12px;color:#888">Min RAM</label>
          <input type="range" id="ramMin" min="512" max="8192" step="256" value="${parseRamMb(d.min_ram)}" style="width:100%;accent-color:#5ced73" oninput="document.getElementById('ramMinVal').textContent=fmtRamMb(parseInt(this.value))">
          <span id="ramMinVal" style="font-size:14px;color:#5ced73;font-weight:bold;display:block;text-align:center">${fmtRamMb(parseRamMb(d.min_ram))}</span>
        </div>
        <div style="flex:1;min-width:120px">
          <label style="font-size:12px;color:#888">Max RAM</label>
          <input type="range" id="ramMax" min="512" max="8192" step="256" value="${parseRamMb(d.max_ram)}" style="width:100%;accent-color:#5ced73" oninput="document.getElementById('ramMaxVal').textContent=fmtRamMb(parseInt(this.value))">
          <span id="ramMaxVal" style="font-size:14px;color:#5ced73;font-weight:bold;display:block;text-align:center">${fmtRamMb(parseRamMb(d.max_ram))}</span>
        </div>
        <button class="btn btn-save" style="padding:8px 18px;height:36px" onclick="saveRam()" id="ramSaveBtn">Save RAM</button>
      </div>
      <div style="font-size:12px;color:#666;margin-top:8px">Stop server before changing</div>
    </div>
  `;
}

async function saveRam() {
  const min = valToRam($('ramMin').value);
  const max = valToRam($('ramMax').value);
  const btn = $('ramSaveBtn');
  btn.textContent = 'Saving...';
  btn.disabled = true;
  const d = await api('ram', {min_ram: min, max_ram: max});
  btn.textContent = 'Save RAM';
  btn.disabled = false;
}

// ── Properties / Settings ──
async function loadProperties() {
  const d = await get('/api/properties');
  if (!d.ok) { $('page-properties').innerHTML = `<div class="search-status">${d.error}</div>`; return; }
  const props = d.properties || [];
  const cats = {};
  for (const p of props) {
    const cat = p.cat || 'other';
    if (!cats[cat]) cats[cat] = [];
    cats[cat].push(p);
  }
  const catOrder = ['server', 'gameplay', 'world', 'network', 'other'];
  let html = '';
  for (const c of catOrder) {
    if (!cats[c]) continue;
    html += `<div class="props-cat"><h4>${c.charAt(0).toUpperCase() + c.slice(1)}</h4>`;
    for (const p of cats[c]) {
      html += `<div class="prop-row" data-key="${p.key}"><div class="pr-label">${escapeHtml(p.label)}<small>${escapeHtml(p.desc)}</small></div>`;
      const val = p.value;
      if (p.type === 'bool' || val === 'true' || val === 'false') {
        const checked = val === 'true' ? 'checked' : '';
        html += `<label class="toggle"><input type="checkbox" ${checked} onchange="propChanged('${p.key}',this.checked?'true':'false')"><span class="slider"></span></label>`;
      } else if (p.type === 'enum') {
        html += `<select onchange="propChanged('${p.key}',this.value)">`;
        for (const o of (p.opts || [])) {
          html += `<option value="${o}" ${o===val?'selected':''}>${o}</option>`;
        }
        html += `</select>`;
      } else if (p.type === 'number') {
        html += `<input type="number" value="${escapeHtml(val)}" ${p.min!==undefined?`min="${p.min}"`:''} ${p.max!==undefined?`max="${p.max}"`:''} onchange="propChanged('${p.key}',this.value)">`;
      } else {
        html += `<input type="text" value="${escapeHtml(val)}" onchange="propChanged('${p.key}',this.value)">`;
      }
      html += '</div>';
    }
    html += '</div>';
  }
  html += '</div>';
  $('page-properties').innerHTML = '<div id="propsBanner"></div>' + html;
  window._propChanges = {};
}

let _saveTimeout = null;

function propChanged(key, value) {
  if (!window._propChanges) window._propChanges = {};
  window._propChanges[key] = value;
  if (_saveTimeout) clearTimeout(_saveTimeout);
  _saveTimeout = setTimeout(autoSaveProperties, 300);
}

function showRestartBanner() {
  const b = $('propsBanner');
  if (!b) return;
  b.innerHTML = '<div style="background:#332200;border:1px solid #664400;border-radius:4px;padding:10px 14px;margin-bottom:12px;font-size:13px;color:#ffcc00">Restart server to apply property changes</div>';
}

function hideRestartBanner() {
  const b = $('propsBanner');
  if (b) b.innerHTML = '';
}

async function autoSaveProperties() {
  const changes = window._propChanges || {};
  if (!Object.keys(changes).length) return;
  const r = await fetch(`/api/servers/${_currentServer}/properties`, {
    method:'POST', headers:{'Content-Type':'application/json'},
    body:JSON.stringify({changes})
  });
  const d = await r.json();
  if (d.ok) {
    window._propChanges = {};
    if (d.restart_required) showRestartBanner();
    else hideRestartBanner();
  } else {
    toast(d.error || 'Failed to save', 'error');
  }
}

const PACK_TYPES = [
  { value:'modpack', label:'Modpacks', providers:['modrinth','curseforge'] },
  { value:'mod', label:'Mods', providers:['modrinth','curseforge'] },
  { value:'resourcepack', label:'Resource Packs', providers:['modrinth','curseforge'] },
  { value:'datapack', label:'Data Packs', providers:['modrinth','curseforge'] },
  { value:'shader', label:'Shaders', providers:['modrinth','curseforge'] },
  { value:'plugin', label:'Plugins', providers:['modrinth','curseforge'] },
  { value:'server', label:'Servers', providers:['modrinth'] },
];

function updatePackTypes(provider) {
  const sel = $('packTypeSelect');
  const cur = sel.value;
  sel.innerHTML = '';
  for (const t of PACK_TYPES) {
    if (t.providers.includes(provider)) {
      const opt = document.createElement('option');
      opt.value = t.value;
      opt.textContent = t.label;
      sel.appendChild(opt);
    }
  }
  if ([...sel.options].some(o => o.value === cur)) sel.value = cur;
}

function onProviderChange() {
  updatePackTypes($('packProviderSelect').value);
  searchPacks(true);
}

// ── Modpacks / Resource Packs ──
function showPackTab(tab) {
  $('packBrowse').style.display = tab === 'browse' ? 'block' : 'none';
  $('packInstalled').style.display = tab === 'installed' ? 'block' : 'none';
  $('packBrowseBtn').className = tab === 'browse' ? 'active' : '';
  $('packInstalledBtn').className = tab === 'installed' ? 'active' : '';
  if (tab === 'installed') loadInstalledPacks();
}

async function searchPacks(auto) {
  let q = $('packSearchInput').value.trim();
  const type = $('packTypeSelect').value;
  const prov = $('packProviderSelect').value;
  if (!q) {
    if (auto) { q = 'popular'; }
    else { toast('Enter a search term', 'info'); return; }
  }
  const container = $('packResults');
  container.innerHTML = '<div class="search-status">Searching...</div>';
  const d = await get(`/api/packs/search?q=${encodeURIComponent(q)}&type=${type}&provider=${prov}`);
  if (!d.ok || !d.results) { container.innerHTML = `<div class="search-status">${d.error||'No results'}</div>`; return; }
  if (!d.results.length) { container.innerHTML = '<div class="search-status">No results found</div>'; return; }
  let html = '<div class="pack-grid">';
  for (const r of d.results) {
    const icon = r.icon_url || '';
    const dl = r.downloads >= 1000 ? Math.floor(r.downloads/1000)+'k' : r.downloads;
    const provLabel = r.provider === 'curseforge' ? '<span style="color:#f90">CurseForge</span>' : '<span style="color:#5ced73">Modrinth</span>';
    html += `<div class="pack-card">
      <img src="${icon}" alt="" onerror="this.src='data:image/svg+xml,<svg xmlns=%22http://www.w3.org/2000/svg%22 viewBox=%220 0 48 48%22><rect fill=%22%23333%22 width=%2248%22 height=%2248%22/><text x=%2224%22 y=%2232%22 text-anchor=%22middle%22 fill=%22%23888%22 font-size=%2224%22>?</text></svg>'">
      <div class="pc-body">
        <h4>${escapeHtml(r.title)}</h4>
        <p>${escapeHtml(r.description)}</p>
        <div class="pc-meta">
          <span>${escapeHtml(r.author)}</span>
          <span>${dl} downloads</span>
          <span>${provLabel}</span>
        </div>
        <button class="btn btn-cmd" style="padding:4px 12px;font-size:12px;margin-top:6px" onclick="showVersions('${r.id}','${escapeHtml(r.title)}','${type}','${prov}')">Install</button>
      </div>
    </div>`;
  }
  html += '</div>';
  container.innerHTML = html;
}

let _allVersions = [];
let _versionPackType = '';

function renderVersions() {
  const gameVerFilter = $('verFilterGameVer').value;
  const loaderFilter = $('verFilterLoader').value;
  const filtered = _allVersions.filter(v => {
    if (gameVerFilter && !(v.game_versions||[]).includes(gameVerFilter)) return false;
    if (loaderFilter && !(v.loaders||[]).includes(loaderFilter)) return false;
    return true;
  });
  if (!filtered.length) {
    $('versionList').innerHTML = '<div class="search-status" style="padding:20px">No versions match the selected filters.</div>';
    return;
  }
  let html = '<div style="max-height:300px;overflow-y:auto">';
  for (const v of filtered) {
    const gameVer = (v.game_versions||[]).slice(0,3).join(', ') + ((v.game_versions||[]).length > 3 ? '...' : '');
    const loaders = (v.loaders||[]).join(', ');
    for (const f of (v.files||[]).slice(0,1)) {
      const size = f.size >= 1048576 ? (f.size/1048576).toFixed(1)+' MB' : (f.size/1024).toFixed(0)+' KB';
      html += `<div style="padding:10px;border:1px solid #2a2a2a;border-radius:4px;margin-bottom:6px;background:#151515">
        <div style="font-size:13px"><strong>${escapeHtml(v.name)}</strong> <span style="color:#888">${v.version_number}</span></div>
        <div style="font-size:12px;color:#666;margin:4px 0">${gameVer} | ${loaders} | ${size}</div>
        <button class="btn btn-start" style="padding:4px 12px;font-size:12px" onclick="installPack('${f.url}','${f.filename}','${_versionPackType}')">Download</button>
      </div>`;
    }
  }
  html += '</div>';
  $('versionList').innerHTML = html;
}

function applyVersionFilters() {
  renderVersions();
}

async function showVersions(projectId, title, packType, provider) {
  $('versionModalTitle').textContent = `Versions — ${title}`;
  $('versionList').innerHTML = '<div class="search-status">Loading...</div>';
  $('verFilterGameVer').innerHTML = '<option value="">All game versions</option>';
  $('verFilterLoader').innerHTML = '<option value="">All platforms</option>';
  $('versionModal').classList.add('show');
  _versionPackType = packType;
  let url = `/api/packs/versions?id=${projectId}&type=${packType}`;
  if (provider) url += `&provider=${provider}`;
  const d = await get(url);
  if (!d.ok || !d.versions) { $('versionList').innerHTML = `<div class="search-status">${d.error||'Failed to load'}</div>`; return; }
  if (!d.versions.length) { $('versionList').innerHTML = '<div class="search-status">No versions found</div>'; return; }
  _allVersions = d.versions;
  const gameVersions = [...new Set(_allVersions.flatMap(v => v.game_versions||[]))].sort().reverse();
  const loaders = [...new Set(_allVersions.flatMap(v => v.loaders||[]))].sort();
  const gvSelect = $('verFilterGameVer');
  for (const gv of gameVersions) {
    const opt = document.createElement('option');
    opt.value = gv; opt.textContent = gv;
    gvSelect.appendChild(opt);
  }
  const lSelect = $('verFilterLoader');
  for (const l of loaders) {
    const opt = document.createElement('option');
    opt.value = l; opt.textContent = l;
    lSelect.appendChild(opt);
  }
  renderVersions();
}

async function installPack(fileUrl, filename, packType) {
  closeModal('versionModal');

  // Show progress modal for modpacks
  if (packType === 'modpack') {
    const cp = (id) => document.getElementById(id);
    cp('installProgressModal').classList.add('show');
    cp('ipCloseBtn').disabled = true;
    cp('ipTitle').textContent = 'Installing modpack...';
    cp('ipPhase').textContent = 'Downloading modpack...';
    cp('ipCount').textContent = '';
    cp('ipBar').style.width = '5%';
    cp('ipDetail').textContent = '';

    try {
      const r = await fetch(`/api/servers/${_currentServer}/packs/install`, {
        method:'POST',
        headers:{'Content-Type':'application/json'},
        body:JSON.stringify({file_url: fileUrl, filename, type: packType})
      });
      const d = await r.json();
      if (!d.ok) { toast(d.error || 'Install failed', 'error'); closeModal('installProgressModal'); return; }

      const taskId = d.task_id;
      if (!taskId) { toast('Installed', 'success'); closeModal('installProgressModal'); loadInstalledPacks(); return; }

      // Poll progress
      const poll = setInterval(async () => {
        try {
          const pr = await fetch('/api/packs/install/status/' + taskId).then(r => r.json());
          if (!pr.ok || !pr.progress) { clearInterval(poll); return; }
          const p = pr.progress;

          if (p.phase === 'extracting') {
            cp('ipPhase').textContent = 'Extracting modpack files...';
            const pct = p.total > 0 ? Math.round((p.current / p.total) * 100) : 0;
            cp('ipBar').style.width = Math.min(pct, 100) + '%';
            cp('ipCount').textContent = p.current + '/' + p.total;
            cp('ipDetail').textContent = p.message || '';
          } else if (p.phase === 'downloading') {
            cp('ipPhase').textContent = 'Downloading mods...';
            const pct = p.total > 0 ? Math.round((p.current / p.total) * 100) : 0;
            cp('ipBar').style.width = Math.min(pct, 100) + '%';
            cp('ipCount').textContent = p.current + '/' + p.total;
            cp('ipDetail').textContent = p.message || '';
          } else if (p.phase === 'done' || p.status === 'done') {
            clearInterval(poll);
            cp('ipBar').style.width = '100%';
            cp('ipPhase').textContent = 'Complete!';
            cp('ipCount').textContent = '';
            cp('ipDetail').textContent = p.message || '';
            cp('ipCloseBtn').disabled = false;
            toast(p.message || 'Modpack installed!', 'success');
            loadInstalledPacks();
          } else if (p.status === 'error') {
            clearInterval(poll);
            cp('ipDetail').textContent = p.message || 'Install failed';
            cp('ipCloseBtn').disabled = false;
            toast(p.message || 'Install failed', 'error');
          }
        } catch(e) { clearInterval(poll); }
      }, 500);
    } catch(e) { toast('Install request failed', 'error'); closeModal('installProgressModal'); }
    return;
  }

  // Non-modpack: simple install
  toast('Installing...', 'info');
  const d = await api('packs/install', {file_url: fileUrl, filename, type: packType});
  if (d.ok) {
    toast(`Installed ${filename}`, 'success');
    loadInstalledPacks();
  } else if (d.error === 'blocked') {
    toast('CurseForge blocked server download, opening browser...', 'info');
    window.open(d.url || fileUrl, '_blank');
  }
}

let _packSelected = new Set();

async function loadInstalledPacks() {
  const d = await get('/api/packs/installed');
  $('packSearchInput').value = '';
  _packSelected = new Set();
  $('packSelectBar').style.display = 'none';
  _allInstalledPacks = (d.ok && d.packs) ? d.packs : [];
  filterInstalledPacks();
}

let _selectMode = false;

function toggleSelectMode() {
  _selectMode = !_selectMode;
  _packSelected = new Set();
  const bar = $('packSelectBar');
  const btn = $('packSelectModeBtn');
  if (_selectMode) {
    btn.textContent = '✕ Cancel Selection';
    bar.style.display = 'flex';
    document.querySelectorAll('.pack-cb').forEach(cb => cb.style.display = 'inline-block');
    document.querySelectorAll('.pack-remove-btn').forEach(b => b.style.display = 'none');
  } else {
    btn.textContent = '✓ Select Multiple';
    bar.style.display = 'none';
    document.querySelectorAll('.pack-cb').forEach(cb => cb.style.display = 'none');
    document.querySelectorAll('.pack-remove-btn').forEach(b => b.style.display = '');
  }
  updatePackSelectUI();
}

function onPackCheck(cb) {
  if (cb.checked) _packSelected.add(cb.dataset.path);
  else _packSelected.delete(cb.dataset.path);
  updatePackSelectUI();
}

function toggleSelectAllPacks() {
  const all = document.querySelectorAll('.pack-cb');
  const someUnchecked = Array.from(all).some(cb => !cb.checked);
  all.forEach(cb => {
    cb.checked = someUnchecked;
    if (someUnchecked) _packSelected.add(cb.dataset.path);
    else _packSelected.delete(cb.dataset.path);
  });
  updatePackSelectUI();
  $('packSelectAllBtn').textContent = someUnchecked ? 'Deselect All' : 'Select All';
}

function updatePackSelectUI() {
  const count = _packSelected.size;
  $('packSelectedCount').textContent = count + ' selected';
  const btn = $('packDeleteSelectedBtn');
  btn.disabled = count === 0;
  btn.textContent = 'Delete Selected (' + count + ')';
}

let _allInstalledPacks = [];

function filterInstalledPacks() {
  const q = $('packSearchInput').value.toLowerCase().trim();
  const container = $('packInstalledList');
  let html = '<div style="display:flex;gap:8px;margin-bottom:10px">';
  html += '<button class="btn btn-secondary" style="padding:4px 12px;font-size:12px" onclick="toggleSelectMode()" id="packSelectModeBtn">&#x2713; Select Multiple</button>';
  html += '</div>';
  html += '<div class="installed-list">';
  let count = 0;
  for (const p of _allInstalledPacks) {
    if (q && !p.name.toLowerCase().includes(q) && !p.type.toLowerCase().includes(q)) continue;
    const size = p.size >= 1048576 ? (p.size/1048576).toFixed(1)+' MB' : (p.size/1024).toFixed(0)+' KB';
    const typeLabels = {'mod':'<span style="color:#5ced73">Mod</span>','plugin':'<span style="color:#b388ff">Plugin</span>','resourcepack':'<span style="color:#64b5f6">Resource Pack</span>','datapack':'<span style="color:#4db6ac">Data Pack</span>','shader':'<span style="color:#ffd54f">Shader</span>','modpack':'<span style="color:#f48fb1">Modpack</span>','server':'<span style="color:#888">Server</span>'};
    const label = typeLabels[p.type] || 'Mod';
    const checked = _packSelected.has(p.path) ? 'checked' : '';
    html += `<div class="installed-item" style="position:relative">
      <div style="display:flex;align-items:center;gap:10px;flex:1">
        <input type="checkbox" class="pack-cb" data-path="${escapeHtml(p.path)}" ${checked} onchange="onPackCheck(this)" style="display:none;width:16px;height:16px;accent-color:#5ced73;flex-shrink:0">
        <div class="ii-info"><strong>${escapeHtml(p.name)}</strong><span>${label}</span><span>${size}</span></div>
      </div>
      <button class="btn btn-danger pack-remove-btn" style="padding:4px 12px;font-size:12px" onclick="removePack('${p.path}','${escapeHtml(p.name)}')">Remove</button>
    </div>`;
    count++;
  }
  html += '</div>';
  if (count === 0) {
    html = '<div class="search-status">' + (q ? 'No results matching "' + escapeHtml(q) + '"' : 'Nothing installed yet') + '</div>';
  } else if (q) {
    html += '<div style="text-align:center;font-size:12px;color:#666;margin-top:8px">' + count + ' matching of ' + _allInstalledPacks.length + ' installed</div>';
  }
  container.innerHTML = html;
}

function clearPackSelection() {
  _packSelected = new Set();
  document.querySelectorAll('.pack-cb').forEach(cb => cb.checked = false);
  updatePackSelectUI();
  $('packSelectAllBtn').textContent = 'Select All';
}

async function deleteSelectedPacks() {
  if (_packSelected.size === 0) return;
  if (!confirm('Delete ' + _packSelected.size + ' selected file(s)?')) return;
  const paths = Array.from(_packSelected);
  const r = await fetch('/api/servers/' + _currentServer + '/packs/remove', {
    method:'POST',
    headers:{'Content-Type':'application/json'},
    body:JSON.stringify({paths})
  });
  const d = await r.json();
  if (d.ok) { toast(d.message || 'Deleted', 'success'); loadInstalledPacks(); }
  else { toast(d.error || 'Delete failed', 'error'); }
}

function initPackDropzone() {
}

async function removePack(path, name) {
  if (!confirm(`Remove ${name}?`)) return;
  const d = await api('packs/remove', {path});
  if (d.ok) { toast(`Removed ${name}`, 'success'); loadInstalledPacks(); }
}

// ── Console ──
function setupConsole() {
  if (consoleStream) return;
  if (!_currentServer) { toast('Select a server first', 'info'); return; }
  const out = $('consoleOutput');
  const es = new EventSource(`/api/servers/${_currentServer}/console`);
  consoleStream = es;
  es.onmessage = e => {
    const d = JSON.parse(e.data);
    if (!d || !d.lines || !d.lines.length) return;
    if (d.type === 'history') {
      out.innerHTML = '';
      for (const line of d.lines) appendConsoleLine(out, line);
      out.scrollTop = out.scrollHeight;
      return;
    }
    if (out.children.length === 1 && out.children[0].textContent.includes('not running')) {
      out.innerHTML = '';
    }
    for (const line of d.lines) appendConsoleLine(out, line);
    out.scrollTop = out.scrollHeight;
  };
}

function appendConsoleLine(out, line) {
  const div = document.createElement('div');
  let cls = '';
  let text = line;

  text = text.replace(/[\u00a7\x7f]([0-9a-fklmnor])/gi, '');
  text = text.replace(/\x1b\[[0-9;]*[a-zA-Z]/g, '');
  text = text.replace(/[\x00-\x08\x0b\x0c\x0e-\x1f]/g, '');
  text = text.replace(/\u00a7/g, '');

  if (/\[.*\/INFO\]:/.test(line) || /]: <|]: \[Not Secure\]/.test(line)) cls = 'info';
  if (/\[.*\/WARN\]:/.test(line)) cls = 'warn';
  if (/\[.*\/ERROR\]:/.test(line)) cls = 'error';
  if (/joined the game/.test(line)) cls = 'done';
  if (/left the game/.test(line)) cls = 'warn';
  if (/\[.*\/FATAL\]:/.test(line)) cls = 'error';
  if (/^\[[0-9]{2}:[0-9]{2}:[0-9]{2}\] \[Server thread\/INFO\]: Done /.test(line)) cls = 'done';
  if (/]: .* whispers: /.test(line)) cls = 'say';
  if (/]: .* </.test(line) && !/]: \[Not Secure\]/.test(line)) cls = 'say';
  let ts = '';
  const tm = text.match(/^\[([0-9]{2}:[0-9]{2}:[0-9]{2})\]/);
  if (tm) ts = tm[1];
  div.innerHTML = `<span class="ts">${ts}</span><span class="${cls}">${escapeHtml(text)}</span>`;
  out.appendChild(div);
}

function clearConsole() {
  $('consoleOutput').innerHTML = '<span style="color:#555">Server not running — start it to see console output</span>';
}

function copyConsoleLogs() {
  const lines = Array.from($('consoleOutput').children).map(el => el.textContent.replace(/^\S+\s/, '')).join('\n');
  if (!lines) { toast('No console output to copy', 'info'); return; }
  navigator.clipboard.writeText(lines).then(() => toast('Console logs copied!', 'success')).catch(() => {
    const ta = document.createElement('textarea');
    ta.value = lines;
    document.body.appendChild(ta);
    ta.select();
    document.execCommand('copy');
    ta.remove();
    toast('Console logs copied!', 'success');
  });
}

function sendCmd(e) {
  e.preventDefault();
  const input = $('cmdInput');
  const cmd = input.value.trim();
  if (!cmd) return;
  api('command', {command: cmd});
  input.value = '';
}

// ── Modals ──
function showStopModal() { $('stopModal').classList.add('show') }
function showRestartModal() { $('restartModal').classList.add('show') }
function closeModal(id) { $(id).classList.remove('show') }
function doStop() { closeModal('stopModal'); api('stop', {seconds: parseInt($('stopSeconds').value) || 15}) }
function doRestart() { closeModal('restartModal'); api('restart', {seconds: parseInt($('restartSeconds').value) || 15}) }

// ── File Manager ──
let _fileCurrentDir = '';

function parentDir(path) {
  if (!path) return '';
  const parts = path.replace(/\\/g,'/').split('/');
  parts.pop();
  return parts.join('/');
}

function dirName(path) {
  if (!path) return '';
  const parts = path.replace(/\\/g,'/').split('/');
  return parts.pop();
}

async function loadFileTree(path) {
  _fileCurrentDir = path || '';
  const d = await get(`/api/files?path=${path||''}`);
  if (!d.ok) { $('fileBrowser').innerHTML = `<div class="loading">${d.error}</div>`; return }
  const items = d.items || [];
  const html = ['<div class="file-browser"><div class="file-tree">'];
  if (d.current) {
    const parent = parentDir(d.current);
    if (parent !== d.current) {
      html.push(`<div class="fi folder" onclick="loadFileTree('${parent}')">&#x2191; .. (${parent ? dirName(parent) : 'root'})</div>`);
    }
  }
  for (const item of items) {
    const icon = item.is_dir ? '' : '';
    const cls = item.is_dir ? 'folder' : 'file';
    const click = item.is_dir ? `loadFileTree('${item.path}')` : `openFile('${item.path}')`;
    const acts = `<span class="fi-act"><span onclick="event.stopPropagation();copyFile('${item.path}',${item.is_dir})" title="Copy">&#x1F4CB;</span><span class="fi-mv" onclick="event.stopPropagation();moveFile('${item.path}',${item.is_dir})" title="Move">&#x2702;</span><span class="fi-del" onclick="event.stopPropagation();deleteFile('${item.path}',${item.is_dir})" title="Delete">&#x2715;</span></span>`;
    html.push(`<div class="fi ${cls}" onclick="${click}"><span class="fi-name">${icon} ${item.name}</span>${acts}</div>`);
  }
  html.push('</div><div class="file-editor" id="fileEditor"><div class="fe-header">Select a file to edit</div></div></div>');
  $('fileBrowser').innerHTML = html.join('');
}

async function openFile(path) {
  const d = await get(`/api/files?path=${path}`);
  if (!d.ok) { toast(d.error, 'error'); return }
  currentFilePath = path;
  currentFile = d.name;
  const eds = document.getElementById('fileEditor');
  if (!eds) return;
  const isProps = d.name === 'server.properties' || d.name === 'eula.txt';
  eds.innerHTML = `
    <div class="fe-header"><span>${escapeHtml(d.path)}</span><span style="color:#666">${isProps ? 'Editing this will restart the server to take effect.' : ''}</span></div>
    <textarea id="fileContent" spellcheck="false">${escapeHtml(d.content)}</textarea>
    <div class="fe-actions">
      <button class="btn btn-save" onclick="saveFile()">Save</button>
      <button class="btn btn-secondary" onclick="loadFileTree(_fileCurrentDir)">Cancel</button>
    </div>
  `;
}

async function saveFile() {
  const content = document.getElementById('fileContent').value;
  if (!currentFilePath) return;
  const d = await api('file/save', {path: currentFilePath, content});
  if (d.ok) toast('File saved!', 'success');
}

async function deleteFile(path, isDir) {
  const label = isDir ? 'folder and all contents' : 'file';
  if (!confirm(`Delete ${label}?\n${path}`)) return;
  const d = await api('file/delete', {path});
  if (d.ok) {
    toast(`Deleted`, 'success');
    loadFileTree(_fileCurrentDir);
  }
}

async function copyFile(path, isDir) {
  const label = isDir ? 'folder' : 'file';
  const dest = prompt(`Copy "${path}" to (relative path):`, path);
  if (!dest) return;
  if (dest === path) { toast('Destination must be different', 'error'); return; }
  const d = await api('file/copy', {source: path, destination: dest});
  if (d.ok) { toast(d.message||'Copied!', 'success'); loadFileTree(_fileCurrentDir); }
}

async function moveFile(path, isDir) {
  const label = isDir ? 'folder' : 'file';
  const dest = prompt(`Move "${path}" to (relative path):`, path);
  if (!dest) return;
  if (dest === path) { toast('Destination must be different', 'error'); return; }
  const d = await api('file/move', {source: path, destination: dest});
  if (d.ok) { toast(d.message||'Moved!', 'success'); loadFileTree(_fileCurrentDir); }
}

let _fileUploadDest = '';

// ── Backups ──
async function loadBackups() {
  const d = await get('/api/backups');
  const list = $('backupsList');
  if (!d.backups || !d.backups.length) {
    list.innerHTML = '<div style="padding:24px;text-align:center;color:#666">No backups yet.</div>';
    return;
  }
  let html = '<div class="backups-list">';
  for (const b of d.backups) {
    html += `<div class="backup-item">
      <div class="bi-info"><strong>${escapeHtml(b.name)}</strong><span>${b.size} KB</span><span>${b.date}</span></div>
      <div><button class="btn btn-secondary" style="padding:4px 12px;font-size:12px" onclick="restoreBackup('${b.name}')">Restore</button></div>
    </div>`;
  }
  html += '</div>';
  list.innerHTML = html;
}

async function createBackup() {
  const d = await api('backup');
  if (d.ok) { loadBackups(); toast('Backup created!', 'success'); }
}

async function restoreBackup(name) {
  if (!confirm('Restore this backup? The server will be overwritten.')) return;
  const d = await api('backup/restore', {file: name});
  if (d.ok) toast('Backup restored!', 'success');
}

// ── Tunnel (Playit.gg) ──
let _tunnelPoll = null;

async function loadTunnel() {
  const d = await get('/api/playit/info');
  const c = $('tunnelContent');
  if (!d.ok) { c.innerHTML = '<div class="search-status">Error loading tunnel status.</div>'; return; }
  if (!d.installed) {
    c.innerHTML = `
      <div class="search-status" style="padding:24px">
        <p style="margin-bottom:12px">Playit.gg lets you share your Minecraft server online without port forwarding.</p>
        <button class="btn btn-cmd" onclick="installPlayit()">Install Playit.gg</button>
      </div>`;
    stopTunnelPoll();
    return;
  }
  renderTunnelPage(d);
  updateTunnelDashboard(d);
  startTunnelPoll();
}

function renderTunnelPage(d) {
  const c = $('tunnelContent');
  const claimed = d.claimed;
  const daemonOn = d.daemon_running;
  const running = d.running;
  const logs = d.logs || [];
  const tunnels = d.tunnels || [];
  const claimUrl = d.claim_url;
  const claimCode = d.claim_code;

  let html = '<div class="status-grid">';
  const statusColor = running ? '#5ced73' : (daemonOn ? '#f90' : '#ff4444');
  const statusText = running ? 'Online' : (daemonOn ? 'Daemon Running' : 'Stopped');
  html += `<div class="stat-card"><div class="sc-label">Tunnel</div><div class="sc-val" style="color:${statusColor}">${statusText}</div></div>`;
  html += `<div class="stat-card"><div class="sc-label">Account</div><div class="sc-val" style="color:${claimed?'#5ced73':'#f90'};font-size:14px">${claimed?'Claimed':'Not Claimed'}</div></div>`;
  html += `<div class="stat-card"><div class="sc-label">Daemon</div><div class="sc-val" style="color:${daemonOn?'#5ced73':'#666'};font-size:14px">${daemonOn?'Running':'Off'}</div></div>`;
  if (tunnels.length) html += `<div class="stat-card"><div class="sc-label">Tunnels</div><div class="sc-val" style="color:#64b5f6">${tunnels.length}</div></div>`;
  html += '</div>';

  html += '<div class="server-actions">';
  if (!daemonOn) html += '<button class="btn btn-start" onclick="startDaemon()" id="daemonBtn">Start Daemon</button>';
  if (daemonOn && !claimed) html += '<button class="btn btn-cmd" onclick="runPlayitCli()" id="playitCliBtn">&#9654; Get Claim URL</button>';
  if (daemonOn) html += '<button class="btn btn-stop" onclick="stopDaemon()" id="stopDaemonBtn">Stop Daemon</button>';
  html += '<button class="btn btn-secondary" onclick="loadTunnel()">&#x21bb; Refresh</button>';
  html += '</div>';

  if (!claimed) {
    html += '<div style="margin-top:16px;padding:16px;background:#1a2a1a;border:1px solid #3a4a3a;border-radius:8px">';
    html += '<h3 style="margin-bottom:12px;font-size:14px;color:#5ced73">&#9654; Claim Your Tunnel</h3>';
    if (claimUrl) {
      html += `<div style="margin-bottom:12px"><a href="${escapeHtml(claimUrl)}" target="_blank" class="btn btn-cmd" style="text-decoration:none;display:inline-block;padding:8px 18px;font-size:14px">&#x2197; ${escapeHtml(claimUrl)}</a></div>`;
      if (claimCode) html += `<div style="font-size:13px;color:#888">Claim code: <code style="background:#111;padding:3px 7px;border-radius:3px;font-size:14px;color:#64b5f6;user-select:all">${escapeHtml(claimCode)}</code></div>`;
      html += '<p style="color:#666;font-size:12px;margin-top:8px">Open the link above to claim your tunnel. The daemon will reconnect automatically once claimed.</p>';
    } else if (daemonOn) {
      html += '<p style="color:#ccc;font-size:13px">Daemon is running but no claim URL found yet.</p>';
      html += '<p style="color:#666;font-size:12px;margin-top:6px">Click "Get Claim URL" above, or visit <a href="https://playit.gg/claim" target="_blank" style="color:#64b5f6">playit.gg/claim</a></p>';
    } else {
      html += '<p style="color:#888;font-size:13px">Start the daemon to get a claim URL.</p>';
    }
    html += '</div>';
  } else if (claimUrl) {
    html += `<div style="margin-top:8px;padding:8px 12px;background:#1a1a1a;border:1px solid #2a2a2a;border-radius:4px;font-size:12px;color:#666">Claim URL: <a href="${escapeHtml(claimUrl)}" target="_blank" style="color:#64b5f6">${escapeHtml(claimUrl)}</a></div>`;
  }

  if (tunnels.length) {
    html += '<div style="margin-top:16px;padding:16px;background:#1a1a1a;border:1px solid #2a2a2a;border-radius:8px">';
    html += '<h3 style="margin-bottom:10px;font-size:14px;color:#888;text-transform:uppercase;letter-spacing:1px">Tunnel Addresses</h3>';
    html += '<div style="display:grid;gap:8px">';
    for (const t of tunnels) {
      html += `<div class="tunnel-addr" style="display:flex;align-items:center;gap:8px;padding:10px 14px;background:#0d0d0d;border:1px solid #2a2a2a;border-radius:6px">`;
      html += `<span style="font-family:monospace;font-size:14px;color:#5ced73;word-break:break-all;min-width:0">${escapeHtml(t)}</span>`;
      html += `<button class="btn btn-secondary" style="padding:4px 10px;font-size:12px;flex-shrink:0" onclick="copyText('${escapeHtml(t)}')">Copy</button>`;
      html += '</div>';
    }
    html += '</div>';
    html += '<p style="color:#666;font-size:12px;margin-top:10px">Share these addresses with players to connect to your server.</p>';
    html += '</div>';
  }

  html += '<div style="margin-top:16px">';
  html += '<div class="console-wrap">';
  html += '<div class="console-header"><span>Playit Logs</span><span><button class="btn btn-secondary" style="padding:4px 10px;font-size:12px" onclick="copyDaemonLogs()">Copy</button></span></div>';
  html += '<div class="console" id="daemonLogs" style="height:300px">';
  if (logs.length) {
    for (const l of logs.slice(-80)) html += `<div>${escapeHtml(l)}</div>`;
  } else {
    html += '<span style="color:#555">No daemon logs yet. Start the daemon to see output.</span>';
  }
  html += '</div>';
  html += '</div>';
  html += '</div>';

  c.innerHTML = html;
  const dl = $('daemonLogs');
  if (dl) dl.scrollTop = dl.scrollHeight;
}

function startTunnelPoll() {
  stopTunnelPoll();
  _tunnelPoll = setInterval(async () => {
    if (!$('page-tunnel').classList.contains('active')) { stopTunnelPoll(); return; }
    try {
      const d = await get('/api/playit/info');
      if (d.ok) { renderTunnelPage(d); updateTunnelDashboard(d); }
    } catch(e) {}
  }, 3000);
}

function stopTunnelPoll() {
  if (_tunnelPoll) { clearInterval(_tunnelPoll); _tunnelPoll = null; }
}

async function startDaemon() {
  const btn = $('daemonBtn');
  if (btn) { btn.disabled = true; btn.textContent = 'Starting...'; }
  try {
    const r = await fetch('/api/playit/daemon', {method:'POST'});
    const d = await r.json();
    if (!d.ok) { toast(d.error || 'Failed to start daemon', 'error'); if (btn) { btn.disabled = false; btn.textContent = 'Start Daemon'; } return; }
    toast('Daemon started!', 'success');
    loadTunnel();
  } catch(e) {
    toast('Request failed', 'error');
    if (btn) { btn.disabled = false; btn.textContent = 'Start Daemon'; }
  }
}

async function stopDaemon() {
  const btn = $('stopDaemonBtn');
  if (btn) { btn.disabled = true; btn.textContent = 'Stopping...'; }
  try {
    const r = await fetch('/api/playit/daemon/stop', {method:'POST'});
    const d = await r.json();
    if (btn) { btn.disabled = false; btn.textContent = 'Stop Daemon'; }
    if (!d.ok) { toast(d.error || 'Failed to stop daemon', 'error'); return; }
    toast('Daemon stopped', 'success');
    loadTunnel();
  } catch(e) {
    toast('Request failed', 'error');
    if (btn) { btn.disabled = false; btn.textContent = 'Stop Daemon'; }
  }
}

async function runPlayitCli() {
  const btn = $('playitCliBtn');
  if (btn) { btn.disabled = true; btn.textContent = 'Running...'; }
  try {
    const ac = new AbortController();
    const timeout = setTimeout(() => ac.abort(), 40000);
    const r = await fetch('/api/playit/cli', {method:'POST', signal: ac.signal});
    clearTimeout(timeout);
    const d = await r.json();
    if (!d.ok) { toast(d.error || 'Failed', 'error'); if (btn) { btn.disabled = false; btn.textContent = 'Get Claim URL'; } return; }
    if (d.claim_url) toast('Claim URL found!', 'success');
    else toast('No claim URL found in output', 'info');
    loadTunnel();
  } catch(e) {
    toast('Request timed out or failed', 'error');
    if (btn) { btn.disabled = false; btn.textContent = 'Get Claim URL'; }
  }
}

async function installPlayit() {
  const c = $('tunnelContent');
  c.innerHTML = '<div class="search-status">Installing Playit.gg (this may take a moment)...</div>';
  const r = await fetch('/api/playit/install', {method:'POST'});
  const d = await r.json();
  if (d.ok && d.installed) { toast('Playit installed!', 'success'); loadTunnel(); }
  else toast('Install failed — try manually: pkg install tur-repo && pkg install playit', 'error');
}

function updateTunnelDashboard(d) {
  const tw = document.getElementById('dashTunnel');
  if (!tw) return;
  if (d.installed && d.running && d.tunnels && d.tunnels.length) {
    tw.innerHTML = '<span style="color:#5ced73;font-size:12px">' + escapeHtml(d.tunnels[0]) + '</span>';
  } else if (d.installed && d.running) {
    tw.innerHTML = '<span style="color:#5ced73">&#x25cf; Online</span>';
  } else if (d.installed && d.daemon_running) {
    tw.innerHTML = '<span style="color:#f90">&#x25cf; Daemon Running</span>';
  } else {
    tw.innerHTML = '<span style="color:#888">&#x25cf; Offline</span>';
  }
}

function copyText(text) {
  navigator.clipboard.writeText(text).then(() => toast('Copied!', 'success')).catch(() => {
    const ta = document.createElement('textarea');
    ta.value = text;
    document.body.appendChild(ta);
    ta.select();
    document.execCommand('copy');
    ta.remove();
    toast('Copied!', 'success');
  });
}

function copyDaemonLogs() {
  const dl = $('daemonLogs');
  if (!dl) return;
  const text = Array.from(dl.children).map(el => el.textContent).join('\n');
  if (!text) { toast('No logs to copy', 'info'); return; }
  navigator.clipboard.writeText(text).then(() => toast('Logs copied!', 'success')).catch(() => {
    const ta = document.createElement('textarea');
    ta.value = text;
    document.body.appendChild(ta);
    ta.select();
    document.execCommand('copy');
    ta.remove();
    toast('Logs copied!', 'success');
  });
}

// ── Utility ──
function escapeHtml(s) {
  const d = document.createElement('div');
  d.textContent = s;
  return d.innerHTML;
}

</script>
</body>
</html>
"""

# ═══════════════════════════════════════════════════════════════════════
#  Import routes (registers them on app; app & HTML must be defined first)
# ═══════════════════════════════════════════════════════════════════════

import mc_state
from mc_routes import register_routes  # noqa: E402

register_routes(app, HTML)


# ═══════════════════════════════════════════════════════════════════════
#  CLI
# ═══════════════════════════════════════════════════════════════════════

def main():
    ap = argparse.ArgumentParser(description="Minecraft Web Manager for Termux")
    ap.add_argument("--dir", help="Server directory to import into ~/mc-servers/")
    ap.add_argument("--port", type=int, help=f"Web port (default: {mc_state.PORT})")
    ap.add_argument("--host", help=f"Bind address (default: {mc_state.HOST})")
    ap.add_argument("--headless", action="store_true", help="Import dir then exit (no web server)")
    ap.add_argument("--no-browser", action="store_true", help="Don't auto-open browser (EXE only)")
    args = ap.parse_args()
    if args.port:
        mc_state.PORT = args.port
    if args.host:
        mc_state.HOST = args.host

    import mc_instances as mci
    mci.load_registry()

    if args.dir:
        path = Path(args.dir).resolve()
        if path.exists():
            inst, msg = mci.import_server(str(path))
            if inst:
                print(f" Imported server '{inst.name}' to ~/mc-servers/")
                print(f" You can now manage it from the web UI.")
            else:
                print(f" {msg}")
        else:
            print(f" Directory not found: {path}")
            print(f" Create it and add a server.jar, or use the web UI.")

    if args.headless:
        return

    if not mci.all_servers():
        print(" No Minecraft servers found in ~/mc-servers/")
        print(" Create one from the web UI at http://localhost:5000")
        print(" Or import an existing server folder there.")
        print()

    port = mc_state.PORT
    host = mc_state.HOST
    print(f" Minecraft Web Manager")
    print(f"  Web URL:          http://localhost:{port}")
    print()

    # Auto-open browser when packaged as EXE (unless --no-browser)
    if getattr(sys, 'frozen', False) and not args.no_browser:
        import threading
        def _open_browser():
            import time
            time.sleep(1.5)
            try:
                import webbrowser
                webbrowser.open(f"http://localhost:{port}")
            except Exception:
                pass
        threading.Thread(target=_open_browser, daemon=True).start()

    app.run(host=host, port=port, debug=False, use_reloader=False)


if __name__ == "__main__":
    main()
