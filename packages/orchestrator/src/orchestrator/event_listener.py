"""
Blockchain event listener.

Listens to Monad testnet events:
  - QueryCreated     → spawn a process_query coroutine
  - WinnerSelected   → log + update DB
  - AgentRegistered  → sync agent into DB

Runs as a background task started from main.py lifespan.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Callable, Coroutine, Any

from .chain_client import ChainClient
from .config import settings
from .database import db_session
from .memory_service import MemoryService
from .models import Query, QueryStatus

logger = logging.getLogger("orchestrator.events")


class EventListener:
    """
    Polls the QueryEscrow contract for new events and dispatches them
    to the orchestrator state machine.
    """

    def __init__(
        self,
        chain_client: ChainClient,
        memory_service: MemoryService,
        on_query_created: Callable[[dict], Coroutine[Any, Any, None]],
    ) -> None:
        self.chain = chain_client
        self.memory = memory_service
        self.on_query_created = on_query_created
        self._running = False

    async def start(self) -> None:
        """Main event loop — runs forever until stop() is called."""
        if not settings.contracts_deployed:
            logger.info(
                "[EVENTS] Contracts not deployed — event listener in offline mode."
            )
            return

        self._running = True
        logger.info("[EVENTS] Starting Monad event listener...")

        while self._running:
            try:
                await self.chain.listen_for_events(self._handle_chain_event)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"[EVENTS] Listener error: {e}", exc_info=True)
                await asyncio.sleep(5)

    async def stop(self) -> None:
        self._running = False
        logger.info("[EVENTS] Event listener stopped.")

    async def _handle_chain_event(self, event: dict) -> None:
        """Dispatch incoming chain events to the appropriate handler."""
        event_name = event.get("event_name", "QueryCreated")

        if event_name == "QueryCreated":
            await self._on_query_created(event)
        elif event_name == "WinnerSelected":
            await self._on_winner_selected(event)
        elif event_name == "AgentRegistered":
            await self._on_agent_registered(event)
        else:
            logger.debug(f"[EVENTS] Unhandled event: {event_name}")

    # ── Event handlers ─────────────────────────────────────────────────────

    async def _on_query_created(self, event: dict) -> None:
        """
        A new query was posted on-chain.
        Create a DB record and kick off the state machine.
        """
        chain_query_id: int = event["chain_query_id"]
        requester: str = event.get("requester", "0x0000000000000000000000000000000000000000")
        capabilities: list[str] = event.get("capabilities", [])
        bounty: str = event.get("bounty", "0")
        deadline_ts: int = event.get("deadline", 0)
        tx_hash: str = event.get("tx_hash", "")
        block_number: int = event.get("block_number", 0)

        # Convert deadline timestamp
        try:
            deadline = datetime.utcfromtimestamp(deadline_ts) if deadline_ts else datetime.utcnow() + timedelta(minutes=5)
        except (OSError, OverflowError):
            deadline = datetime.utcnow() + timedelta(minutes=5)

        logger.info(
            f"[EVENTS] QueryCreated — chain_id={chain_query_id} "
            f"bounty={bounty} capabilities={capabilities}"
        )

        async with db_session() as session:
            # Check if already exists (idempotent)
            from sqlalchemy import select
            from .models import Query
            result = await session.execute(
                select(Query).where(Query.chain_query_id == chain_query_id)
            )
            existing = result.scalar_one_or_none()

            if existing:
                logger.info(
                    f"[EVENTS] Query chain_id={chain_query_id} already in DB, skipping"
                )
                return

            # Derive a mock problem from capabilities (real problem comes from metadata)
            problem = event.get(
                "problem",
                f"On-chain query #{chain_query_id} requiring: {', '.join(capabilities)}",
            )
            question_hash = event.get("question_hash")

            query = Query(
                chain_query_id=chain_query_id,
                problem=problem,
                bounty=bounty,
                requester=requester,
                deadline=deadline,
                capabilities=capabilities,
                status=QueryStatus.CREATED,
                round=1,
                question_hash=question_hash,
                tx_hash=tx_hash,
            )
            session.add(query)
            await session.flush()
            query_id = query.id

        # Initialize memory
        await self.memory.initialize(
            query_id=query_id,
            problem=problem,
            bounty=bounty,
            capabilities=capabilities,
            requester=requester,
        )

        # Dispatch to the state machine (runs in background)
        asyncio.create_task(self.on_query_created({"query_id": query_id}))

    async def _on_winner_selected(self, event: dict) -> None:
        chain_query_id: int = event["chain_query_id"]
        winner: str = event.get("winner", "")
        bounty: str = event.get("bounty", "0")
        memory_hash: str = event.get("memory_hash", "")
        round_num: int = event.get("round", 1)

        logger.info(
            f"[EVENTS] WinnerSelected — chain_id={chain_query_id} "
            f"winner={winner[:12]}... bounty={bounty} round={round_num}"
        )

    async def _on_agent_registered(self, event: dict) -> None:
        address: str = event.get("agent", "")
        capabilities: list[str] = event.get("capabilities", [])
        stake: str = event.get("stake", "0")

        logger.info(
            f"[EVENTS] AgentRegistered — address={address[:12]}... "
            f"capabilities={capabilities} stake={stake}"
        )

        async with db_session() as session:
            from sqlalchemy import select
            from .models import Agent
            existing = await session.get(Agent, address)
            if existing:
                existing.capabilities = capabilities
                existing.stake = stake
                existing.active = True
            else:
                agent = Agent(
                    address=address,
                    name=f"Agent-{address[:6]}",
                    capabilities=capabilities,
                    stake=stake,
                    reputation=5000,
                )
                session.add(agent)
