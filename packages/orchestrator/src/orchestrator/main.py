"""
MindMesh Orchestrator — FastAPI application entry point.

Wires together: database, Redis, chain client, memory service, judge,
router, query state machine, proposal state machine, node discovery,
and websocket manager.
"""
import asyncio
import logging
from contextlib import asynccontextmanager

import redis.asyncio as aioredis
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .chain_client import ChainClient
from .chain_store import init_chain_store
from .config import settings
from .database import create_tables
from .judge import MetaLLMJudge
from .memory_service import MemoryService
from .proposal_state_machine import ProposalStateMachine
from .query_router import QueryRouter
from .state_machine import QueryStateMachine
from .websocket_manager import WebSocketManager
import orchestrator.node_discovery as node_discovery

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s — %(message)s",
)
logger = logging.getLogger("orchestrator")

# ── Global singletons ─────────────────────────────────────────────────────────

_redis: aioredis.Redis | None = None
_chain_client: ChainClient | None = None
_memory_service: MemoryService | None = None
_judge: MetaLLMJudge | None = None
_router: QueryRouter | None = None
_orchestrator: QueryStateMachine | None = None
_proposal_orchestrator: ProposalStateMachine | None = None
_ws_manager: WebSocketManager | None = None


def get_redis() -> aioredis.Redis:
    return _redis


def get_chain_client() -> ChainClient:
    return _chain_client


def get_memory_service() -> MemoryService:
    return _memory_service


def get_orchestrator() -> QueryStateMachine:
    return _orchestrator


def get_proposal_orchestrator() -> ProposalStateMachine:
    return _proposal_orchestrator


def get_ws_manager() -> WebSocketManager:
    return _ws_manager


# ── Lifespan ──────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    global _redis, _chain_client, _memory_service, _judge, _router
    global _orchestrator, _proposal_orchestrator, _ws_manager

    logger.info("Starting MindMesh Orchestrator...")

    # DB tables (creates all new proposal tables too)
    await create_tables()
    logger.info("✓ Database tables ready")

    # Redis
    _redis = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
    await _redis.ping()
    logger.info(f"✓ Redis connected: {settings.REDIS_URL}")

    # Core services
    _ws_manager = WebSocketManager()
    _chain_client = ChainClient()
    _memory_service = MemoryService()
    _judge = MetaLLMJudge()
    _router = QueryRouter(_redis)

    # Query state machine (existing track)
    _orchestrator = QueryStateMachine(
        memory_service=_memory_service,
        judge=_judge,
        chain_client=_chain_client,
        router=_router,
        redis_client=_redis,
        ws_manager=_ws_manager,
    )

    # Proposal state machine (new track) — ChainEventStore replaces SQLite
    try:
        from eth_account import Account
        from web3 import AsyncWeb3, AsyncHTTPProvider
        _w3 = AsyncWeb3(AsyncHTTPProvider(settings.MONAD_RPC_URL))
        _acct = Account.from_key(settings.DEPLOYER_PRIVATE_KEY)
        init_chain_store(
            w3=_w3 if settings.proposal_contracts_deployed else None,
            account=_acct if settings.proposal_contracts_deployed else None,
            contract_address=settings.PROPOSAL_ESCROW_ADDRESS,
        )
        logger.info(
            f"✓ ChainEventStore: {'online (Monad)' if settings.proposal_contracts_deployed else 'offline (in-memory)'}"
        )
    except Exception as _e:
        logger.warning(f"ChainEventStore init warning: {_e} — falling back to offline mode")
        init_chain_store()

    _proposal_orchestrator = ProposalStateMachine(
        redis_client=_redis,
        ws_manager=_ws_manager,
        chain_client=_chain_client,
    )

    logger.info(f"✓ Escalation threshold: {settings.ESCALATION_THRESHOLD}")
    logger.info(f"✓ Max rounds: {settings.MAX_ROUNDS}")
    logger.info(f"✓ Proposal bidding timeout: {settings.PROPOSAL_BIDDING_TIMEOUT}s")
    logger.info(f"✓ Proposal discussion timeout: {settings.PROPOSAL_DISCUSSION_TIMEOUT}s/round")
    logger.info(
        f"✓ Contracts {'deployed' if settings.contracts_deployed else 'NOT deployed (offline mode)'}"
    )
    logger.info(f"✓ IPFS: {'Pinata' if settings.ipfs_available else 'offline stub'}")

    # Background: relay Redis logs to WebSocket clients
    asyncio.create_task(_ws_manager.relay_redis_logs(_redis))

    # Background: chain event listener
    if settings.contracts_deployed:
        asyncio.create_task(_chain_client.listen_for_events(_handle_chain_event))

    # Background: node discovery
    await node_discovery.start(_redis)

    logger.info(
        f"MindMesh Orchestrator ready — "
        f"http://{settings.ORCHESTRATOR_HOST}:{settings.ORCHESTRATOR_PORT}"
    )

    yield

    logger.info("Shutting down MindMesh Orchestrator...")
    await node_discovery.stop()
    await _redis.aclose()


async def _handle_chain_event(event_data: dict) -> None:
    """Called when QueryCreated fires on-chain via event listener."""
    logger.info(f"[CHAIN] On-chain event: {event_data}")


# ── App ───────────────────────────────────────────────────────────────────────

app = FastAPI(
    title="MindMesh Orchestrator",
    description="Decentralized AI Agent Coordination on Monad",
    version="2.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routes ────────────────────────────────────────────────────────────────────

from .routes.queries import router as queries_router
from .routes.agents import router as agents_router
from .routes.websocket import router as ws_router
from .routes.leaderboard import router as leaderboard_router
from .routes.proposals import router as proposals_router

app.include_router(queries_router)
app.include_router(agents_router)
app.include_router(ws_router)
app.include_router(leaderboard_router)
app.include_router(proposals_router)


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "service": "mindmesh-orchestrator",
        "version": "2.0.0",
        "contracts_deployed": settings.contracts_deployed,
        "proposal_contracts_deployed": settings.proposal_contracts_deployed,
        "ipfs_available": settings.ipfs_available,
        "node_mode": settings.NODE_MODE,
        "escalation_threshold": settings.ESCALATION_THRESHOLD,
        "max_rounds": settings.MAX_ROUNDS,
        "chain_id": settings.CHAIN_ID,
        "rpc": settings.MONAD_RPC_URL,
        **node_discovery.node_info(),
    }


@app.get("/api/memory/{query_id}")
async def get_memory_direct(query_id: str):
    """Direct memory endpoint (also available via /api/queries/{id}/memory)."""
    from .database import db_session
    from .models import TaskMemory
    from sqlalchemy import select

    async with db_session() as session:
        result = await session.execute(
            select(TaskMemory).where(TaskMemory.task_id == query_id)
        )
        mem = result.scalar_one_or_none()

    if not mem:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Memory not found")

    ctx = await _memory_service.get_context_for_agent(query_id)
    return {
        "task_id": query_id,
        "content": mem.content,
        "memory_hash": mem.memory_hash,
        "context_string": ctx,
        "updated_at": mem.updated_at.isoformat(),
    }


@app.post("/api/nodes/announce")
async def announce_node(body: dict):
    """Peer nodes call this to register themselves with this node."""
    endpoint = body.get("endpoint", "")
    if endpoint:
        node_discovery.register_peer(endpoint)
    return {"status": "ok", "peers": node_discovery.get_peers()}


@app.get("/api/nodes/peers")
async def list_peers():
    """List all known peer nodes."""
    return node_discovery.node_info()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "orchestrator.main:app",
        host=settings.ORCHESTRATOR_HOST,
        port=settings.ORCHESTRATOR_PORT,
        reload=True,
        log_level="info",
    )
