"""
MonadBlitz CLI — Entry point.

Usage:
    monadblitz-cli            # Full TUI mode (default)
    monadblitz-cli --simple   # Simple log mode (no TUI, plain stdout)
    monadblitz-cli --demo     # Demo mode with simulated events (no backend needed)
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import datetime


# ---------------------------------------------------------------------------
# Simple (non-TUI) log mode
# ---------------------------------------------------------------------------

async def simple_log_mode(ws_url: str) -> None:
    """Connect to the orchestrator WebSocket and print coloured logs via Rich."""
    from rich.console import Console
    from rich.text import Text

    try:
        import websockets
    except ImportError:
        print("websockets is not installed. Run: pip install websockets")
        sys.exit(1)

    from .config import settings

    console = Console()

    ROLE_COLOURS = {
        "[ORCH]":   "bold cyan",
        "[ALPHA]":  "bold green",
        "[BETA]":   "bold yellow",
        "[GAMMA]":  "bold red",
        "[CHAIN]":  "bold magenta",
        "[JUDGE]":  "bold blue",
        "[MEMORY]": "bold white",
        "[ERROR]":  "bold red",
        "[INFO]":   "dim",
    }

    url = ws_url or settings.WEBSOCKET_URL

    console.print(f"\n[bold cyan]MonadBlitz Simple Log Mode[/bold cyan]  ->  {url}\n")
    console.print("[dim]Press Ctrl-C to exit.[/dim]\n")

    while True:
        try:
            async with websockets.connect(url, ping_interval=20) as ws:
                console.print("[bold green]Connected[/bold green]")
                async for raw in ws:
                    try:
                        msg = json.loads(raw)
                        text = msg.get("message", str(msg))
                    except (json.JSONDecodeError, TypeError):
                        text = str(raw)

                    ts = datetime.now().strftime("%H:%M:%S")

                    # Detect role tag for colour
                    style = "white"
                    for tag, colour in ROLE_COLOURS.items():
                        if tag in text:
                            style = colour
                            break

                    console.print(f"[dim]{ts}[/dim]  {text}", style=style)

        except KeyboardInterrupt:
            console.print("\n[dim]Exiting.[/dim]")
            return
        except Exception as exc:
            console.print(f"[red]Connection error: {exc}[/red] — reconnecting in 3s…")
            await asyncio.sleep(3)


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        prog="monadblitz-cli",
        description="MonadBlitz — AI Agent Coordination on Monad · Live Dashboard",
    )
    parser.add_argument(
        "--simple",
        action="store_true",
        help="Simple log mode: connect to WebSocket and print to stdout (no TUI).",
    )
    parser.add_argument(
        "--ws-url",
        default=None,
        metavar="URL",
        help="Override the WebSocket URL (default: from config / .env).",
    )
    parser.add_argument(
        "--version",
        action="version",
        version="monadblitz-cli 0.1.0",
    )

    args = parser.parse_args()

    if args.simple:
        try:
            asyncio.run(simple_log_mode(args.ws_url or ""))
        except KeyboardInterrupt:
            pass
        return

    # Default: full TUI mode
    try:
        from .app import MonadBlitzCLI
    except ImportError as exc:
        print(f"Could not import TUI dependencies: {exc}")
        print("Try: pip install textual  or run with --simple for plain log mode.")
        sys.exit(1)

    app = MonadBlitzCLI()
    app.run()


if __name__ == "__main__":
    main()
