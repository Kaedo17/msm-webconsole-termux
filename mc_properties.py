"""Minecraft server.properties schema and editor."""

PROPS_SCHEMA = {
    "online-mode":           {"type": "bool",   "cat": "server",   "label": "Online Mode",       "desc": "Authenticate players with Mojang"},
    "difficulty":            {"type": "enum",   "cat": "gameplay", "label": "Difficulty",         "desc": "Game difficulty", "opts": ["peaceful","easy","normal","hard"]},
    "gamemode":              {"type": "enum",   "cat": "gameplay", "label": "Default Gamemode",   "desc": "Default game mode for new players", "opts": ["survival","creative","adventure","spectator"]},
    "pvp":                   {"type": "bool",   "cat": "gameplay", "label": "PvP",               "desc": "Allow player versus player combat"},
    "hardcore":              {"type": "bool",   "cat": "gameplay", "label": "Hardcore",           "desc": "Ban on death"},
    "enable-command-block":  {"type": "bool",   "cat": "server",   "label": "Command Blocks",    "desc": "Enable command blocks"},
    "spawn-monsters":        {"type": "bool",   "cat": "world",    "label": "Spawn Monsters",     "desc": "Natural monster spawning"},
    "spawn-animals":         {"type": "bool",   "cat": "world",    "label": "Spawn Animals",      "desc": "Natural animal spawning"},
    "spawn-npcs":            {"type": "bool",   "cat": "world",    "label": "Spawn NPCs",         "desc": "Natural villager spawning"},
    "allow-flight":          {"type": "bool",   "cat": "gameplay", "label": "Allow Flight",       "desc": "Allow flying without cheat"},
    "white-list":            {"type": "bool",   "cat": "server",   "label": "Whitelist",          "desc": "Only whitelisted players can join"},
    "enforce-whitelist":     {"type": "bool",   "cat": "server",   "label": "Enforce Whitelist",  "desc": "Kick non-whitelisted players on reload"},
    "enable-query":          {"type": "bool",   "cat": "network",  "label": "Query",              "desc": "Enable GameSpy query protocol"},
    "enable-rcon":           {"type": "bool",   "cat": "network",  "label": "RCON",               "desc": "Enable remote console access"},
    "broadcast-rcon-to-ops": {"type": "bool",   "cat": "network",  "label": "Broadcast RCON",     "desc": "Broadcast RCON commands to ops"},
    "prevent-proxy-connections":{"type": "bool","cat": "network",  "label": "Prevent Proxy",      "desc": "Block proxy connections"},
    "sync-chunk-writes":     {"type": "bool",   "cat": "world",    "label": "Sync Chunk Writes",  "desc": "Sync world writes to disk"},
    "max-players":           {"type": "number", "cat": "server",   "label": "Max Players",        "desc": "Maximum concurrent players", "min": 1, "max": 100},
    "view-distance":         {"type": "number", "cat": "world",    "label": "View Distance",      "desc": "Client view radius in chunks", "min": 2, "max": 32},
    "simulation-distance":   {"type": "number", "cat": "world",    "label": "Sim Distance",       "desc": "Entity simulation radius", "min": 2, "max": 32},
    "server-port":           {"type": "number", "cat": "network",  "label": "Server Port",        "desc": "Port to listen on", "min": 1, "max": 65535},
    "spawn-protection":      {"type": "number", "cat": "world",    "label": "Spawn Protection",   "desc": "Radius around spawn protected", "min": 0},
    "player-idle-timeout":   {"type": "number", "cat": "server",   "label": "Idle Timeout",       "desc": "Kick idle players after (minutes)", "min": 0},
    "max-world-size":        {"type": "number", "cat": "world",    "label": "Max World Size",     "desc": "World border radius", "min": 1},
    "rate-limit":            {"type": "number", "cat": "network",  "label": "Rate Limit",         "desc": "Packets per second limit", "min": 0},
    "max-tick-time":         {"type": "number", "cat": "server",   "label": "Max Tick Time",      "desc": "Max ms per tick before watchdog", "min": 0},
    "entity-broadcast-range-percentage": {"type": "number", "cat": "world", "label": "Entity Range %", "desc": "Entity tracking range %", "min": 10, "max": 1000},
    "network-compression-threshold": {"type": "number", "cat": "network", "label": "Compression", "desc": "Network compression threshold", "min": -1},
    "motd":                  {"type": "string", "cat": "server",   "label": "MOTD",              "desc": "Message of the Day"},
    "resource-pack":         {"type": "string", "cat": "server",   "label": "Resource Pack URL", "desc": "URL to a resource pack"},
    "resource-pack-sha1":    {"type": "string", "cat": "server",   "label": "Pack SHA1",         "desc": "SHA1 hash of the resource pack"},
    "level-name":            {"type": "string", "cat": "world",    "label": "World Name",        "desc": "World folder name"},
    "level-seed":            {"type": "string", "cat": "world",    "label": "World Seed",        "desc": "Random seed for world generation"},
    "generator-settings":    {"type": "string", "cat": "world",    "label": "Generator Settings", "desc": "Superflat/amplified settings"},
}


def save_props(server_dir, changes):
    pf = server_dir / "server.properties"
    if not pf.exists():
        lines = ["#Minecraft server properties\n"]
        for k, s in PROPS_SCHEMA.items():
            default = changes.get(k) or s.get("default", "")
            lines.append(f"{k}={default}\n")
        for k, v in changes.items():
            if k not in PROPS_SCHEMA:
                lines.append(f"{k}={v}\n")
        pf.write_text("".join(lines), encoding="utf-8")
        return True, "Properties saved"
    lines = pf.read_text(encoding="utf-8").splitlines(keepends=True)
    changed = set(changes.keys())
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and "=" in stripped:
            k = stripped.split("=", 1)[0].strip()
            if k in changed:
                lines[i] = f"{k}={changes[k]}\n"
                changed.discard(k)
    for k in changed:
        lines.append(f"{k}={changes[k]}\n")
    pf.write_text("".join(lines), encoding="utf-8")
    return True, "Properties saved"
