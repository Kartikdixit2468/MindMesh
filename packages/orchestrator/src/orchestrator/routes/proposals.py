"""Proposal routes — create/list/get proposals, submit bids and discussion messages.

All proposal state lives in ChainEventStore (on-chain events + in-memory cache).
No SQLite, no SQLAlchemy dependencies in this module.
"""
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel, Field

from ..chain_store import get_store
from ..config import settings
from ..vector_store import get_vector_store

router = APIRouter(prefix="/api/proposals", tags=["proposals"])


# ── Pydantic schemas ──────────────────────────────────────────────────────────

class CreateProposalRequest(BaseModel):
    title: str = Field(..., min_length=5, max_length=200)
    description: str = Field(..., min_length=20, max_length=8000)
    max_roles: int = Field(default=4, ge=2, le=6)
    bounty: str = Field(default="0", description="Bounty in wei as string")
    requester: str = Field(default="0x0000000000000000000000000000000000000000")
    lock_time: int = Field(default=60, ge=10, le=300, description="Seconds before bidding starts")
    proposal_time: int = Field(default=30, ge=10, le=120, description="Seconds for bidding phase")
    evaluation_time: int = Field(default=300, ge=60, le=1800, description="Seconds for full evaluation")
    chain_proposal_id: Optional[int] = None


class SubmitBidRequest(BaseModel):
    agent_address: str
    agent_name: str = ""
    role_name: str
    fit_score: float = Field(..., ge=0.0, le=1.0)
    reasoning: str = Field(default="")


class SubmitDiscussionRequest(BaseModel):
    agent_address: str
    agent_name: str = ""
    role_name: str
    round_num: int = Field(..., ge=1, le=10)
    round_type: str = Field(default="initial")
    content: str = Field(..., min_length=10, max_length=3000)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _serialize_proposal(p: dict) -> dict:
    return {
        "id": p["id"],
        "title": p["title"],
        "description": p["description"],
        "domain": p.get("domain", ""),
        "status": p["status"],
        "bounty": p.get("bounty", "0"),
        "requester": p.get("requester", ""),
        "max_roles": p.get("max_roles", 4),
        "lock_time": p.get("lock_time", 60),
        "proposal_time": p.get("proposal_time", 30),
        "evaluation_time": p.get("evaluation_time", 300),
        "chain_proposal_id": p.get("chain_proposal_id"),
        "roles_decided": p.get("roles_decided") or [],
        "final_report": p.get("final_report"),
        "report_ipfs_hash": p.get("report_ipfs_hash"),
        "report_hash": p.get("report_hash"),
        "tx_hash": p.get("tx_hash"),
        "created_at": p.get("created_at", ""),
        "updated_at": p.get("updated_at", ""),
        "roles": [_serialize_role(r) for r in (p.get("roles") or [])],
        "bids": [_serialize_bid(b) for b in (p.get("bids") or [])],
        "messages": [_serialize_message(m) for m in (p.get("messages") or [])],
    }


def _serialize_role(r: dict) -> dict:
    return {
        "id": r.get("id", ""),
        "role_name": r.get("role_name", ""),
        "role_description": r.get("role_description", ""),
        "agent_address": r.get("agent_address"),
        "agent_name": r.get("agent_name"),
        "assigned_at": r.get("assigned_at"),
    }


def _serialize_bid(b: dict) -> dict:
    return {
        "id": b.get("id", ""),
        "agent_address": b.get("agent_address", ""),
        "agent_name": b.get("agent_name", ""),
        "role_name": b.get("role_name", ""),
        "fit_score": b.get("fit_score", 0.0),
        "reasoning": b.get("reasoning", ""),
        "created_at": b.get("created_at", ""),
    }


def _serialize_message(m: dict) -> dict:
    return {
        "id": m.get("id", ""),
        "agent_address": m.get("agent_address", ""),
        "agent_name": m.get("agent_name", ""),
        "role_name": m.get("role_name", ""),
        "round_num": m.get("round_num", 1),
        "round_type": m.get("round_type", "initial"),
        "content": m.get("content", ""),
        "created_at": m.get("created_at", ""),
    }


# ── Routes ────────────────────────────────────────────────────────────────────

@router.post("/", status_code=201)
async def create_proposal(
    body: CreateProposalRequest,
    background_tasks: BackgroundTasks,
):
    """Create a new proposal and start the structured discussion pipeline."""
    from ..main import get_proposal_orchestrator

    store = get_store()
    proposal_id = await store.create_proposal(
        title=body.title,
        description=body.description,
        max_roles=min(body.max_roles, settings.PROPOSAL_MAX_ROLES),
        bounty_wei=int(body.bounty),
        lock_time=body.lock_time,
        proposal_time=body.proposal_time,
        evaluation_time=body.evaluation_time,
        requester=body.requester,
        chain_proposal_id=body.chain_proposal_id,
    )

    orch = get_proposal_orchestrator()
    background_tasks.add_task(orch.process_proposal, proposal_id)

    return {
        "id": proposal_id,
        "status": "CREATED",
        "message": "Proposal created — role discovery starting",
        "title": body.title,
        "max_roles": min(body.max_roles, settings.PROPOSAL_MAX_ROLES),
    }


@router.get("/")
async def list_proposals(
    status: Optional[str] = None,
    limit: int = 20,
    offset: int = 0,
):
    store = get_store()
    proposals = await store.list_proposals(limit=limit, offset=offset, status=status)
    return [_serialize_proposal(p) for p in proposals]


@router.get("/{proposal_id}")
async def get_proposal(proposal_id: str):
    store = get_store()
    p = await store.get_proposal(proposal_id)
    if not p:
        raise HTTPException(status_code=404, detail="Proposal not found")
    return _serialize_proposal(p)


@router.post("/{proposal_id}/bid", status_code=201)
async def submit_bid(
    proposal_id: str,
    body: SubmitBidRequest,
):
    """Agent submits a bid to fill a role in a proposal."""
    store = get_store()
    p = await store.get_proposal(proposal_id)
    if not p:
        raise HTTPException(status_code=404, detail="Proposal not found")

    allowed_statuses = {"BIDDING", "ROLE_DISCOVERY", "CREATED"}
    if p["status"] not in allowed_statuses:
        raise HTTPException(
            status_code=409,
            detail=f"Proposal is in status {p['status']} — not accepting bids",
        )

    bid_id = await store.post_bid(
        proposal_id=proposal_id,
        role_name=body.role_name,
        agent_address=body.agent_address,
        agent_name=body.agent_name or body.agent_address[:10] + "...",
        fit_score=body.fit_score,
        reasoning=body.reasoning,
    )

    return {"id": bid_id, "status": "submitted", "role": body.role_name, "fit_score": body.fit_score}


@router.post("/{proposal_id}/discuss", status_code=201)
async def submit_discussion_message(
    proposal_id: str,
    body: SubmitDiscussionRequest,
):
    """Agent submits a discussion message for a specific round."""
    store = get_store()
    vstore = get_vector_store()

    p = await store.get_proposal(proposal_id)
    if not p:
        raise HTTPException(status_code=404, detail="Proposal not found")

    allowed_statuses = {"DISCUSSING", "TEAM_FORMED"}
    if p["status"] not in allowed_statuses:
        raise HTTPException(
            status_code=409,
            detail=f"Proposal is in status {p['status']} — not in discussion phase",
        )

    msg_id = await store.post_message(
        proposal_id=proposal_id,
        round_num=body.round_num,
        round_type=body.round_type,
        agent_address=body.agent_address,
        agent_name=body.agent_name or body.agent_address[:10] + "...",
        role_name=body.role_name,
        content=body.content,
    )

    # Index in vector store for RAG
    vstore.add_message(
        proposal_id=proposal_id,
        msg_id=msg_id,
        content=body.content,
        agent_name=body.agent_name or "",
        role_name=body.role_name,
        round_num=body.round_num,
        round_type=body.round_type,
    )

    return {"id": msg_id, "status": "submitted", "round": body.round_num, "role": body.role_name}


@router.get("/{proposal_id}/report")
async def get_report(proposal_id: str):
    """Get the final synthesized report for a settled proposal."""
    store = get_store()
    p = await store.get_proposal(proposal_id)
    if not p:
        raise HTTPException(status_code=404, detail="Proposal not found")

    if not p.get("final_report"):
        raise HTTPException(status_code=404, detail="Report not yet generated")

    from ..ipfs_client import ipfs_url
    return {
        "proposal_id": proposal_id,
        "title": p["title"],
        "report": p["final_report"],
        "report_hash": p.get("report_hash"),
        "report_ipfs_hash": p.get("report_ipfs_hash"),
        "ipfs_url": ipfs_url(p["report_ipfs_hash"]) if p.get("report_ipfs_hash") else None,
        "tx_hash": p.get("tx_hash"),
        "status": p["status"],
    }
