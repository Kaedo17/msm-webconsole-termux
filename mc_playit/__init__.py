"""Playit.gg tunnel manager — platform-dispatched.

Automatically selects the right implementation:
  - Windows: uses the modern playit CLI (playit.exe) with service management
  - Unix/Termux: uses separate playitd/playit-cli binaries with subprocess management

Usage (same regardless of platform):
    import mc_playit
    status = mc_playit.check_tunnel_status()
    ok, msg = mc_playit.start_daemon()
    ...
"""

import sys as _sys

if _sys.platform == "win32":
    from mc_playit._windows import (  # noqa: F401, E501
        # Installation / status
        is_installed,
        install_commands,
        is_claimed,
        check_tunnel_status,
        get_tunnel_info,
        # Daemon management
        start_daemon,
        stop_daemon,
        # Logs
        get_logs,
        # Claim flow
        run_cli,
        complete_claim,     # Windows-only: finalises claim after user visits URL
        parse_claim_url,
        parse_tunnel_urls,
    )
else:
    from mc_playit._unix import (   # noqa: F401, E501
        # Installation / status
        is_installed,
        install_commands,
        is_claimed,
        check_tunnel_status,
        get_tunnel_info,
        # Daemon management
        start_daemon,
        stop_daemon,
        # Logs
        get_logs,
        # Claim flow
        run_cli,
        parse_claim_url,
        parse_tunnel_urls,
    )
