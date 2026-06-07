"""
Launch all 3 agent nodes in parallel.
Run: python -m agents.launcher
"""
import asyncio
import logging
import sys

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from .alpha import AlphaAgent
from .beta import BetaAgent
from .config import settings
from .gamma import GammaAgent

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s — %(message)s",
    stream=sys.stdout,
)

console = Console()


async def main_async():
    console.print(
        Panel.fit(
            "[bold cyan]MonadBlitz Agent Nodes[/bold cyan]\n"
            "[dim]Decentralized AI Agent Coordination on Monad[/dim]",
            border_style="cyan",
        )
    )

    alpha = AlphaAgent(private_key=settings.ALPHA_PRIVATE_KEY)
    beta = BetaAgent(private_key=settings.BETA_PRIVATE_KEY)
    gamma = GammaAgent(private_key=settings.GAMMA_PRIVATE_KEY)

    table = Table(title="Agent Nodes", show_header=True, header_style="bold magenta")
    table.add_column("Agent", style="cyan")
    table.add_column("Address", style="dim")
    table.add_column("Tier", style="yellow")
    table.add_column("Model", style="green")
    table.add_column("Capabilities")

    table.add_row("Alpha", alpha.address[:16] + "...", "alpha", "claude-sonnet-4-6", ", ".join(alpha.capabilities[:4]))
    table.add_row("Beta", beta.address[:16] + "...", "beta", "gpt-4o-mini", ", ".join(beta.capabilities[:4]))
    table.add_row("Gamma", gamma.address[:16] + "...", "gamma", "llama-3.3-70b", ", ".join(gamma.capabilities[:3]))

    console.print(table)
    console.print(f"\n[dim]Orchestrator: {settings.ORCHESTRATOR_BASE_URL}[/dim]")
    console.print(f"[dim]Redis: {settings.REDIS_URL}[/dim]\n")
    console.print("[green]Starting agents...[/green]\n")

    await asyncio.gather(
        alpha.start(),
        beta.start(),
        gamma.start(),
        return_exceptions=True,
    )


def main():
    asyncio.run(main_async())


if __name__ == "__main__":
    main()
