"""
Leaderboard route.

GET /api/leaderboard — top agents by reputation, filterable by capability.
"""

from typing import Optional

from fastapi import APIRouter, Depends, Query as QueryParam
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..models import Agent

router = APIRouter(tags=["leaderboard"])


@router.get("/api/leaderboard")
async def leaderboard(
    capability: Optional[str] = QueryParam(None, description="Filter by capability tag"),
    limit: int = QueryParam(50, ge=1, le=200),
    active_only: bool = QueryParam(True, description="Only include active agents"),
    db: AsyncSession = Depends(get_db),
):
    """
    Return agents ranked by reputation score.

    Each entry includes rank, win rate, stake, and capability list.
    """
    stmt = select(Agent).order_by(Agent.reputation.desc()).limit(limit * 3)
    if active_only:
        stmt = stmt.where(Agent.active == True)  # noqa: E712

    result = await db.execute(stmt)
    agents = list(result.scalars().all())

    if capability:
        agents = [a for a in agents if capability in (a.capabilities or [])]

    agents = agents[:limit]

    return [
        {
            "rank": i + 1,
            "address": a.address,
            "name": a.name,
            "tier": a.tier,
            "capabilities": a.capabilities or [],
            "reputation": a.reputation,
            "reputation_pct": round(a.reputation / 10000 * 100, 1),
            "wins": a.wins,
            "losses": a.losses,
            "timeouts": a.timeouts,
            "win_rate": a.win_rate,
            "stake": a.stake,
            "active": a.active,
        }
        for i, a in enumerate(agents)
    ]
