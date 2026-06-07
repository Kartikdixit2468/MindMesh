"""
Async SQLAlchemy engine and session factory.

Usage:
  - call create_tables() on startup to create all tables
  - use get_db() as a FastAPI dependency to obtain an AsyncSession
  - use DatabaseService for higher-level query/agent operations
"""
import logging
from contextlib import asynccontextmanager
from datetime import datetime
from typing import AsyncGenerator, Optional

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from .config import settings
from .models import (
    Agent,
    Base,
    OrchestratorEvent,
    Query,
    QueryStatus,
    Response,
    TaskMemory,
)

logger = logging.getLogger("orchestrator.database")

# ── Engine & Session factory ───────────────────────────────────────────────────

engine: AsyncEngine = create_async_engine(
    settings.DATABASE_URL,
    echo=False,
    pool_pre_ping=True,
    pool_size=10,
    max_overflow=20,
)

AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


# ── FastAPI dependency ─────────────────────────────────────────────────────────

async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency — yields an AsyncSession and commits/rolls back."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


# ── Schema bootstrap ───────────────────────────────────────────────────────────

async def create_tables() -> None:
    """Create all tables if they do not exist. Called during app startup."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Database tables ensured.")


async def drop_tables() -> None:
    """Drop all tables. Useful for testing."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    logger.warning("All database tables dropped.")


@asynccontextmanager
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    """Context manager that yields a session and auto-commits."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


# ── Higher-level DB service ────────────────────────────────────────────────────

class DatabaseService:
    """
    Thin service layer over AsyncSession.
    Wraps common query patterns used by the orchestrator state machine and routes.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # ── Query operations ───────────────────────────────────────────────────

    async def create_query(
        self,
        *,
        problem: str,
        bounty: str,
        requester: str,
        deadline: datetime,
        capabilities: list[str],
        chain_query_id: Optional[int] = None,
        question_hash: Optional[str] = None,
    ) -> Query:
        query = Query(
            problem=problem,
            bounty=bounty,
            requester=requester,
            deadline=deadline,
            capabilities=capabilities,
            chain_query_id=chain_query_id,
            question_hash=question_hash,
            status=QueryStatus.CREATED,
            round=1,
        )
        self._session.add(query)
        await self._session.flush()
        await self._session.refresh(query)
        return query

    async def get_query(self, query_id: str) -> Optional[Query]:
        return await self._session.get(Query, query_id)

    async def get_query_by_chain_id(self, chain_query_id: int) -> Optional[Query]:
        result = await self._session.execute(
            select(Query).where(Query.chain_query_id == chain_query_id)
        )
        return result.scalars().first()

    async def list_queries(
        self,
        status: Optional[str] = None,
        capability: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Query]:
        stmt = select(Query).order_by(Query.created_at.desc())
        if status:
            try:
                stmt = stmt.where(Query.status == QueryStatus(status))
            except ValueError:
                pass
        result = await self._session.execute(stmt.limit(limit).offset(offset))
        queries = list(result.scalars().all())
        if capability:
            queries = [q for q in queries if capability in (q.capabilities or [])]
        return queries

    async def update_query_status(self, query_id: str, new_status: str) -> None:
        await self._session.execute(
            update(Query)
            .where(Query.id == query_id)
            .values(status=QueryStatus(new_status), updated_at=datetime.utcnow())
        )

    async def increment_round(self, query_id: str) -> None:
        query = await self.get_query(query_id)
        if query:
            query.round = query.round + 1
            query.updated_at = datetime.utcnow()

    async def settle_query(
        self,
        query_id: str,
        winner_address: str,
        tx_hash: Optional[str],
        memory_hash: Optional[str],
    ) -> None:
        await self._session.execute(
            update(Query)
            .where(Query.id == query_id)
            .values(
                status=QueryStatus.SETTLED,
                winner_address=winner_address,
                tx_hash=tx_hash,
                memory_hash=memory_hash,
                updated_at=datetime.utcnow(),
            )
        )

    # ── Response operations ────────────────────────────────────────────────

    async def create_response(
        self,
        *,
        query_id: str,
        agent_address: str,
        response_text: str,
        reasoning: str = "",
        confidence: float = 0.5,
        response_hash: str,
        round_num: int = 1,
    ) -> Response:
        response = Response(
            query_id=query_id,
            agent_address=agent_address,
            response_text=response_text,
            reasoning=reasoning,
            confidence=confidence,
            response_hash=response_hash,
            round=round_num,
        )
        self._session.add(response)
        await self._session.flush()
        await self._session.refresh(response)
        return response

    async def get_responses_for_query(
        self, query_id: str, round_num: Optional[int] = None
    ) -> list[Response]:
        stmt = select(Response).where(Response.query_id == query_id)
        if round_num is not None:
            stmt = stmt.where(Response.round == round_num)
        stmt = stmt.order_by(Response.submitted_at.asc())
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def update_response_score(
        self, response_id: str, score: float, score_reasoning: str
    ) -> None:
        await self._session.execute(
            update(Response)
            .where(Response.id == response_id)
            .values(score=score, score_reasoning=score_reasoning)
        )

    # ── Agent operations ───────────────────────────────────────────────────

    async def upsert_agent(
        self,
        *,
        address: str,
        name: str,
        capabilities: list[str],
        stake: str = "0",
        reputation: int = 5000,
        metadata_uri: str = "",
        tier: str = "beta",
    ) -> Agent:
        agent = await self._session.get(Agent, address)
        if agent is None:
            agent = Agent(
                address=address,
                name=name,
                capabilities=capabilities,
                stake=stake,
                reputation=reputation,
                metadata_uri=metadata_uri,
                tier=tier,
            )
            self._session.add(agent)
        else:
            agent.name = name
            agent.capabilities = capabilities
            agent.stake = stake
            agent.reputation = reputation
            agent.metadata_uri = metadata_uri
            agent.tier = tier
        await self._session.flush()
        await self._session.refresh(agent)
        return agent

    async def get_agent(self, address: str) -> Optional[Agent]:
        return await self._session.get(Agent, address)

    async def list_agents(
        self,
        capability: Optional[str] = None,
        active_only: bool = True,
        limit: int = 100,
    ) -> list[Agent]:
        stmt = select(Agent)
        if active_only:
            stmt = stmt.where(Agent.active == True)  # noqa: E712
        stmt = stmt.order_by(Agent.reputation.desc()).limit(limit)
        result = await self._session.execute(stmt)
        agents = list(result.scalars().all())
        if capability:
            agents = [a for a in agents if capability in (a.capabilities or [])]
        return agents

    async def update_agent_stats(
        self, address: str, won: bool, reputation_delta: int = 0
    ) -> None:
        agent = await self._session.get(Agent, address)
        if agent:
            if won:
                agent.wins = agent.wins + 1
            else:
                agent.losses = agent.losses + 1
            agent.reputation = max(0, agent.reputation + reputation_delta)

    # ── Memory operations ──────────────────────────────────────────────────

    async def get_or_create_memory(self, task_id: str) -> TaskMemory:
        memory = await self._session.get(TaskMemory, task_id)
        if memory is None:
            memory = TaskMemory(task_id=task_id, content={}, memory_hash=None)
            self._session.add(memory)
            await self._session.flush()
        return memory

    async def update_memory(
        self, task_id: str, content: dict, memory_hash: Optional[str] = None
    ) -> None:
        memory = await self.get_or_create_memory(task_id)
        memory.content = content
        memory.memory_hash = memory_hash
        memory.updated_at = datetime.utcnow()

    # ── Event log ──────────────────────────────────────────────────────────

    async def log_event(
        self,
        *,
        event_type: str,
        query_id: Optional[str] = None,
        payload: Optional[dict] = None,
        tx_hash: Optional[str] = None,
        block_number: Optional[int] = None,
    ) -> OrchestratorEvent:
        event = OrchestratorEvent(
            event_type=event_type,
            query_id=query_id,
            payload=payload or {},
            tx_hash=tx_hash,
            block_number=block_number,
        )
        self._session.add(event)
        await self._session.flush()
        return event


@asynccontextmanager
async def get_db_service() -> AsyncGenerator[DatabaseService, None]:
    """Context manager yielding a DatabaseService with auto-commit."""
    async with AsyncSessionLocal() as session:
        try:
            service = DatabaseService(session)
            yield service
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
