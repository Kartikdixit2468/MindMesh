"""Agent routes — register, list, and inspect agents."""
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import settings
from ..database import get_db
from ..models import Agent, Response

router = APIRouter(prefix="/api/agents", tags=["agents"])


class RegisterAgentRequest(BaseModel):
    address: str
    name: str
    capabilities: list[str] = Field(..., min_length=1)
    tier: str = "beta"
    metadata_uri: str = ""
    private_key: Optional[str] = None
    stake_wei: int = 0


@router.post("/register", status_code=201)
async def register_agent(
    body: RegisterAgentRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    """Register an agent in the DB. Optionally trigger on-chain registration."""
    existing = await db.get(Agent, body.address)
    if existing:
        existing.active = True
        existing.capabilities = body.capabilities
        existing.name = body.name
        existing.tier = body.tier
        return {"status": "updated", "address": body.address}

    agent = Agent(
        address=body.address,
        name=body.name,
        capabilities=body.capabilities,
        tier=body.tier,
        metadata_uri=body.metadata_uri,
        active=True,
    )
    db.add(agent)

    # Optional on-chain registration
    if body.private_key and settings.contracts_deployed and body.stake_wei > 0:
        from ..main import get_chain_client

        async def _register_on_chain():
            try:
                cc = get_chain_client()
                await cc.register_agent(
                    body.private_key,
                    body.capabilities,
                    body.metadata_uri or f"ipfs://monadblitz/{body.name.lower()}",
                    body.stake_wei,
                )
            except Exception as e:
                import logging
                logging.getLogger("orchestrator").warning(
                    f"On-chain registration failed for {body.address}: {e}"
                )

        background_tasks.add_task(_register_on_chain)

    return {
        "status": "registered",
        "address": body.address,
        "name": body.name,
        "capabilities": body.capabilities,
        "tier": body.tier,
    }


@router.get("/")
async def list_agents(
    active_only: bool = True,
    capability: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
):
    stmt = select(Agent).order_by(Agent.reputation.desc())
    if active_only:
        stmt = stmt.where(Agent.active == True)
    result = await db.execute(stmt)
    agents = result.scalars().all()

    if capability:
        agents = [a for a in agents if capability in (a.capabilities or [])]

    return [
        {
            "address": a.address,
            "name": a.name,
            "capabilities": a.capabilities,
            "tier": a.tier,
            "reputation": a.reputation,
            "stake": a.stake,
            "wins": a.wins,
            "losses": a.losses,
            "win_rate": a.win_rate,
            "active": a.active,
        }
        for a in agents
    ]


@router.get("/leaderboard")
async def leaderboard(
    capability: Optional[str] = None,
    limit: int = 20,
    db: AsyncSession = Depends(get_db),
):
    stmt = select(Agent).where(Agent.active == True).order_by(Agent.reputation.desc()).limit(limit)
    result = await db.execute(stmt)
    agents = result.scalars().all()

    if capability:
        agents = [a for a in agents if capability in (a.capabilities or [])]

    return [
        {
            "rank": i + 1,
            "address": a.address,
            "name": a.name,
            "tier": a.tier,
            "capabilities": a.capabilities,
            "reputation": a.reputation,
            "reputation_pct": round(a.reputation / 10000 * 100, 1),
            "wins": a.wins,
            "losses": a.losses,
            "win_rate": a.win_rate,
            "stake": a.stake,
        }
        for i, a in enumerate(agents)
    ]


@router.get("/{address}")
async def get_agent(address: str, db: AsyncSession = Depends(get_db)):
    agent = await db.get(Agent, address)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    resp_result = await db.execute(
        select(Response)
        .where(Response.agent_address == address)
        .order_by(Response.submitted_at.desc())
        .limit(20)
    )
    responses = resp_result.scalars().all()

    return {
        "address": agent.address,
        "name": agent.name,
        "capabilities": agent.capabilities,
        "tier": agent.tier,
        "reputation": agent.reputation,
        "reputation_pct": round(agent.reputation / 10000 * 100, 1),
        "stake": agent.stake,
        "wins": agent.wins,
        "losses": agent.losses,
        "timeouts": agent.timeouts,
        "win_rate": agent.win_rate,
        "active": agent.active,
        "registered_at": agent.registered_at.isoformat(),
        "recent_responses": [
            {
                "query_id": r.query_id,
                "score": r.score,
                "round": r.round,
                "submitted_at": r.submitted_at.isoformat(),
            }
            for r in responses
        ],
    }
