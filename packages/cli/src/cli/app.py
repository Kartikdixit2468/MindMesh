"""
MonadBlitz CLI — Beautiful two-pane terminal dashboard.

LEFT  PANE : Live orchestrator logs, colored by agent role.
RIGHT PANE : Live task memory tree showing round progression,
             scores and on-chain anchoring.
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime
from typing import Any

import websockets
import aiohttp

from rich.text import Text
from rich.tree import Tree as RichTree
from rich.panel import Panel
from rich.columns import Columns
from rich.align import Align

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual import work
from textual.widgets import Header, Footer, RichLog, Static, Label

from .config import settings

# ---------------------------------------------------------------------------
# Colour palette — every agent role gets a distinct personality
# ---------------------------------------------------------------------------

ROLE_STYLES: dict[str, tuple[str, str]] = {
    # tag          text-colour   glyph
    "[ORCH]":   ("cyan",    "⬡"),
    "[ALPHA]":  ("green",   "α"),
    "[BETA]":   ("yellow",  "β"),
    "[GAMMA]":  ("red",     "γ"),
    "[CHAIN]":  ("magenta", "⛓"),
    "[JUDGE]":  ("blue",    "⚖"),
    "[MEMORY]": ("white",   "🧠"),
    "[ERROR]":  ("red",     "✖"),
    "[INFO]":   ("bright_black", "·"),
}

SCORE_THRESHOLDS = {
    "winner":   0.85,
    "good":     0.75,
    "mediocre": 0.60,
}


def _score_colour(score: float) -> str:
    if score >= SCORE_THRESHOLDS["winner"]:
        return "bold bright_green"
    if score >= SCORE_THRESHOLDS["good"]:
        return "bold yellow"
    if score >= SCORE_THRESHOLDS["mediocre"]:
        return "bold dark_orange"
    return "bold red"


def _status_badge(status: str) -> tuple[str, str]:
    """Return (label, style) for a round/query status."""
    mapping = {
        "ACTIVE":     ("◉ ACTIVE",     "bold cyan"),
        "ESCALATED":  ("⬆ ESCALATED",  "bold yellow"),
        "RESOLVED":   ("✓ RESOLVED",   "bold green"),
        "FAILED":     ("✖ FAILED",     "bold red"),
        "PENDING":    ("○ PENDING",    "dim white"),
        "ANCHORED":   ("⛓ ANCHORED",   "bold magenta"),
    }
    return mapping.get(status.upper(), (status, "white"))


# ---------------------------------------------------------------------------
# Left pane — orchestrator log stream
# ---------------------------------------------------------------------------

class OrchestratorLogPane(RichLog):
    """
    Scrolling, colour-coded log pane.
    Each message is tagged by its agent role and rendered with a matching style.
    """

    DEFAULT_CSS = """
    OrchestratorLogPane {
        scrollbar-color: cyan;
        scrollbar-size: 1 1;
    }
    """

    # Pre-compiled role tag lookup for O(1) matching
    _ROLE_TAGS = list(ROLE_STYLES.keys())

    def _detect_role(self, message: str) -> str | None:
        for tag in self._ROLE_TAGS:
            if tag in message:
                return tag
        return None

    def add_log(self, message: str, timestamp: bool = True) -> None:
        """
        Render *message* with agent-role colouring and an optional timestamp.
        Supports both plain strings and Rich markup strings.
        """
        role = self._detect_role(message)

        if timestamp:
            ts = datetime.now().strftime("%H:%M:%S")
            ts_text = Text(f"{ts} ", style="dim bright_black")
        else:
            ts_text = Text("")

        if role:
            colour, glyph = ROLE_STYLES[role]
            # Replace the bare [TAG] with a coloured glyph + tag
            styled_tag = Text(f"{glyph} {role} ", style=f"bold {colour}")
            rest = message.replace(role, "", 1).strip()
            body = Text.from_markup(rest) if "[/" in rest or "[" in rest else Text(rest)
            line = ts_text + styled_tag + body
        else:
            line = ts_text + Text.from_markup(message)

        self.write(line)


# ---------------------------------------------------------------------------
# Right pane — memory tree
# ---------------------------------------------------------------------------

class MemoryTreePane(Static):
    """
    Renders the live task memory tree using Rich's Tree primitive.

    Expected memory_data shape (from /api/memory/{id}):
    {
      "query_id": 42,
      "query_text": "Optimize this SQL query",
      "status": "ACTIVE",
      "bounty": "0.25",
      "rounds": [
        {
          "round": 1,
          "status": "ESCALATED",
          "responses": [
            {"agent": "alpha", "score": 0.61, "summary": "Used SLOAD…", "winner": false},
            {"agent": "beta",  "score": 0.58, "summary": "Added indexes…", "winner": false}
          ],
          "orchestrator_note": "Escalated (best < 0.75)",
          "tx_hash": null
        },
        {
          "round": 2,
          "status": "RESOLVED",
          "responses": [
            {"agent": "alpha", "score": 0.91, "summary": "Parallel reads…", "winner": true}
          ],
          "orchestrator_note": null,
          "tx_hash": "0xabc123…"
        }
      ]
    }
    """

    DEFAULT_CSS = """
    MemoryTreePane {
        scrollbar-color: green;
        overflow-y: auto;
        overflow-x: auto;
    }
    """

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._current_data: dict | None = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def update_memory(self, memory_data: dict) -> None:
        self._current_data = memory_data
        self._render()

    def clear_memory(self) -> None:
        self._current_data = None
        self.update(Align.center(
            Text("\n\n  Waiting for active queries…", style="dim italic cyan"),
            vertical="middle",
        ))

    # ------------------------------------------------------------------
    # Rendering helpers
    # ------------------------------------------------------------------

    def _render(self) -> None:
        if not self._current_data:
            self.clear_memory()
            return

        data = self._current_data
        tree = self._build_tree(data)
        self.update(tree)

    def _build_tree(self, data: dict) -> RichTree:
        qid    = data.get("query_id", "?")
        text   = data.get("query_text", "(no query text)")
        status = data.get("status", "UNKNOWN")
        bounty = data.get("bounty", "?")
        rounds = data.get("rounds", [])

        badge_label, badge_style = _status_badge(status)

        # Root node
        root_label = Text()
        root_label.append(f"Task #{qid}  ", style="bold bright_white")
        root_label.append(badge_label, style=badge_style)
        root_label.append(f"  bounty: ", style="dim")
        root_label.append(f"{bounty} MON", style="bold magenta")

        tree = RichTree(root_label, guide_style="dim cyan")

        # Truncate query text for display
        max_q = 55
        display_q = (text[:max_q] + "…") if len(text) > max_q else text
        tree.add(Text(f'"{display_q}"', style="italic bright_white"))

        # --- Rounds ---
        for r in rounds:
            round_node = self._build_round_node(r)
            tree.add(round_node)

        # If no rounds yet
        if not rounds:
            tree.add(Text("  No rounds yet…", style="dim italic"))

        return tree

    def _build_round_node(self, r: dict) -> RichTree:
        rnum   = r.get("round", "?")
        status = r.get("status", "UNKNOWN")
        tx     = r.get("tx_hash")
        note   = r.get("orchestrator_note")
        resps  = r.get("responses", [])

        badge_label, badge_style = _status_badge(status)

        label = Text()
        label.append(f"Round {rnum}  ", style="bold white")
        label.append(badge_label, style=badge_style)

        rnode = RichTree(label, guide_style="dim")

        # Agent responses
        for resp in resps:
            rnode.add(self._build_response_leaf(resp))

        # Orchestrator note
        if note:
            note_text = Text()
            note_text.append("⬡ ORCH  ", style="bold cyan")
            note_text.append(note, style="italic dim white")
            rnode.add(note_text)

        # On-chain anchor
        if tx:
            chain_text = Text()
            chain_text.append("⛓ Tx  ", style="bold magenta")
            chain_text.append(tx, style="underline magenta")
            chain_text.append("  ✓", style="bold bright_green")
            rnode.add(chain_text)

        return rnode

    def _build_response_leaf(self, resp: dict) -> Text:
        agent   = resp.get("agent", "?").upper()
        score   = resp.get("score", 0.0)
        summary = resp.get("summary", "")
        winner  = resp.get("winner", False)

        # Agent glyph
        tag = f"[{agent}]"
        colour, glyph = ROLE_STYLES.get(tag, ("white", agent[0]))

        leaf = Text()
        leaf.append(f"{glyph} {agent:<6}", style=f"bold {colour}")
        leaf.append(f"  score: ")
        leaf.append(f"{score:.2f}", style=_score_colour(score))

        # Summary (truncated)
        if summary:
            max_s = 42
            display_s = (summary[:max_s] + "…") if len(summary) > max_s else summary
            leaf.append(f"  — {display_s}", style="dim white")

        if winner:
            leaf.append("  ★ WINNER", style="bold bright_green blink")

        return leaf


# ---------------------------------------------------------------------------
# Status bar
# ---------------------------------------------------------------------------

class StatusBar(Static):
    """
    Bottom strip showing live system statistics.
    Updated whenever memory or connection state changes.
    """

    DEFAULT_CSS = """
    StatusBar {
        height: 3;
        content-align: center middle;
        text-style: bold;
    }
    """

    def __init__(self, **kwargs: Any) -> None:
        super().__init__("", **kwargs)
        self._connected = False
        self._active_queries = 0
        self._total_bounty = 0.0
        self._agents_online = 0

    def set_connected(self, connected: bool) -> None:
        self._connected = connected
        self._refresh()

    def set_stats(self, active_queries: int, total_bounty: float, agents_online: int) -> None:
        self._active_queries = active_queries
        self._total_bounty = total_bounty
        self._agents_online = agents_online
        self._refresh()

    def _refresh(self) -> None:
        conn_icon  = "[bold bright_green]● LIVE[/]" if self._connected else "[bold red]○ DISCONNECTED[/]"
        agents_str = f"[bold cyan]{self._agents_online}[/] agents"
        queries_str = f"[bold yellow]{self._active_queries}[/] active"
        bounty_str  = f"[bold magenta]{self._total_bounty:.3f} MON[/] bounty"

        sep = "  [dim]│[/]  "
        self.update(
            f"  {conn_icon}{sep}{agents_str}{sep}{queries_str}{sep}{bounty_str}  "
        )


# ---------------------------------------------------------------------------
# Main application
# ---------------------------------------------------------------------------

MONADBLITZ_CSS = """
Screen {
    layout: vertical;
    background: $background;
}

Header {
    background: $primary-darken-3;
    color: $text;
    text-style: bold;
}

#main-container {
    layout: horizontal;
    height: 1fr;
}

#log-pane {
    width: 55%;
    border: tall cyan;
    padding: 0 1;
    background: $surface-darken-1;
}

#log-pane > .log--title {
    color: cyan;
    text-style: bold;
}

#memory-pane {
    width: 45%;
    border: tall green;
    padding: 1 1;
    background: $surface-darken-2;
    overflow-y: auto;
    overflow-x: auto;
}

#status-bar {
    height: 3;
    background: $surface;
    border-top: solid $primary-darken-2;
    padding: 0 2;
    content-align: left middle;
}

Footer {
    background: $primary-darken-3;
}
"""


class MonadBlitzCLI(App):
    """MonadBlitz orchestrator live dashboard."""

    CSS = MONADBLITZ_CSS

    BINDINGS = [
        Binding("q", "quit",        "Quit"),
        Binding("n", "new_query",   "New Query"),
        Binding("r", "refresh",     "Refresh"),
        Binding("c", "clear_logs",  "Clear Logs"),
    ]

    TITLE = "MonadBlitz"
    SUB_TITLE = "AI Agent Coordination on Monad · Live Dashboard"

    # ------------------------------------------------------------------
    # Composition
    # ------------------------------------------------------------------

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Horizontal(id="main-container"):
            yield OrchestratorLogPane(
                id="log-pane",
                markup=True,
                highlight=True,
                max_lines=settings.LOG_MAX_LINES,
            )
            yield MemoryTreePane(id="memory-pane")
        yield StatusBar(id="status-bar")
        yield Footer()

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def on_mount(self) -> None:
        self._print_banner()
        self.subscribe_to_logs()
        self.poll_memory()

    def _print_banner(self) -> None:
        log = self.query_one("#log-pane", OrchestratorLogPane)
        lines = [
            "",
            "[bold cyan]  ███╗   ███╗ ██████╗ ███╗   ██╗ █████╗ ██████╗ [/]",
            "[bold cyan]  ████╗ ████║██╔═══██╗████╗  ██║██╔══██╗██╔══██╗[/]",
            "[bold cyan]  ██╔████╔██║██║   ██║██╔██╗ ██║███████║██║  ██║[/]",
            "[bold cyan]  ██║╚██╔╝██║██║   ██║██║╚██╗██║██╔══██║██║  ██║[/]",
            "[bold cyan]  ██║ ╚═╝ ██║╚██████╔╝██║ ╚████║██║  ██║██████╔╝[/]",
            "[bold cyan]  ╚═╝     ╚═╝ ╚═════╝ ╚═╝  ╚═══╝╚═╝  ╚═╝╚═════╝ [/]",
            "",
            "[bold bright_white]         ⚡  B L I T Z  ·  AI on Monad  ⚡[/]",
            "",
            "[dim]  Connecting to orchestrator at "
            f"[underline]{settings.ORCHESTRATOR_BASE_URL}[/underline]…[/]",
            "",
        ]
        for line in lines:
            log.add_log(line, timestamp=False)

    # ------------------------------------------------------------------
    # Worker: WebSocket log stream
    # ------------------------------------------------------------------

    @work(exclusive=True, thread=False)
    async def subscribe_to_logs(self) -> None:
        log   = self.query_one("#log-pane",   OrchestratorLogPane)
        sbar  = self.query_one("#status-bar", StatusBar)

        while True:
            try:
                async with websockets.connect(
                    settings.WEBSOCKET_URL,
                    ping_interval=20,
                    ping_timeout=20,
                ) as ws:
                    sbar.set_connected(True)
                    log.add_log("[ORCH] [bold green]✓ Connected to orchestrator WebSocket[/]")

                    async for raw in ws:
                        try:
                            msg = json.loads(raw)
                        except json.JSONDecodeError:
                            log.add_log(f"[INFO] (raw) {raw[:120]}")
                            continue

                        mtype = msg.get("type", "log")

                        if mtype == "log":
                            log.add_log(msg.get("message", ""))

                        elif mtype == "status_change":
                            qid    = msg.get("query_id", "?")
                            status = msg.get("status", "?")
                            badge_label, badge_style = _status_badge(status)
                            log.add_log(
                                f"[ORCH] Query [bold]#{qid}[/bold] → "
                                f"[{badge_style}]{badge_label}[/{badge_style}]"
                            )

                        elif mtype == "agent_result":
                            agent = msg.get("agent", "?").upper()
                            score = msg.get("score", 0.0)
                            tag   = f"[{agent}]"
                            log.add_log(
                                f"{tag} score=[{_score_colour(score)}]{score:.3f}[/]  "
                                f"{msg.get('summary', '')[:60]}"
                            )

                        elif mtype == "chain_anchor":
                            tx  = msg.get("tx_hash", "?")
                            qid = msg.get("query_id", "?")
                            log.add_log(
                                f"[CHAIN] Query #{qid} anchored on-chain  "
                                f"[bold magenta]{tx}[/]  [bold bright_green]✓[/]"
                            )

                        elif mtype == "stats":
                            sbar.set_stats(
                                active_queries=msg.get("active_queries", 0),
                                total_bounty=msg.get("total_bounty", 0.0),
                                agents_online=msg.get("agents_online", 0),
                            )

            except (websockets.exceptions.ConnectionClosed,
                    websockets.exceptions.WebSocketException,
                    OSError) as exc:
                sbar.set_connected(False)
                log.add_log(
                    f"[ERROR] WebSocket error: [red]{exc}[/red]  "
                    f"— reconnecting in {settings.WS_RECONNECT_DELAY:.0f}s…"
                )

            except Exception as exc:
                sbar.set_connected(False)
                log.add_log(f"[ERROR] Unexpected error: [red]{exc}[/red]")

            await asyncio.sleep(settings.WS_RECONNECT_DELAY)

    # ------------------------------------------------------------------
    # Worker: HTTP memory polling
    # ------------------------------------------------------------------

    @work(exclusive=False, thread=False)
    async def poll_memory(self) -> None:
        memory_pane = self.query_one("#memory-pane", MemoryTreePane)
        sbar        = self.query_one("#status-bar",  StatusBar)

        # Show placeholder until first successful fetch
        memory_pane.clear_memory()

        connector = aiohttp.TCPConnector(limit=4)
        async with aiohttp.ClientSession(connector=connector) as session:
            while True:
                try:
                    async with session.get(
                        f"{settings.ORCHESTRATOR_BASE_URL}/api/queries",
                        params={"status": "active"},
                        timeout=aiohttp.ClientTimeout(total=5),
                    ) as resp:
                        if resp.status == 200:
                            queries: list[dict] = await resp.json()

                            # Update stats in status bar
                            total_bounty = sum(
                                float(q.get("bounty", 0)) for q in queries
                            )
                            sbar.set_stats(
                                active_queries=len(queries),
                                total_bounty=total_bounty,
                                agents_online=0,   # updated via WS stats event
                            )

                            if queries:
                                latest = queries[0]
                                qid = latest.get("id") or latest.get("query_id")
                                async with session.get(
                                    f"{settings.ORCHESTRATOR_BASE_URL}/api/memory/{qid}",
                                    timeout=aiohttp.ClientTimeout(total=5),
                                ) as mem_resp:
                                    if mem_resp.status == 200:
                                        memory_data = await mem_resp.json()
                                        memory_pane.update_memory(memory_data)
                            else:
                                memory_pane.clear_memory()

                except (aiohttp.ClientError, asyncio.TimeoutError):
                    pass   # Silent — log pane already shows WS errors
                except Exception:
                    pass

                await asyncio.sleep(settings.MEMORY_POLL_INTERVAL)

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def action_quit(self) -> None:
        self.exit()

    def action_clear_logs(self) -> None:
        self.query_one("#log-pane", OrchestratorLogPane).clear()
        self._print_banner()

    def action_refresh(self) -> None:
        log = self.query_one("#log-pane", OrchestratorLogPane)
        log.add_log("[INFO] Manual refresh triggered")
        # Restart memory poll (non-exclusive so it spawns a new task)
        self.poll_memory()

    def action_new_query(self) -> None:
        log = self.query_one("#log-pane", OrchestratorLogPane)
        log.add_log("[INFO] Use the web UI or API to submit a new query.")
