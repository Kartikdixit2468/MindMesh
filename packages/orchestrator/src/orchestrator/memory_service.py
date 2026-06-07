"""
Shared memory service — the key differentiator.

Every query gets a TaskMemory object that grows as agents respond and the
orchestrator makes decisions. This memory is injected into every agent's LLM
prompt so agents in round 2 know exactly why round 1 failed.

The keccak256 hash of the memory object is anchored on-chain via DecisionLedger,
making the entire reasoning chain tamper-proof and verifiable.
"""
import hashlib
import json
import logging
from datetime import datetime
from typing import Optional

from sqlalchemy import select, update

from .database import db_session
from .models import TaskMemory

logger = logging.getLogger("orchestrator.memory")


class MemoryService:
    async def initialize(
        self,
        query_id: str,
        problem: str,
        bounty: str,
        capabilities: list[str],
        requester: str,
    ) -> None:
        content = {
            "query_id": query_id,
            "problem": problem,
            "bounty": bounty,
            "capabilities": capabilities,
            "requester": requester,
            "created_at": datetime.utcnow().isoformat(),
            "rounds": [],
            "events": [
                {
                    "type": "query_created",
                    "timestamp": datetime.utcnow().isoformat(),
                    "data": {
                        "problem": problem,
                        "bounty": bounty,
                        "capabilities": capabilities,
                    },
                }
            ],
        }
        memory_hash = self._hash(content)

        async with db_session() as session:
            mem = TaskMemory(
                task_id=query_id,
                content=content,
                memory_hash=memory_hash,
            )
            session.add(mem)

        logger.info(f"[MEMORY] Initialized for query {query_id}")

    async def add_event(self, query_id: str, event_type: str, data: dict) -> None:
        async with db_session() as session:
            result = await session.execute(
                select(TaskMemory).where(TaskMemory.task_id == query_id)
            )
            mem = result.scalar_one_or_none()
            if not mem:
                logger.warning(f"[MEMORY] No memory found for query {query_id}")
                return

            content = dict(mem.content)
            content["events"].append(
                {
                    "type": event_type,
                    "timestamp": datetime.utcnow().isoformat(),
                    "data": data,
                }
            )
            new_hash = self._hash(content)
            mem.content = content
            mem.memory_hash = new_hash

        logger.debug(f"[MEMORY] Added event '{event_type}' for query {query_id}")

    async def get_memory(self, query_id: str) -> Optional[dict]:
        async with db_session() as session:
            result = await session.execute(
                select(TaskMemory).where(TaskMemory.task_id == query_id)
            )
            mem = result.scalar_one_or_none()
            return mem.content if mem else None

    async def get_hash(self, query_id: str) -> Optional[str]:
        async with db_session() as session:
            result = await session.execute(
                select(TaskMemory).where(TaskMemory.task_id == query_id)
            )
            mem = result.scalar_one_or_none()
            return mem.memory_hash if mem else None

    async def get_context_for_agent(self, query_id: str) -> str:
        """
        Format memory into a string injected into each agent's LLM system prompt.
        This is what makes round 2 agents smarter — they see why round 1 failed.
        """
        memory = await self.get_memory(query_id)
        if not memory:
            return ""

        lines = ["=== SHARED TASK MEMORY (Read before responding) ==="]
        lines.append(f"Problem: {memory.get('problem', '')}")
        lines.append(f"Bounty: {memory.get('bounty', '')} MON")
        lines.append("")

        rounds_data: dict[int, list] = {}
        for event in memory.get("events", []):
            etype = event["type"]
            data = event["data"]

            if etype == "routing":
                round_num = data.get("round", 1)
                lines.append(f"--- Round {round_num} routing ---")
                lines.append(f"Routed to agents: {data.get('agents', [])}")

            elif etype == "agent_response":
                round_num = data.get("round", 1)
                if round_num not in rounds_data:
                    rounds_data[round_num] = []
                rounds_data[round_num].append(
                    f"  Agent {data.get('agent_address', '')[:8]}... "
                    f"(score: {data.get('score', 'pending')}) — "
                    f"{data.get('reasoning', '')[:120]}"
                )

            elif etype == "score":
                round_num = data.get("round", 1)
                lines.append(
                    f"Score round {round_num}: Agent {data.get('agent_address', '')[:8]}... "
                    f"→ {data.get('score', 0):.2f} — {data.get('reasoning', '')[:100]}"
                )

            elif etype == "escalation":
                lines.append(
                    f"\n⚠ ESCALATED after round {data.get('round', 1)}: "
                    f"{data.get('reason', '')} → Starting round {data.get('next_round', 2)}"
                )
                lines.append(
                    "  [BUILD ON PREVIOUS ATTEMPTS — do NOT repeat what failed]\n"
                )

        for round_num, responses in sorted(rounds_data.items()):
            lines.append(f"\nRound {round_num} responses:")
            lines.extend(responses)

        lines.append("\n=== END OF MEMORY — Now respond better than all of the above ===")
        return "\n".join(lines)

    async def compute_hash(self, content: dict) -> str:
        """Compute keccak256 hash of the memory content (for on-chain anchoring)."""
        return self._hash(content)

    def _hash(self, content: dict) -> str:
        """keccak256 of JSON-serialized content, returned as 0x-prefixed hex."""
        serialized = json.dumps(content, sort_keys=True, default=str)
        try:
            from eth_hash.auto import keccak
            return "0x" + keccak(serialized.encode()).hex()
        except ImportError:
            # Fallback to sha256 if eth_hash not available
            return "0x" + hashlib.sha256(serialized.encode()).hexdigest()
