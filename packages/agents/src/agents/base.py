"""
Base agent class for MonadBlitz AI agent nodes.

Each agent:
1. Registers itself with the orchestrator on startup
2. Subscribes to Redis channels for queries matching its capabilities
3. Reads full shared task memory before responding
4. Calls its LLM to generate a structured response
5. Submits response back to orchestrator via HTTP
"""
import asyncio
import hashlib
import json
import logging
import re
from abc import ABC, abstractmethod
from typing import Optional

import aiohttp
import redis.asyncio as aioredis
from eth_account import Account

from .config import settings

logger = logging.getLogger("agents")


class BaseAgent(ABC):
    # Override in subclasses
    name: str = "BaseAgent"
    capabilities: list[str] = ["general"]
    tier: str = "beta"

    def __init__(self, private_key: Optional[str] = None):
        self.private_key = private_key or "0x" + "0" * 63 + "1"
        self.account = Account.from_key(self.private_key)
        self.address = self.account.address
        self.logger = logging.getLogger(f"agents.{self.name.lower()}")
        self._running = False

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    async def start(self) -> None:
        self.logger.info(
            f"[{self.name}] Starting | address: {self.address} | "
            f"tier: {self.tier} | capabilities: {self.capabilities}"
        )
        self._running = True

        await self._register()

        redis_client = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
        pubsub = redis_client.pubsub()

        channels = ["queries:all"] + [f"queries:{cap}" for cap in self.capabilities]
        await pubsub.subscribe(*channels)
        self.logger.info(f"[{self.name}] Subscribed to: {channels}")

        async for message in pubsub.listen():
            if not self._running:
                break
            if message["type"] == "message":
                try:
                    data = json.loads(message["data"])
                    await self._handle_query(data)
                except json.JSONDecodeError:
                    pass
                except Exception as e:
                    self.logger.error(
                        f"[{self.name}] Error handling query: {e}", exc_info=True
                    )

        await redis_client.aclose()

    async def stop(self) -> None:
        self._running = False

    # ── Registration ──────────────────────────────────────────────────────────

    async def _register(self) -> None:
        async with aiohttp.ClientSession() as session:
            # Check if already registered
            try:
                async with session.get(
                    f"{settings.ORCHESTRATOR_BASE_URL}/api/agents/{self.address}",
                    timeout=aiohttp.ClientTimeout(total=5),
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        if data.get("active"):
                            self.logger.info(f"[{self.name}] Already registered ✓")
                            return
            except Exception:
                pass

            # Register
            try:
                payload = {
                    "address": self.address,
                    "name": self.name,
                    "capabilities": self.capabilities,
                    "tier": self.tier,
                    "metadata_uri": f"ipfs://monadblitz/{self.name.lower()}",
                    "private_key": self.private_key,
                }
                async with session.post(
                    f"{settings.ORCHESTRATOR_BASE_URL}/api/agents/register",
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as resp:
                    if resp.status in (200, 201):
                        self.logger.info(f"[{self.name}] Registered ✓")
                    else:
                        body = await resp.text()
                        self.logger.warning(
                            f"[{self.name}] Registration {resp.status}: {body[:200]}"
                        )
            except Exception as e:
                self.logger.warning(f"[{self.name}] Registration error: {e}")

    # ── Query handling ────────────────────────────────────────────────────────

    async def _handle_query(self, data: dict) -> None:
        query_id = data.get("query_id")
        problem = data.get("problem", "")
        round_num = data.get("round", 1)

        if not query_id or not problem:
            return

        self.logger.info(
            f"[{self.name}] Query #{query_id[:8]}... round {round_num} received"
        )

        # Fetch shared memory context
        memory_context = await self._fetch_memory(query_id)
        if memory_context:
            self.logger.info(f"[{self.name}] Memory context loaded ({len(memory_context)} chars)")

        # Generate response
        self.logger.info(f"[{self.name}] Calling LLM...")
        try:
            response = await asyncio.wait_for(
                self.generate_response(problem, memory_context, round_num),
                timeout=settings.RESPONSE_TIMEOUT,
            )
        except asyncio.TimeoutError:
            self.logger.error(f"[{self.name}] LLM timeout for query #{query_id[:8]}")
            return
        except Exception as e:
            self.logger.error(
                f"[{self.name}] LLM error for query #{query_id[:8]}: {e}", exc_info=True
            )
            return

        self.logger.info(
            f"[{self.name}] Response generated "
            f"(confidence={response.get('confidence', 0):.2f})"
        )

        # Submit
        await self._submit_response(query_id, response)

    async def _fetch_memory(self, query_id: str) -> str:
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{settings.ORCHESTRATOR_BASE_URL}/api/memory/{query_id}",
                    timeout=aiohttp.ClientTimeout(total=5),
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        return data.get("context_string", "")
        except Exception as e:
            self.logger.debug(f"[{self.name}] Memory fetch failed: {e}")
        return ""

    async def _submit_response(self, query_id: str, response: dict) -> None:
        response_text = response.get("answer", "") or response.get("response", "")
        reasoning = response.get("reasoning", "")
        confidence = float(response.get("confidence", 0.5))

        response_hash = "0x" + hashlib.sha256(response_text.encode()).hexdigest()

        payload = {
            "agent_address": self.address,
            "response_text": response_text,
            "reasoning": reasoning,
            "confidence": confidence,
            "response_hash": response_hash,
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{settings.ORCHESTRATOR_BASE_URL}/api/queries/{query_id}/respond",
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as resp:
                    if resp.status in (200, 201):
                        self.logger.info(
                            f"[{self.name}] Response submitted for #{query_id[:8]}... ✓"
                        )
                    else:
                        body = await resp.text()
                        self.logger.error(
                            f"[{self.name}] Submit failed {resp.status}: {body[:200]}"
                        )
        except Exception as e:
            self.logger.error(f"[{self.name}] Submit error: {e}")

    # ── Helpers ───────────────────────────────────────────────────────────────

    @abstractmethod
    async def generate_response(
        self, problem: str, memory_context: str, round_num: int
    ) -> dict:
        """
        Generate a response. Must return:
        {
            "reasoning": str,  # step-by-step thinking
            "answer": str,     # the actual answer
            "confidence": float  # 0.0-1.0
        }
        """

    def _parse_json_response(self, raw: str) -> dict:
        """Extract JSON dict from LLM output, even if wrapped in markdown."""
        raw = re.sub(r"```(?:json)?", "", raw).strip().rstrip("```").strip()
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            # Try to extract JSON object
            match = re.search(r"\{[\s\S]*\}", raw)
            if match:
                try:
                    return json.loads(match.group())
                except json.JSONDecodeError:
                    pass
        # Fallback: treat whole text as answer
        return {"reasoning": "Direct response", "answer": raw, "confidence": 0.5}

    def _build_prompt(self, problem: str, memory_context: str, round_num: int) -> str:
        round_note = ""
        if round_num > 1:
            round_note = (
                f"\n\n⚠ THIS IS ROUND {round_num}. Previous rounds scored too low. "
                "You MUST significantly improve on what came before. "
                "Read the memory context carefully and address the gaps."
            )

        ctx_section = f"\n\n{memory_context}" if memory_context else ""

        return (
            f"Problem:{round_note}\n{problem}"
            f"{ctx_section}\n\n"
            "Respond ONLY in this JSON format:\n"
            '{"reasoning": "your step-by-step thinking", '
            '"answer": "your complete answer", '
            '"confidence": 0.90}'
        )
