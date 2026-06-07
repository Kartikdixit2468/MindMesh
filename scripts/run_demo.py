"""
MonadBlitz End-to-End Demo Script

Submits a query to the orchestrator and polls for the result.
Shows real-time task memory events as the orchestrator processes it.

Usage:
    python scripts/run_demo.py [--problem "your question here"]
    python scripts/run_demo.py --quick   # use a preset easy question
"""
import argparse
import asyncio
import json
import sys
import time
from typing import Optional

try:
    import aiohttp
    from rich.console import Console
    from rich.live import Live
    from rich.panel import Panel
    from rich.progress import Progress, SpinnerColumn, TextColumn, TimeElapsedColumn
    from rich.table import Table
    from rich.text import Text
    from rich.tree import Tree
except ImportError:
    sys.exit("Missing deps. Run: pip install aiohttp rich")

BASE_URL = "http://localhost:8000"
POLL_INTERVAL = 2.0
TIMEOUT = 180  # seconds

console = Console()

DEMO_PROBLEMS = [
    "Explain the key differences between optimistic rollups and ZK rollups for Ethereum scaling.",
    "Write a Solidity function to safely transfer ERC-20 tokens using the check-effects-interactions pattern.",
    "What is the Byzantine Generals Problem and how does Practical Byzantine Fault Tolerance (PBFT) solve it?",
    "Analyze the trade-offs between proof-of-work and proof-of-stake consensus mechanisms.",
]


async def submit_query(session: aiohttp.ClientSession, problem: str) -> str:
    async with session.post(
        f"{BASE_URL}/api/queries",
        json={"problem": problem, "reward": "0.05"},
    ) as resp:
        if resp.status not in (200, 201):
            txt = await resp.text()
            raise RuntimeError(f"Submit failed {resp.status}: {txt}")
        data = await resp.json()
        return data["id"]


async def poll_query(session: aiohttp.ClientSession, query_id: str) -> dict:
    async with session.get(f"{BASE_URL}/api/queries/{query_id}") as resp:
        resp.raise_for_status()
        return await resp.json()


async def get_memory(session: aiohttp.ClientSession, query_id: str) -> Optional[dict]:
    try:
        async with session.get(f"{BASE_URL}/api/queries/{query_id}/memory") as resp:
            if resp.status == 200:
                return await resp.json()
    except Exception:
        pass
    return None


def build_memory_tree(memory: dict) -> Tree:
    tree = Tree(f"[bold]Task Memory  [dim]query={memory.get('query_id','')[:12]}…[/dim][/bold]")
    content = memory.get("content", {})
    events = content.get("events", [])

    rounds: dict[int, list] = {}
    for ev in events:
        r = ev.get("round", 0)
        rounds.setdefault(r, []).append(ev)

    for r, evs in sorted(rounds.items()):
        rb = tree.add(f"[cyan]Round {r}[/cyan]")
        for ev in evs:
            et = ev.get("type", "?")
            if et == "routed":
                rb.add(f"[blue]routed[/blue]  agents={ev.get('agent_count', '?')}")
            elif et == "response":
                score = ev.get("score")
                sc = f"  score=[yellow]{score:.2f}[/yellow]" if score is not None else ""
                rb.add(f"[white]response[/white]  agent={ev.get('agent_address','?')[:12]}…{sc}")
            elif et == "escalation":
                rb.add(f"[orange3]escalation[/orange3]  {ev.get('reason','')[:60]}")
            elif et == "winner":
                rb.add(f"[green bold]winner[/green bold]  {ev.get('winner_address','?')[:14]}…  score={ev.get('score','?')}")
            else:
                rb.add(f"[dim]{et}[/dim]  {json.dumps(ev)[:80]}")

    return tree


def build_summary_table(query: dict, memory: Optional[dict]) -> Table:
    table = Table(show_header=False, box=None, padding=(0, 2))
    table.add_column("Key", style="bold cyan", width=20)
    table.add_column("Value")

    status = query.get("status", "?")
    status_colors = {
        "settled": "green",
        "failed": "red",
        "collecting": "yellow",
        "scoring": "magenta",
        "escalating": "orange3",
        "routing": "cyan",
    }
    color = status_colors.get(status.lower(), "white")
    table.add_row("Status", f"[{color}]{status}[/]")
    table.add_row("Query ID", query.get("id", "?")[:36])
    table.add_row("Problem", query.get("problem", "")[:80])
    table.add_row("Round", str(query.get("current_round", 1)))
    table.add_row("Responses", str(query.get("response_count", 0)))

    if memory:
        content = memory.get("content", {})
        events = content.get("events", [])
        winner_evs = [e for e in events if e.get("type") == "winner"]
        if winner_evs:
            w = winner_evs[-1]
            table.add_row("Winner", f"[green]{w.get('winner_address','?')[:18]}…[/green]")
            table.add_row("Score", f"[green]{w.get('score', '?')}[/green]")

    return table


async def run_demo(problem: str) -> None:
    console.print()
    console.print(
        Panel.fit(
            "[bold cyan]MonadBlitz Demo[/bold cyan]\n"
            "[dim]Decentralized AI Agent Coordination on Monad[/dim]",
            border_style="cyan",
        )
    )
    console.print(f"\n[bold]Problem:[/bold] {problem}\n")

    async with aiohttp.ClientSession() as session:
        # Health check
        try:
            async with session.get(f"{BASE_URL}/health", timeout=aiohttp.ClientTimeout(total=5)) as r:
                if r.status != 200:
                    console.print(f"[red]Orchestrator not healthy: {r.status}[/red]")
                    sys.exit(1)
            console.print("[green]✓ Orchestrator is healthy[/green]")
        except Exception as exc:
            console.print(f"[red]Cannot reach orchestrator at {BASE_URL}: {exc}[/red]")
            console.print("[dim]Make sure the orchestrator is running: make orchestrator[/dim]")
            sys.exit(1)

        # Submit
        console.print("[cyan]→ Submitting query…[/cyan]")
        start = time.time()
        try:
            query_id = await submit_query(session, problem)
        except Exception as exc:
            console.print(f"[red]Failed to submit: {exc}[/red]")
            sys.exit(1)
        console.print(f"[green]✓ Query created:[/green] {query_id}\n")

        # Poll loop
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            TimeElapsedColumn(),
            console=console,
            transient=True,
        ) as progress:
            task = progress.add_task("Processing…", total=None)

            terminal_statuses = {"settled", "failed"}
            query: dict = {}
            memory: Optional[dict] = None

            while True:
                elapsed = time.time() - start
                if elapsed > TIMEOUT:
                    console.print(f"[red]Timeout after {TIMEOUT}s[/red]")
                    break

                query = await poll_query(session, query_id)
                memory = await get_memory(session, query_id)
                status = query.get("status", "?")
                progress.update(task, description=f"Status: [bold]{status}[/bold]  Round: {query.get('current_round', 1)}  Elapsed: {elapsed:.0f}s")

                if status.lower() in terminal_statuses:
                    break

                await asyncio.sleep(POLL_INTERVAL)

    # Final output
    console.print()
    console.print(build_summary_table(query, memory))

    if memory:
        console.print()
        console.print(build_memory_tree(memory))

    # Show winning response
    if query.get("status", "").lower() == "settled" and memory:
        content = memory.get("content", {})
        events = content.get("events", [])
        winner_evs = [e for e in events if e.get("type") == "winner"]
        if winner_evs:
            w = winner_evs[-1]
            answer = w.get("answer") or w.get("response", "")
            if answer:
                console.print()
                console.print(
                    Panel(
                        f"[white]{answer[:2000]}[/white]",
                        title="[bold green]Winning Response[/bold green]",
                        border_style="green",
                    )
                )

    total = time.time() - start
    console.print(f"\n[dim]Total time: {total:.1f}s[/dim]\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="MonadBlitz end-to-end demo")
    parser.add_argument("--problem", type=str, help="Problem to submit")
    parser.add_argument("--quick", action="store_true", help="Use preset demo problem")
    parser.add_argument("--index", type=int, default=0, help="Demo problem index (0-3)")
    args = parser.parse_args()

    if args.problem:
        problem = args.problem
    elif args.quick or True:
        problem = DEMO_PROBLEMS[args.index % len(DEMO_PROBLEMS)]
    else:
        problem = input("Enter problem: ").strip()
        if not problem:
            sys.exit("Empty problem")

    asyncio.run(run_demo(problem))


if __name__ == "__main__":
    main()
