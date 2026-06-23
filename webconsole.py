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
  body{font-family:'Segoe UI',system-ui,sans-serif;background:#0f0f0f;color:#e0e0e0;display:flex;height:100vh;overflow:hidden}
  ::-webkit-scrollbar{width:6px}
  ::-webkit-scrollbar-track{background:#1a1a1a}
  ::-webkit-scrollbar-thumb{background:#333;border-radius:3px}
  .sidebar{width:260px;background:#1a1a1a;border-right:1px solid #2a2a2a;display:flex;flex-direction:column;flex-shrink:0}
  .sidebar h2{padding:18px 16px;font-size:15px;font-weight:600;color:#aaa;text-transform:uppercase;letter-spacing:1px;border-bottom:1px solid #2a2a2a}
  .sidebar nav{flex:1;overflow-y:auto;padding:8px 0}
  .sidebar nav a{display:flex;align-items:center;gap:10px;padding:10px 18px;color:#bbb;text-decoration:none;font-size:14px;transition:.15s;border-left:3px solid transparent}
  .sidebar nav a:hover{background:#222;color:#fff}
  .sidebar nav a.active{background:#1e2a1e;color:#5ced73;border-left-color:#5ced73}
  .main{flex:1;display:flex;flex-direction:column;min-width:0}
  .topbar{display:flex;align-items:center;gap:12px;padding:12px 24px;background:#1a1a1a;border-bottom:1px solid #2a2a2a;flex-shrink:0}
  .topbar .dot{width:10px;height:10px;border-radius:50%;display:inline-block}
  .dot.green{background:#5ced73;box-shadow:0 0 6px #5ced7380}
  .dot.red{background:#ff4444;box-shadow:0 0 6px #ff444480}
  .topbar .stat{padding:4px 12px;border-radius:4px;font-size:13px}
  .topbar .stat.mem{background:#1e3a2e;color:#5ced73}
  .topbar .stat.players{background:#2a1e3a;color:#b388ff}
  .topbar .stat.uptime{background:#1e2a3a;color:#64b5f6}
  .content{flex:1;overflow-y:auto;padding:24px}
  .page{display:none}
  .page.active{display:block}
  .server-actions{display:flex;gap:10px;margin-bottom:24px;flex-wrap:wrap}
  .btn{padding:10px 22px;border:none;border-radius:6px;font-size:14px;font-weight:600;cursor:pointer;transition:.15s;display:inline-flex;align-items:center;gap:6px}
  .btn:disabled{opacity:.4;cursor:not-allowed}
  .btn-start{background:#2e7d32;color:#fff}.btn-start:hover{background:#388e3c}
  .btn-stop{background:#c62828;color:#fff}.btn-stop:hover{background:#d32f2f}
  .btn-restart{background:#e65100;color:#fff}.btn-restart:hover{background:#ef6c00}
  .btn-cmd{background:#1565c0;color:#fff}.btn-cmd:hover{background:#1976d2}
  .btn-backup{background:#4a148c;color:#fff}.btn-backup:hover{background:#6a1b9a}
  .btn-save{background:#00695c;color:#fff}.btn-save:hover{background:#00796b}
  .btn-secondary{background:#333;color:#ccc}.btn-secondary:hover{background:#444;color:#fff}
  .btn-danger{background:#7f0000;color:#fff}.btn-danger:hover{background:#b71c1c}
  .console-wrap{background:#0a0a0a;border:1px solid #2a2a2a;border-radius:8px;overflow:hidden}
  .console-header{display:flex;justify-content:space-between;align-items:center;padding:8px 16px;background:#111;border-bottom:1px solid #2a2a2a;font-size:12px;color:#888}
  .console{height:400px;overflow-y:auto;padding:12px 16px;font-family:'JetBrains Mono','Cascadia Code','Fira Code',monospace;font-size:13px;line-height:1.5;white-space:pre-wrap;word-break:break-all;color:#ccc}
  .console .ts{color:#666;margin-right:8px}
  .console .info{color:#4fc3f7}
  .console .warn{color:#ffd54f}
  .console .err,.console .error{color:#ef5350}
  .console .done{color:#69f0ae}
  .console .say{color:#ce93d8}
  .cmd-bar{display:flex;gap:8px;padding:10px 16px;background:#111;border-top:1px solid #2a2a2a}
  .cmd-bar input{flex:1;padding:8px 12px;background:#1a1a1a;border:1px solid #333;border-radius:4px;color:#e0e0e0;font-family:monospace;font-size:13px;outline:none}
  .cmd-bar input:focus{border-color:#5ced73}
  .file-browser{display:flex;gap:1px;height:calc(100vh - 180px);min-height:400px;background:#1a1a1a;border:1px solid #2a2a2a;border-radius:8px;overflow:hidden}
  .file-tree{width:220px;overflow-y:auto;background:#111;padding:8px 0;flex-shrink:0}
  .file-tree .fi{padding:6px 14px;font-size:13px;cursor:pointer;color:#aaa;transition:.1s;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
  .file-tree .fi:hover{background:#222;color:#fff}
  .file-tree .fi.folder{color:#fdd835}
  .file-tree .fi.file{color:#90caf9}
  .file-tree .fi.active{background:#1e2a1e;color:#5ced73}
  .file-tree .fi-del{float:right;color:#555;cursor:pointer;font-size:11px;padding:0 4px;border-radius:3px;opacity:0;transition:.15s}
  .file-tree .fi:hover .fi-del{opacity:1}
  .file-tree .fi-del:hover{color:#ff4444;background:#2a1a1a}
  .file-editor{flex:1;display:flex;flex-direction:column}
  .file-editor .fe-header{padding:8px 16px;background:#151515;border-bottom:1px solid #2a2a2a;font-size:13px;color:#888;display:flex;justify-content:space-between;align-items:center}
  .file-editor textarea{flex:1;background:#0d0d0d;border:none;color:#e0e0e0;font-family:monospace;font-size:13px;padding:12px 16px;resize:none;outline:none;tab-size:2}
  .file-editor .fe-actions{padding:8px 16px;background:#151515;border-top:1px solid #2a2a2a;display:flex;gap:8px}
  .backups-list{display:grid;gap:8px}
  .backup-item{display:flex;justify-content:space-between;align-items:center;padding:12px 16px;background:#1a1a1a;border:1px solid #2a2a2a;border-radius:6px}
  .backup-item .bi-info{font-size:13px}
  .backup-item .bi-info strong{color:#ccc}
  .backup-item .bi-info span{color:#888;margin-left:8px}
  .toast{position:fixed;bottom:24px;right:24px;padding:12px 20px;border-radius:6px;font-size:14px;z-index:100;opacity:0;transition:opacity .3s}
  .toast.show{opacity:1}
  .toast.success{background:#2e7d32;color:#fff}
  .toast.error{background:#b71c1c;color:#fff}
  .toast.info{background:#1565c0;color:#fff}
  .loading{text-align:center;padding:40px;color:#666}
  .status-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:12px;margin-bottom:24px}
  .stat-card{padding:16px;background:#1a1a1a;border:1px solid #2a2a2a;border-radius:8px;text-align:center}
  .stat-card .sc-val{font-size:24px;font-weight:700;margin-top:4px}
  .stat-card .sc-label{font-size:12px;color:#888;text-transform:uppercase;letter-spacing:1px}
  .modal{display:none;position:fixed;inset:0;background:rgba(0,0,0,.7);z-index:50;align-items:center;justify-content:center}
  .modal.show{display:flex}
  .modal-box{background:#1a1a1a;border:1px solid #333;border-radius:8px;padding:24px;min-width:320px}
  .modal-box h3{margin-bottom:16px}
  .modal-box input{width:100%;padding:8px 12px;background:#111;border:1px solid #333;border-radius:4px;color:#e0e0e0;margin-bottom:12px;outline:none}
  .modal-box input:focus{border-color:#5ced73}
  .modal-actions{display:flex;gap:8px;justify-content:flex-end}
  .props-cat{margin-bottom:20px}
  .props-cat h4{font-size:13px;color:#888;text-transform:uppercase;letter-spacing:1px;margin-bottom:10px;padding-bottom:6px;border-bottom:1px solid #2a2a2a}
  .prop-row{display:flex;align-items:center;justify-content:space-between;padding:8px 12px;background:#151515;border:1px solid #2a2a2a;border-radius:4px;margin-bottom:6px}
  .prop-row .pr-label{font-size:13px}
  .prop-row .pr-label small{display:block;font-size:11px;color:#666;margin-top:2px}
  .toggle{position:relative;width:44px;height:24px;flex-shrink:0}
  .toggle input{opacity:0;width:0;height:0}
  .toggle .slider{position:absolute;cursor:pointer;inset:0;background:#333;border-radius:12px;transition:.2s}
  .toggle .slider::before{content:"";position:absolute;width:18px;height:18px;border-radius:50%;background:#888;top:3px;left:3px;transition:.2s}
  .toggle input:checked+.slider{background:#2e7d32}
  .toggle input:checked+.slider::before{background:#fff;transform:translateX(20px)}
  .prop-row select,.prop-row input[type=number],.prop-row input[type=text]{padding:6px 10px;background:#111;border:1px solid #333;border-radius:4px;color:#e0e0e0;font-size:13px;outline:none;width:160px}
  .prop-row select:focus,.prop-row input:focus{border-color:#5ced73}
  .props-save-bar{position:sticky;bottom:0;padding:12px 0;text-align:right}
  .pack-search-bar{display:flex;gap:8px;margin-bottom:16px;flex-wrap:wrap}
  .pack-search-bar input{flex:1;min-width:200px;padding:10px 14px;background:#111;border:1px solid #333;border-radius:6px;color:#e0e0e0;font-size:14px;outline:none}
  .pack-search-bar input:focus{border-color:#5ced73}
  .pack-search-bar select{padding:10px 14px;background:#111;border:1px solid #333;border-radius:6px;color:#e0e0e0;font-size:14px;outline:none}
  .pack-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(280px,1fr));gap:12px}
  .pack-card{background:#1a1a1a;border:1px solid #2a2a2a;border-radius:8px;padding:14px;display:flex;gap:12px;transition:.15s}
  .pack-card:hover{border-color:#444}
  .pack-card img{width:48px;height:48px;border-radius:6px;flex-shrink:0;object-fit:cover;background:#111}
  .pack-card .pc-body{flex:1;min-width:0}
  .pack-card .pc-body h4{font-size:14px;margin-bottom:4px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
  .pack-card .pc-body p{font-size:12px;color:#888;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}
  .pack-card .pc-body .pc-meta{font-size:11px;color:#666;margin-top:6px}
  .pack-card .pc-body .pc-meta span{margin-right:10px}
  .pack-subnav{display:flex;gap:8px;margin-bottom:16px}
  .pack-subnav button{padding:8px 18px;border:1px solid #333;border-radius:6px;background:#1a1a1a;color:#aaa;font-size:13px;cursor:pointer}
  .pack-subnav button.active{background:#2e7d32;color:#fff;border-color:#2e7d32}
  .installed-list{display:grid;gap:8px}
  .installed-item{display:flex;justify-content:space-between;align-items:center;padding:10px 14px;background:#1a1a1a;border:1px solid #2a2a2a;border-radius:6px}
  .installed-item .ii-info{font-size:13px}
  .installed-item .ii-info strong{color:#ccc}
  .installed-item .ii-info span{color:#888;margin-left:8px}
  .search-status{padding:12px;text-align:center;color:#666;font-size:13px}
  .dropzone{border:2px dashed #444;border-radius:8px;padding:24px;text-align:center;color:#888;cursor:pointer;transition:.2s;margin-bottom:16px}
  .dropzone:hover,.dropzone.dragover{border-color:#5ced73;color:#5ced73;background:#1a2a1a}
  .dropzone input{display:none}
  .upload-progress{font-size:12px;color:#888;margin-top:6px}
  .server-picker{padding:10px 12px;border-bottom:1px solid #2a2a2a}
  .server-picker select{width:100%;padding:8px 10px;background:#111;border:1px solid #333;border-radius:4px;color:#e0e0e0;font-size:13px;outline:none}
  .server-picker select:focus{border-color:#5ced73}
  .server-picker .sp-dot{display:inline-block;width:8px;height:8px;border-radius:50%;margin-right:6px}
  .server-picker .sp-dot.green{background:#5ced73;box-shadow:0 0 4px #5ced7380}
  .server-picker .sp-dot.red{background:#ff4444;box-shadow:0 0 4px #ff444480}
  .servers-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(280px,1fr));gap:12px}
  .server-card{background:#1a1a1a;border:1px solid #2a2a2a;border-radius:8px;padding:16px;transition:.15s}
  .server-card:hover{border-color:#444}
  .server-card h3{font-size:15px;margin-bottom:6px}
  .server-card .sc-meta{font-size:12px;color:#888}
  .server-card .sc-meta span{margin-right:12px}
  .server-card .sc-actions{margin-top:10px;display:flex;gap:6px;flex-wrap:wrap}
  @media(max-width:768px){.sidebar{display:none}.content{padding:12px}}
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
<div class="main">
  <div class="topbar">
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
          <input type="text" id="packSearchInput" placeholder="Search modpacks & mods..." onkeydown="if(event.key==='Enter')searchPacks()">
          <select id="packProviderSelect" onchange="searchPacks()"><option value="modrinth">Modrinth</option><option value="curseforge">CurseForge</option></select>
          <select id="packTypeSelect" onchange="searchPacks()"><option value="modpack">Modpacks</option><option value="mod">Mods</option><option value="resourcepack">Resource Packs</option></select>
          <button class="btn btn-cmd" onclick="searchPacks()">Search</button>
          <button class="btn btn-secondary" onclick="searchPacks()" title="Refresh results">&#x21bb;</button>
        </div>
        <div id="packResults"></div>
      </div>
      <div id="packInstalled" style="display:none">
        <div class="server-actions">
          <button class="btn btn-cmd" onclick="openUploadModal('modpack')">Import Modpack</button>
          <button class="btn btn-cmd" onclick="openUploadModal('resourcepack')">Import Resource Pack</button>
        </div>
        <div id="packInstalledList"></div>
      </div>
    </div>
    <div class="page" id="page-backups">
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
    <select id="csVersion" style="width:100%;padding:8px 12px;background:#111;border:1px solid #333;border-radius:4px;color:#e0e0e0;outline:none">
      <option value="">Loading...</option>
    </select>
    <div id="forgeVersionRow" style="display:none">
      <label style="font-size:13px;color:#888;display:block;margin-top:10px">Forge Version</label>
      <select id="csForgeVersion" style="width:100%;padding:8px 12px;background:#111;border:1px solid #333;border-radius:4px;color:#e0e0e0;outline:none">
        <option value="">Select Forge version...</option>
      </select>
    </div>
    <div style="display:flex;gap:12px;margin-top:10px">
      <div style="flex:1"><label style="font-size:13px;color:#888">Min RAM</label><input type="text" id="csMinRam" value="512M" style="width:100%;padding:8px 12px;background:#111;border:1px solid #333;border-radius:4px;color:#e0e0e0;outline:none"></div>
      <div style="flex:1"><label style="font-size:13px;color:#888">Max RAM</label><input type="text" id="csMaxRam" value="2G" style="width:100%;padding:8px 12px;background:#111;border:1px solid #333;border-radius:4px;color:#e0e0e0;outline:none"></div>
    </div>
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
<div class="toast" id="toast"></div>

<script>
let statusPoll = null;
let consoleStream = null;
let currentFile = null;
let currentFilePath = null;
let _currentServer = '';
let _serverStartedAt = null;

function $(id){return document.getElementById(id)}

// ── Navigation ──
document.querySelectorAll('.sidebar nav a').forEach(a => {
  a.onclick = e => {
    e.preventDefault();
    document.querySelectorAll('.sidebar nav a').forEach(x => x.classList.remove('active'));
    a.classList.add('active');
    showPage(a.dataset.page);
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
  const titles = {file:'Upload File', modpack:'Import Modpack', resourcepack:'Import Resource Pack', mod:'Import Mod'};
  const accepts = {file:'', modpack:'.zip,.jar', resourcepack:'.zip', mod:'.jar,.litemod'};
  const dests = {file:'current directory', modpack:'mods/', resourcepack:'resourcepacks/', mod:'mods/'};
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
  if (_uploadMode === 'modpack') return 'mods';
  if (_uploadMode === 'resourcepack') return 'resourcepacks';
  if (_uploadMode === 'mod') return 'mods';
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
  $('forgeVersionRow').style.display = ($('csType').value === 'forge') ? 'block' : 'none';
  if ($('csType').value === 'forge') loadForgeVersions();
}

async function loadForgeVersions() {
  const mcVer = $('csVersion').value;
  if (!mcVer) return;
  const d = await get(`/api/versions/forge?mc_version=${mcVer}`);
  if (!d.ok || !d.forge_versions) return;
  let html = '<option value="">Select Forge version...</option>';
  for (const v of d.forge_versions) html += `<option>${v}</option>`;
  $('csForgeVersion').innerHTML = html;
}

async function doCreateServer() {
  const name = $('csName').value.trim();
  if (!name) { toast('Enter a server name', 'error'); return; }
  const jt = $('csType').value;
  const mcVer = $('csVersion').value;
  const forgeVer = $('csForgeVersion')?.value || '';
  const minRam = $('csMinRam').value.trim().toUpperCase();
  const maxRam = $('csMaxRam').value.trim().toUpperCase();
  closeModal('createServerModal');
  const body = {name, jar_type: jt, min_ram: minRam, max_ram: maxRam};
  if (mcVer) body.mc_version = mcVer;
  if (forgeVer && jt === 'forge') body.forge_version = forgeVer;
  const d = await api('servers', body);
  if (d.ok) { loadServers(); toast(`Server '${name}' created!`, 'success'); }
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
  setInterval(async () => {
    if (document.getElementById('dashTunnel')) {
      const td = await get('/api/playit/status');
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
      <div style="display:flex;gap:12px;align-items:end;flex-wrap:wrap">
        <div>
          <label style="font-size:12px;color:#888">Min RAM</label>
          <input type="text" id="ramMin" value="${d.min_ram}" style="width:90px;padding:8px 10px;background:#111;border:1px solid #333;border-radius:4px;color:#e0e0e0;font-size:14px;outline:none;margin-top:4px">
        </div>
        <div>
          <label style="font-size:12px;color:#888">Max RAM</label>
          <input type="text" id="ramMax" value="${d.max_ram}" style="width:90px;padding:8px 10px;background:#111;border:1px solid #333;border-radius:4px;color:#e0e0e0;font-size:14px;outline:none;margin-top:4px">
        </div>
        <button class="btn btn-save" style="padding:8px 18px" onclick="saveRam()" id="ramSaveBtn">Save RAM</button>
      </div>
      <div style="font-size:12px;color:#666;margin-top:8px">Examples: 512M, 1G, 2G, 4G — stop server before changing</div>
    </div>
  `;
}

async function saveRam() {
  const min = $('ramMin').value.trim().toUpperCase();
  const max = $('ramMax').value.trim().toUpperCase();
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
      if (p.type === 'bool') {
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
  html += `<div class="props-save-bar"><button class="btn btn-save" onclick="saveProperties()" id="propsSaveBtn">Save Properties</button></div>`;
  $('page-properties').innerHTML = html;
  window._propChanges = {};
}

function propChanged(key, value) {
  if (!window._propChanges) window._propChanges = {};
  window._propChanges[key] = value;
}

async function saveProperties() {
  const changes = window._propChanges || {};
  if (!Object.keys(changes).length) { toast('No changes to save', 'info'); return; }
  const btn = $('propsSaveBtn');
  btn.textContent = 'Saving...';
  btn.disabled = true;
  const d = await api('properties', {changes});
  btn.textContent = 'Save Properties';
  btn.disabled = false;
  if (d.ok) {
    window._propChanges = {};
    toast('Properties saved — restart server to apply', 'success');
  }
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

async function showVersions(projectId, title, packType, provider) {
  $('versionModalTitle').textContent = `Versions — ${title}`;
  $('versionList').innerHTML = '<div class="search-status">Loading...</div>';
  $('versionModal').classList.add('show');
  let url = `/api/packs/versions?id=${projectId}&type=${packType}`;
  if (provider) url += `&provider=${provider}`;
  const d = await get(url);
  if (!d.ok || !d.versions) { $('versionList').innerHTML = `<div class="search-status">${d.error||'Failed to load'}</div>`; return; }
  if (!d.versions.length) { $('versionList').innerHTML = '<div class="search-status">No versions found</div>'; return; }
  let html = '<div style="max-height:300px;overflow-y:auto">';
  for (const v of d.versions) {
    const gameVer = (v.game_versions||[]).slice(0,3).join(', ') + ((v.game_versions||[]).length > 3 ? '...' : '');
    const loaders = (v.loaders||[]).join(', ');
    for (const f of (v.files||[]).slice(0,1)) {
      const size = f.size >= 1048576 ? (f.size/1048576).toFixed(1)+' MB' : (f.size/1024).toFixed(0)+' KB';
      html += `<div style="padding:10px;border:1px solid #2a2a2a;border-radius:4px;margin-bottom:6px;background:#151515">
        <div style="font-size:13px"><strong>${escapeHtml(v.name)}</strong> <span style="color:#888">${v.version_number}</span></div>
        <div style="font-size:12px;color:#666;margin:4px 0">${gameVer} | ${loaders} | ${size}</div>
        <button class="btn btn-start" style="padding:4px 12px;font-size:12px" onclick="installPack('${f.url}','${f.filename}','${packType}')">Download</button>
      </div>`;
    }
  }
  html += '</div>';
  $('versionList').innerHTML = html;
}

async function installPack(fileUrl, filename, packType) {
  closeModal('versionModal');
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

async function loadInstalledPacks() {
  const d = await get('/api/packs/installed');
  const container = $('packInstalledList');
  if (!d.ok || !d.packs || !d.packs.length) {
    container.innerHTML = '<div class="search-status">Nothing installed yet</div>';
    return;
  }
  let html = '<div class="installed-list">';
  for (const p of d.packs) {
    const size = p.size >= 1048576 ? (p.size/1048576).toFixed(1)+' MB' : (p.size/1024).toFixed(0)+' KB';
    const label = p.type === 'mod' ? 'Mod' : 'Resource Pack';
    html += `<div class="installed-item">
      <div class="ii-info"><strong>${escapeHtml(p.name)}</strong><span>${label}</span><span>${size}</span></div>
      <button class="btn btn-danger" style="padding:4px 12px;font-size:12px" onclick="removePack('${p.path}','${escapeHtml(p.name)}')">Remove</button>
    </div>`;
  }
  html += '</div>';
  container.innerHTML = html;
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
async function loadFileTree(path) {
  const d = await get(`/api/files?path=${path||''}`);
  if (!d.ok) { $('fileBrowser').innerHTML = `<div class="loading">${d.error}</div>`; return }
  const items = d.items || [];
  const html = ['<div class="file-browser"><div class="file-tree">'];
  if (d.current) html.push(`<div class="fi folder" onclick="loadFileTree('')">.. (root)</div>`);
  for (const item of items) {
    const icon = item.is_dir ? '' : '';
    const cls = item.is_dir ? 'folder' : 'file';
    const click = item.is_dir ? `loadFileTree('${item.path}')` : `openFile('${item.path}')`;
    const del = `<span class="fi-del" onclick="event.stopPropagation();deleteFile('${item.path}',${item.is_dir})" title="Delete">&#x2715;</span>`;
    html.push(`<div class="fi ${cls}" onclick="${click}">${icon} ${item.name}${del}</div>`);
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
      <button class="btn btn-secondary" onclick="loadFileTree()">Cancel</button>
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
    loadFileTree(_fileUploadDest);
  }
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
async function loadTunnel() {
  const d = await get('/api/playit/status');
  const c = $('tunnelContent');
  if (!d.ok) { c.innerHTML = `<div class="search-status">Error loading tunnel status.</div>`; return; }
  if (!d.installed) {
    c.innerHTML = `
      <div class="search-status" style="padding:24px">
        <p style="margin-bottom:12px">Playit.gg lets you share your Minecraft server online without port forwarding.</p>
        <button class="btn btn-cmd" onclick="installPlayit()">Install Playit.gg</button>
      </div>`;
    return;
  }
  const claimed = d.claimed;
  const running = d.running;
  const daemonOn = d.daemon_running;
  let html = '<div class="status-grid">';
  const dot = running ? 'green' : (daemonOn ? '#f90' : 'red');
  const dotCls = running ? 'green' : (daemonOn ? '#f90' : 'red');
  const statusText = running ? 'Running' : (claimed ? 'Daemon running, waiting for tunnel' : 'Not claimed');
  html += `<div class="stat-card"><div class="sc-label">Status</div><div class="sc-val" style="color:${running?'#5ced73':(claimed?'#f90':'#ff4444')}">${statusText}</div></div>`;
  html += `<div class="stat-card"><div class="sc-label">Claimed</div><div class="sc-val" style="color:${claimed?'#5ced73':'#ff4444'}">${claimed?'Yes':'No'}</div></div>`;
  if (d.public_ip) html += `<div class="stat-card"><div class="sc-label">Public IP</div><div class="sc-val" style="color:#64b5f6;font-size:14px">${d.public_ip}:${d.public_port}</div></div>`;
  if (d.version) html += `<div class="stat-card"><div class="sc-label">Version</div><div class="sc-val" style="font-size:14px;color:#888">${d.version}</div></div>`;
  html += '</div>';
  html += '<div class="server-actions">';
  if (!claimed) html += `<button class="btn btn-cmd" onclick="claimPlayit()">Claim Tunnel (get link)</button>`;
  if (claimed && !running) html += `<button class="btn btn-start" onclick="startDaemon()">Start Daemon</button>`;
  if (running) html += `<span style="font-size:13px;color:#5ced73;padding:8px">Tunnel active — server is online!</span>`;
  html += `<button class="btn btn-secondary" onclick="loadTunnel()">&#x21bb; Refresh</button>`;
  html += '</div>';
  html += '<div id="playitOutput"></div>';
  c.innerHTML = html;
  updateTunnelDashboard(d);
}

async function claimPlayit() {
  const outDiv = $('playitOutput');
  if (!outDiv) return;
  outDiv.style.cssText = 'font-size:13px;color:#888;margin-top:12px;white-space:pre-wrap;background:#0a0a0a;padding:12px;border-radius:6px';
  outDiv.textContent = 'Getting claim URL...';
  try {
    const ac = new AbortController();
    const timeout = setTimeout(() => ac.abort(), 40000);
    const r = await fetch('/api/playit/start', {method:'POST', signal: ac.signal});
    clearTimeout(timeout);
    const d = await r.json();
    if (!d.ok) { outDiv.textContent = d.error || 'Failed.'; return; }
    let html = '';
    if (d.claim) {
      html = `
        <p style="color:#5ced73;margin-bottom:8px">Claim URL generated!</p>
        <a href="${d.claim}" target="_blank" style="color:#64b5f6;font-size:16px;word-break:break-all">${d.claim}</a>
        <p style="color:#888;margin-top:8px">Open the link in your browser and follow the instructions to claim your tunnel.</p>
        <p style="color:#888">After claiming, come back here and click <b>Start Daemon</b>.</p>`;
    } else {
      html = `<p style="color:#f90;margin-bottom:8px">${d.message || 'Could not find claim URL automatically.'}</p>
        <p style="margin-top:8px"><a href="https://playit.gg/claim" target="_blank" class="btn btn-cmd" style="text-decoration:none">&#x2197; Open playit.gg to claim manually</a></p>`;
    }
    if (d.lines && d.lines.length) {
      html += '<div style="font-size:12px;color:#666;margin-top:8px">Output:</div><pre style="font-size:11px;color:#555;margin:4px 0;white-space:pre-wrap">' + escapeHtml(d.lines.join('\n')) + '</pre>';
    }
    outDiv.innerHTML = html;
  } catch(e) {
    outDiv.textContent = 'Request timed out. Try again.';
  }
}

async function startDaemon() {
  const outDiv = $('playitOutput');
  if (!outDiv) return;
  outDiv.style.cssText = 'font-size:13px;color:#888;margin-top:12px;white-space:pre-wrap';
  outDiv.textContent = 'Starting daemon...';
  try {
    const r = await fetch('/api/playit/daemon', {method:'POST'});
    const d = await r.json();
    if (d.ok) { outDiv.textContent = 'Daemon started. Refresh to check status.'; setTimeout(loadTunnel, 2000); }
    else outDiv.textContent = d.error || 'Failed.';
  } catch(e) {
    outDiv.textContent = 'Request failed.';
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
  if (d.installed && d.running) {
    tw.innerHTML = `<span style="color:#5ced73">&#x25cf; Tunnel Online</span>`;
    if (d.public_ip) tw.innerHTML += `<br><span style="font-size:12px;color:#888">${d.public_ip}:${d.public_port}</span>`;
  } else if (d.installed && !d.claimed) {
    tw.innerHTML = `<span style="color:#f90">&#x25cf; Tunnel not claimed</span>`;
  } else {
    tw.innerHTML = `<span style="color:#888">&#x25cf; Tunnel offline</span>`;
  }
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

    print(f" Minecraft Web Manager")
    print(f"  Web URL:          http://localhost:{mc_state.PORT}")
    print()

    app.run(host=mc_state.HOST, port=mc_state.PORT, debug=False, use_reloader=False)


if __name__ == "__main__":
    main()
