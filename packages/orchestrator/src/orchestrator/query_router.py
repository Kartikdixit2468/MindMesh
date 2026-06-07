"""
Query router — finds the best agents for a given query and notifies them via Redis.
"""
import json
import logging
from dataclasses import dataclass

import redis.asyncio as aioredis
from sqlalchemy import select

from .config import settings
from .database import db_session
from .models import Agent

logger = logging.getLogger("orchestrator.router")


@dataclass
class AgentInfo:
    address: str
    name: str
    reputation: int
    tier: str
    capabilities: list[str]


class QueryRouter:
    def __init__(self, redis_client: aioredis.Redis):
        self.redis = redis_client

    async def find_best_agents(
        self,
        capabilities: list[str],
        round_num: int = 1,
        exclude: list[str] | None = None,
    ) -> list[AgentInfo]:
        """
        Return best-matching agents sorted by reputation.
        For round > 1, prefer alpha-tier agents.
        """
        exclude = exclude or []

        async with db_session() as session:
            result = await session.execute(
                select(Agent).where(Agent.active == True)
            )
            all_agents = result.scalars().all()

        if not all_agents:
            logger.warning("[ROUTER] No active agents in DB")
            return []

        # Filter by capabilities
        matching = []
        for agent in all_agents:
            if agent.address in exclude:
                continue
            agent_caps = set(agent.capabilities or [])
            query_caps = set(capabilities)
            # Match if ANY capability overlaps, or if agent has "general"
            if agent_caps & query_caps or "general" in agent_caps:
                matching.append(agent)

        if not matching:
            # Fallback: return all active agents
            matching = [a for a in all_agents if a.address not in exclude]

        # Sort: alpha tier first in round > 1, then by reputation
        def sort_key(a: Agent):
            tier_bonus = 1000 if (round_num > 1 and a.tier == "alpha") else 0
            return -(a.reputation + tier_bonus)

        matching.sort(key=sort_key)
        top = matching[:3]

        return [
            AgentInfo(
                address=a.address,
                name=a.name,
                reputation=a.reputation,
                tier=a.tier,
                capabilities=a.capabilities or [],
            )
            for a in top
        ]

    async def notify_agents(
        self,
        query_id: str,
        problem: str,
        capabilities: list[str],
        bounty: str,
        round_num: int,
        orchestrator_url: str = "http://localhost:8000",
    ) -> None:
        """Publish query to Redis channels that agents subscribe to."""
        message = json.dumps(
            {
                "query_id": query_id,
                "problem": problem,
                "capabilities": capabilities,
                "bounty": bounty,
                "round": round_num,
                "memory_url": f"{orchestrator_url}/api/memory/{query_id}",
            }
        )

        channels = ["queries:all"] + [f"queries:{cap}" for cap in capabilities]
        for channel in channels:
            await self.redis.publish(channel, message)

        logger.info(
            f"[ROUTER] Published query {query_id} round {round_num} "
            f"to channels: {channels}"
        )
