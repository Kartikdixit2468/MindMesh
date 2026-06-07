"""
MonadBlitz Orchestrator — FastAPI application entry point.

Wires together: database, Redis, chain client, memory service, judge,
router, state machine, websocket manager, and event listener.
"""
import asyncio
import logging
from contextlib import asynccontextmanager

import redis.asyncio as aioredis
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .chain_client import ChainClient
from .config import settings
from .database import create_tables
from .judge import MetaLLMJudge
from .memory_service import MemoryService
from .query_router import QueryRouter
from .state_machine import QueryStateMachine
from .websocket_manager import WebSocketManager

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
_ws_manager: WebSocketManager | None = None


def get_redis() -> aioredis.Redis:
    return _redis


def get_chain_client() -> ChainClient:
    return _chain_client


def get_memory_service() -> MemoryService:
    return _memory_service


def get_orchestrator() -> QueryStateMachine:
    return _orchestrator


def get_ws_manager() -> WebSocketManager:
    return _ws_manager


# ── Lifespan ──────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    global _redis, _chain_client, _memory_service, _judge, _router, _orchestrator, _ws_manager

    logger.info("Starting MonadBlitz Orchestrator...")

    # DB tables
    await create_tables()
    logger.info("✓ Database tables ready")

    # Redis
    _redis = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
    await _redis.ping()
    logger.info(f"✓ Redis connected: {settings.REDIS_URL}")

    # Services
    _ws_manager = WebSocketManager()
    _chain_client = ChainClient()
    _memory_service = MemoryService()
    _judge = MetaLLMJudge()
    _router = QueryRouter(_redis)
    _orchestrator = QueryStateMachine(
        memory_service=_memory_service,
        judge=_judge,
        chain_client=_chain_client,
        router=_router,
        redis_client=_redis,
        ws_manager=_ws_manager,
    )

    logger.info(f"✓ Escalation threshold: {settings.ESCALATION_THRESHOLD}")
    logger.info(f"✓ Max rounds: {settings.MAX_ROUNDS}")
    logger.info(
        f"✓ Contracts {'deployed' if settings.contracts_deployed else 'NOT deployed (offline mode)'}"
    )

    # Background: relay Redis logs to WebSocket clients
    asyncio.create_task(_ws_manager.relay_redis_logs(_redis))

    # Background: chain event listener
    if settings.contracts_deployed:
        asyncio.create_task(_chain_client.listen_for_events(_handle_chain_event))

    logger.info(
        "✓ Orchestrator ready — listening on "
        f"http://{settings.ORCHESTRATOR_HOST}:{settings.ORCHESTRATOR_PORT}"
    )

    yield

    logger.info("Shutting down orchestrator...")
    await _redis.close()


async def _handle_chain_event(event_data: dict) -> None:
    """Called by chain event listener when QueryCreated fires on-chain."""
    logger.info(f"[CHAIN] QueryCreated on-chain: {event_data}")
    # Could trigger orchestration for on-chain-originated queries


# ── App ───────────────────────────────────────────────────────────────────────

app = FastAPI(
    title="MonadBlitz Orchestrator",
    description="Decentralized AI Agent Coordination on Monad",
    version="1.0.0",
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

app.include_router(queries_router)
app.include_router(agents_router)
app.include_router(ws_router)


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "service": "monadblitz-orchestrator",
        "contracts_deployed": settings.contracts_deployed,
        "escalation_threshold": settings.ESCALATION_THRESHOLD,
        "max_rounds": settings.MAX_ROUNDS,
        "chain_id": settings.CHAIN_ID,
        "rpc": settings.MONAD_RPC_URL,
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


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "orchestrator.main:app",
        host=settings.ORCHESTRATOR_HOST,
        port=settings.ORCHESTRATOR_PORT,
        reload=True,
        log_level="info",
    )
