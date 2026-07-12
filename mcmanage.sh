#!/data/data/com.termux/files/usr/bin/bash

# ======================================================
#  Minecraft Java Server Manager for Termux (Android)
# ======================================================

SCRIPT_DIR="$(dirname "$(readlink -f "$0")")"
SERVER_DIR="${SERVER_DIR:-$SCRIPT_DIR}"
SERVER_JAR="${SERVER_JAR:-server.jar}"
JAVA_ARGS="-Xms1G -Xmx2G -XX:+UseG1GC -Djline.terminal=jline.UnsupportedTerminal -jar"
SCREEN_SESSION="minecraft-server"
PID_FILE="$SERVER_DIR/server.pid"
LOG_FILE="$SERVER_DIR/server.log"
BACKUP_DIR="$SERVER_DIR/backups"
MAX_BACKUPS=7
MIN_RAM=512M
MAX_RAM="${MAX_RAM:-2G}"

info()  { printf "\e[34m[INFO]\e[0m  %s\n" "$*"; }
ok()    { printf "\e[32m[OK]\e[0m    %s\n" "$*"; }
warn()  { printf "\e[33m[WARN]\e[0m  %s\n" "$*"; }
err()   { printf "\e[31m[ERROR]\e[0m %s\n" "$*"; }

detect_java() {
    if command -v java &>/dev/null; then
        JAVA_BIN="java"
        return 0
    fi
    for dir in "$HOME"/.local/lib/jvm/*/bin; do
        if [ -x "$dir/java" ]; then
            JAVA_BIN="$dir/java"
            return 0
        fi
    done
    err "Java not found. Install it: pkg install openjdk-17"
    return 1
}

find_jar() {
    if [ -f "$SERVER_DIR/$SERVER_JAR" ]; then
        JAR_PATH="$SERVER_DIR/$SERVER_JAR"
        return 0
    fi
    local found
    found=$(find "$SERVER_DIR" -maxdepth 1 -name '*.jar' -type f 2>/dev/null | head -1)
    if [ -n "$found" ]; then
        JAR_PATH="$found"
        SERVER_JAR=$(basename "$found")
        return 0
    fi
    err "No server jar found in $SERVER_DIR."
    warn "Place a Minecraft server jar (e.g. paper-*.jar) in this directory."
    return 1
}

check_eula() {
    if [ ! -f "$SERVER_DIR/eula.txt" ]; then
        warn "eula.txt not found."
        warn "To accept the EULA, run: echo 'eula=true' > '$SERVER_DIR/eula.txt'"
        return 1
    fi
    grep -qi 'eula=true' "$SERVER_DIR/eula.txt"
}

check_screen() {
    command -v screen &>/dev/null
}

start_server() {
    detect_java || return 1
    find_jar || return 1
    check_eula || return 1
    check_screen || { err "'screen' not installed. Run: pkg install screen"; return 1; }

    if is_running; then
        warn "Server is already running (PID $(cat "$PID_FILE" 2>/dev/null))."
        return 1
    fi

    cd "$SERVER_DIR" || return 1

    if [ ! -f "server.properties" ]; then
        info "First run detected. Starting once to generate server files..."
        "$JAVA_BIN" -Xms$MIN_RAM -Xmx$MAX_RAM -jar "$JAR_PATH" --nogui &
        local first_pid=$!
        sleep 15
        kill "$first_pid" 2>/dev/null
        wait "$first_pid" 2>/dev/null
        if [ -f "server.properties" ]; then
            ok "Server files generated."
        fi
    fi

    local cmd
    cmd=$(printf '%s %s %s %s --nogui' "$JAVA_BIN" "$JAVA_ARGS" "$JAR_PATH" 2>/dev/null | sed "s/-Xms1G -Xmx2G/-Xms$MIN_RAM -Xmx$MAX_RAM/")
    cmd=$(echo "$cmd" | sed "s/-Xms1G -Xmx2G/-Xms$MIN_RAM -Xmx$MAX_RAM/")
    cmd="$JAVA_BIN -Xms$MIN_RAM -Xmx$MAX_RAM -XX:+UseG1GC -jar \"$JAR_PATH\" --nogui"

    screen -dmS "$SCREEN_SESSION" sh -c "cd '$SERVER_DIR' && exec $cmd"
    sleep 2

    local pid
    pid=$(screen_pid)
    if [ -n "$pid" ]; then
        echo "$pid" > "$PID_FILE"
        ok "Server started. (PID: $pid, Screen: $SCREEN_SESSION)"
    else
        err "Failed to start the server."
        return 1
    fi
}

screen_pid() {
    screen -ls 2>/dev/null | grep -E "\b$SCREEN_SESSION\b" | awk '{print $1}' | cut -d'.' -f1
}

is_running() {
    if [ -f "$PID_FILE" ]; then
        local pid
        pid=$(cat "$PID_FILE" 2>/dev/null)
        if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then
            return 0
        fi
    fi
    local spid
    spid=$(screen_pid)
    [ -n "$spid" ] && return 0
    return 1
}

stop_server() {
    local warn_time="${1:-30}"
    if ! is_running; then
        warn "Server is not running."
        return 1
    fi

    info "Sending 'say Server shutdown in $warn_time seconds...'"
    screen -S "$SCREEN_SESSION" -X stuff "say §cServer shutdown in $warn_time seconds...$(printf '\r')"

    for ((i=warn_time; i>0; i-=5)); do
        screen -S "$SCREEN_SESSION" -X stuff "say §6Shutting down in §e${i}s§6...$(printf '\r')"
        sleep 5
    done

    info "Sending 'stop' command..."
    screen -S "$SCREEN_SESSION" -X stuff "stop$(printf '\r')"

    local waited=0
    while is_running && [ $waited -lt 60 ]; do
        sleep 2
        ((waited+=2))
    done

    if is_running; then
        warn "Server still running. Force killing..."
        local pid
        pid=$(screen_pid)
        [ -n "$pid" ] && kill "$pid" 2>/dev/null
        screen -S "$SCREEN_SESSION" -X quit 2>/dev/null
        sleep 1
    fi

    rm -f "$PID_FILE"
    ok "Server stopped."
}

restart_server() {
    info "Restarting server..."
    stop_server "$@"
    sleep 2
    start_server
}

console() {
    if ! is_running; then
        err "Server is not running."
        return 1
    fi
    if ! check_screen; then
        err "'screen' not installed."
        return 1
    fi
    info "Attaching to console. Detach with Ctrl+A then D."
    sleep 1
    screen -r "$SCREEN_SESSION"
}

send_command() {
    if ! is_running; then
        err "Server is not running."
        return 1
    fi
    screen -S "$SCREEN_SESSION" -X stuff "$*$(printf '\r')"
    ok "Command sent: $*"
}

status() {
    if is_running; then
        local pid
        pid=$(cat "$PID_FILE" 2>/dev/null || screen_pid)
        local mem
        mem=$(ps -o rss= -p "$pid" 2>/dev/null | awk '{printf "%.0f MB", $1/1024}')
        local uptime_sec
        uptime_sec=$(ps -o etime= -p "$pid" 2>/dev/null)
        printf "\e[32m●\e[0m Server is \e[32mRUNNING\e[0m\n"
        printf "  PID:     %s\n" "$pid"
        printf "  Memory:  %s\n" "${mem:-N/A}"
        printf "  Uptime:  %s\n" "${uptime_sec:-N/A}"
        printf "  Screen:  %s\n" "$SCREEN_SESSION"
        printf "  Jar:     %s\n" "$SERVER_DIR/$SERVER_JAR"
    else
        printf "\e[31m●\e[0m Server is \e[31mSTOPPED\e[0m\n"
    fi
}

backup() {
    local world_dirs
    world_dirs=$(find "$SERVER_DIR" -maxdepth 1 -type d -name 'world*' -o -name '*-world' 2>/dev/null)
    if [ -z "$world_dirs" ]; then
        err "No world directories found."
        return 1
    fi
    if is_running; then
        info "Saving worlds before backup..."
        screen -S "$SCREEN_SESSION" -X stuff "save-all$(printf '\r')"
        sleep 3
    fi
    mkdir -p "$BACKUP_DIR"
    local ts
    ts=$(date '+%Y%m%d_%H%M%S')
    local archive="$BACKUP_DIR/world-backup-$ts.tar.gz"
    info "Creating backup: $archive"
    tar -czf "$archive" -C "$SERVER_DIR" $(basename -a $world_dirs) 2>/dev/null
    if [ $? -eq 0 ]; then
        local size
        size=$(du -h "$archive" | cut -f1)
        ok "Backup created: $archive ($size)"
    else
        err "Backup failed."
        return 1
    fi

    local count
    count=$(ls -1 "$BACKUP_DIR"/world-backup-*.tar.gz 2>/dev/null | wc -l)
    if [ "$count" -gt "$MAX_BACKUPS" ]; then
        warn "Pruning old backups (max $MAX_BACKUPS)..."
        ls -1t "$BACKUP_DIR"/world-backup-*.tar.gz 2>/dev/null | tail -n +$((MAX_BACKUPS+1)) | xargs rm -f
        ok "Pruned $((count - MAX_BACKUPS)) old backup(s)."
    fi
}

list_backups() {
    if [ ! -d "$BACKUP_DIR" ] || [ -z "$(ls -A "$BACKUP_DIR"/world-backup-*.tar.gz 2>/dev/null)" ]; then
        warn "No backups found."
        return 1
    fi
    printf "\e[36m%-25s %s\e[0m\n" "DATE" "SIZE"
    printf "%-25s %s\n" "-------------------------" "--------"
    for f in "$BACKUP_DIR"/world-backup-*.tar.gz; do
        local name
        name=$(basename "$f" .tar.gz | sed 's/world-backup-//')
        local size
        size=$(du -h "$f" | cut -f1)
        printf "%-25s %s\n" "$name" "$size"
    done
}

restore_backup() {
    if is_running; then
        err "Stop the server before restoring a backup."
        return 1
    fi
    local backup_file="$1"
    if [ ! -f "$backup_file" ]; then
        err "Backup not found: $backup_file"
        return 1
    fi
    info "Restoring from: $backup_file"
    info "Extracting into: $SERVER_DIR"
    read -p "This will OVERWRITE existing world data. Continue? [y/N] " -r
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        info "Restore cancelled."
        return 1
    fi
    tar -xzf "$backup_file" -C "$SERVER_DIR"
    if [ $? -eq 0 ]; then
        ok "Backup restored from: $backup_file"
    else
        err "Restore failed."
        return 1
    fi
}

edit_properties() {
    local props="$SERVER_DIR/server.properties"
    if [ ! -f "$props" ]; then
        err "server.properties not found. Start the server first to generate it."
        return 1
    fi
    if command -v nano &>/dev/null; then
        nano "$props"
    elif command -d vi &>/dev/null; then
        vi "$props"
    else
        err "No editor found. Install nano: pkg install nano"
        return 1
    fi
    ok "server.properties saved."
}

logs() {
    local lines="${1:-50}"
    if [ ! -f "$LOG_FILE" ]; then
        warn "No log file found at $LOG_FILE"
        warn "Set the log file in server.properties: log-file=$LOG_FILE"
        return 1
    fi
    tail -n "$lines" "$LOG_FILE"
}

watch_logs() {
    if [ ! -f "$LOG_FILE" ]; then
        err "No log file found at $LOG_FILE"
        return 1
    fi
    tail -f "$LOG_FILE"
}

install() {
    detect_java || return 1
    check_screen || { err "Install screen: pkg install screen"; return 1; }

    printf "Minecraft version (e.g. 1.20.4): "
    read -r mc_version
    printf "Server type (paper/purpur/vanilla) [paper]: "
    read -r server_type
    server_type="${server_type:-paper}"

    case "$server_type" in
        paper)
            info "Fetching Paper $mc_version..."
            local project="paper"
            local api_url="https://api.papermc.io/v2/projects/$project/versions/$mc_version"
            local build
            build=$(curl -s "$api_url" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['builds'][-1])" 2>/dev/null)
            if [ -z "$build" ]; then
                err "Failed to fetch Paper version info."
                return 1
            fi
            local download_url="$api_url/builds/$build/downloads/$project-$mc_version-$build.jar"
            info "Downloading $project-$mc_version-$build.jar ..."
            curl -#Lo "$SERVER_DIR/$SERVER_JAR" "$download_url"
            ;;
        purpur)
            info "Fetching Purpur $mc_version..."
            local purpur_url="https://api.purpurmc.org/v2/purpur/$mc_version/latest"
            local download
            download=$(curl -s "$purpur_url" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['build'])" 2>/dev/null)
            if [ -z "$download" ]; then
                err "Failed to fetch Purpur version info."
                return 1
            fi
            curl -#Lo "$SERVER_DIR/$SERVER_JAR" "https://api.purpurmc.org/v2/purpur/$mc_version/$download/download"
            ;;
        vanilla)
            info "Fetching Vanilla $mc_version manifest..."
            local manifest
            manifest=$(curl -s "https://launchermeta.mojang.com/mc/game/version_manifest.json")
            local vanilla_url
            vanilla_url=$(echo "$manifest" | python3 -c "
import sys,json
data=json.load(sys.stdin)
for v in data['versions']:
    if v['id']=='$mc_version':
        print(v['url'])
        break
" 2>/dev/null)
            if [ -z "$vanilla_url" ]; then
                err "Version $mc_version not found."
                return 1
            fi
            local server_jar_url
            server_jar_url=$(curl -s "$vanilla_url" | python3 -c "import sys,json; print(json.load(sys.stdin)['downloads']['server']['url'])" 2>/dev/null)
            curl -#Lo "$SERVER_DIR/$SERVER_JAR" "$server_jar_url"
            ;;
        *)
            err "Unknown server type: $server_type"
            return 1
            ;;
    esac

    if [ -f "$SERVER_DIR/$SERVER_JAR" ] && [ -s "$SERVER_DIR/$SERVER_JAR" ]; then
        ok "Downloaded: $SERVER_DIR/$SERVER_JAR"
    else
        err "Download failed."
        return 1
    fi

    if [ ! -f "$SERVER_DIR/eula.txt" ]; then
        info "Creating eula.txt (eula=false by default)"
        echo "eula=false" > "$SERVER_DIR/eula.txt"
        warn "Edit eula.txt to accept: echo 'eula=true' > eula.txt"
    fi
}

optimize() {
    local props="$SERVER_DIR/server.properties"
    if [ ! -f "$props" ]; then
        err "server.properties not found."
        return 1
    fi

    info "Applying optimization tweaks..."

    local tweaks=(
        "network-compression-threshold=256"
        "max-tick-time=60000"
        "max-world-size=10000"
        "sync-chunk-writes=false"
        "entity-broadcast-range-percentage=50"
        "simulation-distance=6"
        "view-distance=8"
        "spawn-monsters=true"
        "spawn-animals=true"
        "spawn-npcs=true"
        "spawn-protection=0"
        "difficulty=hard"
        "enable-command-block=true"
        "online-mode=true"
        "enable-query=false"
        "enable-rcon=false"
        "broadcast-rcon-to-ops=false"
        "rate-limit=10"
        "prevent-proxy-connections=false"
        "player-idle-timeout=30"
        "allow-flight=false"
        "motd=A Minecraft Server on Android"
    )

    for tweak in "${tweaks[@]}"; do
        local key="${tweak%%=*}"
        local val="${tweak#*=}"
        if grep -q "^$key=" "$props"; then
            sed -i "s|^$key=.*|$key=$val|" "$props"
        else
            echo "$key=$val" >> "$props"
        fi
    done
    ok "Optimization applied."
}

setup_service() {
    local svc_dir="$PREFIX/var/service"
    if [ ! -d "$svc_dir" ]; then
        info "Setting up Termux-services..."
        mkdir -p "$svc_dir"
        pkg install termux-services -y 2>/dev/null
    fi

    local svc_name="minecraft-server"
    local svc_path="$svc_dir/$svc_name"
    mkdir -p "$svc_path"
    cat > "$svc_path/run" << 'RUNEOT'
#!/data/data/com.termux/files/usr/bin/bash
exec 2>&1
exec /data/data/com.termux/files/usr/bin/bash /path/to/mcmanage.sh start
RUNEOT
    sed -i "s|/path/to/mcmanage.sh|$0|" "$svc_path/run"
    chmod +x "$svc_path/run"

    if [ ! -f "$svc_path/down" ]; then
        touch "$svc_path/down"
    fi

    ok "Service created at $svc_path"
    info "Enable: sv up $svc_name"
    info "Disable: sv down $svc_name"
    info "Status: sv status $svc_name"
}

init_server() {
    info "Starting full server setup..."
    echo

    info "[1/5] Installing dependencies (openjdk-17, screen, curl)..."
    pkg update -y
    pkg install openjdk-17 screen curl -y
    local deps_ok=true
    command -v java &>/dev/null || { err "Java install failed."; deps_ok=false; }
    command -v screen &>/dev/null || { err "Screen install failed."; deps_ok=false; }
    command -v curl &>/dev/null || { err "Curl install failed."; deps_ok=false; }
    $deps_ok && ok "Dependencies installed." || return 1
    echo

    info "[2/5] Making script executable and adding to PATH..."
    chmod +x "$0"
    link_to_path
    echo
    install
    if [ $? -ne 0 ] || [ ! -f "$SERVER_DIR/$SERVER_JAR" ]; then
        err "Server jar download failed."
        return 1
    fi
    ok "Server jar ready."
    echo

    info "[3/4] Accepting EULA..."
    echo 'eula=true' > "$SERVER_DIR/eula.txt"
    ok "EULA accepted."
    echo

    info "[4/4] Starting server for the first time..."
    start_server
    if [ $? -ne 0 ]; then
        err "Server failed to start. Run '$0 console' manually after fixing."
        return 1
    fi

    echo
    ok "========================================"
    ok "  Setup complete! Attaching to console..."
    ok "  Detach with Ctrl+A then D"
    ok "========================================"
    sleep 2
    console
}

link_to_path() {
    local target_dir="$HOME/.local/bin"
    mkdir -p "$target_dir"
    local target="$target_dir/mcmanage"

    [ -f "$target" ] || [ -L "$target" ] && rm -f "$target"

    chmod +x "$0"
    local abs_path; abs_path="$(readlink -f "$0")"
    ln -sf "$abs_path" "$target"

    if ! [ -f "$target" ] && ! [ -L "$target" ]; then
        err "Symlink creation failed."
        return 1
    fi
    ok "Linked: $0 -> $target"

    # Auto-add to PATH in .bashrc
    local bashrc="$HOME/.bashrc"
    local line='export PATH="$HOME/.local/bin:$PATH"'
    if [[ ":$PATH:" != *":$target_dir:"* ]]; then
        if ! grep -qF "$line" "$bashrc" 2>/dev/null; then
            echo "" >> "$bashrc"
            echo "# mcmanage" >> "$bashrc"
            echo "$line" >> "$bashrc"
            ok "Added ~/.local/bin to PATH in ~/.bashrc"
        fi
        # Source it for the current session
        export PATH="$HOME/.local/bin:$PATH"
        ok "Run 'mcmanage' from anywhere (restart Termux or source ~/.bashrc to make permanent)"
    else
        ok "Now run 'mcmanage' from anywhere!"
    fi
}

update_self() {
    local script_dir="$SCRIPT_DIR"
    info "Checking for updates..."

    if [ -d "$script_dir/.git" ]; then
        info "Updating via git pull..."
        (cd "$script_dir" && git pull)
        if [ $? -ne 0 ]; then
            err "Git pull failed."
            return 1
        fi
        info "Re-running install.sh..."
        if [ -f "$script_dir/install.sh" ]; then
            chmod +x "$script_dir/install.sh"
            "$script_dir/install.sh"
        else
            err "install.sh not found."
            return 1
        fi
    else
        info "Downloading latest from GitHub..."
        local target="$HOME/.local/bin/mcmanage"
        local web_dir="$HOME/.local/bin"
        local repo="https://raw.githubusercontent.com/Kaedo17/msm-webconsole-termux/main"
        curl -sSfLo "$target" "$repo/mcmanage.sh" || { err "Download failed."; return 1; }
        for mod in webconsole.py mc_state.py mc_helpers.py mc_properties.py mc_modrinth.py mc_curseforge.py mc_server.py mc_routes.py mc_instances.py mc_downloads.py mc_playit.py; do
            curl -sSfLo "$web_dir/$mod" "$repo/$mod" || { err "Failed to download $mod"; return 1; }
        done
        chmod +x "$target"
        ok "Updated mcmanage.sh and all web modules"
    fi
    ok "Update complete!"
}

launch_web_ui() {
    local web_py="$SCRIPT_DIR/webconsole.py"
    if [ ! -f "$web_py" ]; then
        web_py="$HOME/.local/bin/webconsole.py"
    fi
    if [ ! -f "$web_py" ]; then
        err "webconsole.py not found alongside mcmanage.sh"
        err "Download it from the same repository as mcmanage.sh"
        return 1
    fi
    if ! command -v python3 &>/dev/null; then
        err "Python 3 not found. Install: pkg install python"
        return 1
    fi
    # Auto-install Flask if missing
    if ! python3 -c "import flask" 2>/dev/null; then
        info "Installing Flask..."
        # Try pip - on Termux, python-pip might not be installed by default
        python3 -m pip install flask 2>/dev/null || pip install flask 2>/dev/null || {
            info "pip not found, installing python-pip..."
            pkg install python-pip -y 2>/dev/null
            python3 -m pip install flask || { err "Failed to install Flask. Try: pkg install python-pip && pip install flask"; return 1; }
        }
    fi
    # If --dir was given, import it into ~/mc-servers/ first
    if [ "$SERVER_DIR" != "$SCRIPT_DIR" ]; then
        info "Importing server from $SERVER_DIR ..."
        python3 "$web_py" --dir "$SERVER_DIR" --headless 2>&1 || true
    fi
    info "Launching web UI..."
    info "Open http://localhost:5000 in your browser"
    echo
    python3 "$web_py"
}

usage() {
    cat <<EOF
\e[36mMinecraft Server Manager for Termux\e[0m

\e[33mUsage:\e[0m
  $0 [--dir /path/to/server] \e[36m<command>\e[0m [options]

\e[33mCommands:\e[0m
  init               Full setup: install deps, download jar, accept EULA, start & console
  link               Symlink this script to ~/.local/bin/mcmanage (PATH access)
  start              Start the server
  stop [sec]         Stop server (default 30s warning)
  restart [sec]      Restart server
  console            Attach to server console
  cmd <command>      Send a command to the server
  status             Show server status
  backup             Backup world data
  backups            List backups
  restore <file>     Restore a backup
  logs [lines]       Show recent log output (default 50)
  watch              Follow log output in real-time
  props              Edit server.properties
  optimize           Apply optimization tweaks to server.properties
  install            Download and install a server jar
  update             Update mcmanage.sh and webconsole.py to latest
  service            Create a termux-services entry
  web                Launch web management UI (Python Flask app)
  help               Show this help

\e[33mQuick start:\e[0m
  \$0 init       # one-command setup (install deps, jar, accept EULA, start)
  \$0 link       # add to PATH: run 'mcmanage' from anywhere

\e[33mExamples:\e[0m
  \$0 start
  \$0 --dir ~/minecraft-server start
  \$0 stop 15
  \$0 cmd "say Hello everyone!"
  \$0 cmd "whitelist add Steve"
  \$0 logs 100
  \$0 backup

\e[33mArguments:\e[0m
  --dir <path>       Server directory   (default: script directory)

\e[33mEnvironment:\e[0m
  SERVER_DIR         Server directory   (default: script directory)
  SERVER_JAR         Jar filename       (default: server.jar)
  MAX_RAM            Max heap size      (default: 2G)
  MAX_BACKUPS        Max backups to keep (default: 7)
  LOG_FILE           Path to log file   (default: \$SERVER_DIR/server.log)

\e[33mManual setup steps:\e[0m
  pkg install openjdk-17 screen curl
  chmod +x \$0
  echo 'eula=true' > eula.txt
  \$0 start
  \$0 console   (Ctrl+A then D to detach)
EOF
}

# ── Parse --dir flag ──
ARGS=()
while [ $# -gt 0 ]; do
    case "$1" in
        --dir)
            if [ -z "$2" ]; then err "--dir requires a path"; exit 1; fi
            SERVER_DIR="$2"
            shift 2
            ;;
        --dir=*)
            SERVER_DIR="${1#*=}"
            shift
            ;;
        *)
            ARGS+=("$1")
            shift
            ;;
    esac
done
set -- "${ARGS[@]}"

# Recompute path-dependent vars after SERVER_DIR is set
PID_FILE="$SERVER_DIR/server.pid"
LOG_FILE="$SERVER_DIR/server.log"
BACKUP_DIR="$SERVER_DIR/backups"

case "${1:-help}" in
    start)     start_server ;;
    stop)      stop_server "${2:-30}" ;;
    restart)   restart_server "${2:-30}" ;;
    console)   console ;;
    cmd)       shift; send_command "$*" ;;
    status)    status ;;
    backup)    backup ;;
    backups)   list_backups ;;
    restore)   shift; restore_backup "$*" ;;
    logs)      logs "${2:-50}" ;;
    watch)     watch_logs ;;
    props)     edit_properties ;;
    optimize)  optimize ;;
    install)   install ;;
    init)      init_server ;;
    link)      link_to_path ;;
    web)       launch_web_ui ;;
    update)    update_self ;;
    service)   setup_service ;;
    help|*)    usage ;;
esac
