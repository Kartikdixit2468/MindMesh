"""
All-in-one dev runner: orchestrator + 3 agents in one process.
Uses shared fakeredis so pub/sub works between orchestrator and agents.
No PostgreSQL, Redis, or Docker needed.

Usage:
    python scripts/dev_all.py
"""
import asyncio
import os
import sys

# ---- 0. Point to dev.db and fake redis ----
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///./dev_all.db"
os.environ["REDIS_URL"] = "redis://localhost:6379"
os.environ.setdefault("ORCHESTRATOR_HOST", "0.0.0.0")
os.environ.setdefault("ORCHESTRATOR_PORT", "8000")
os.environ.setdefault("ORCHESTRATOR_BASE_URL", "http://localhost:8000")
os.environ.setdefault("ESCALATION_THRESHOLD", "0.75")
os.environ.setdefault("MAX_ROUNDS", "3")
os.environ.setdefault("ROUND_TIMEOUT_SECONDS", "60")
os.environ.setdefault("AGENT_REGISTRY_ADDRESS", "0x0000000000000000000000000000000000000000")
os.environ.setdefault("QUERY_ESCROW_ADDRESS", "0x0000000000000000000000000000000000000000")
# Well-known Hardhat test keys (public domain)
os.environ.setdefault("DEPLOYER_PRIVATE_KEY",  "0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80")
os.environ.setdefault("ALPHA_PRIVATE_KEY",  "0x59c6995e998f97a5a0044966f0945389dc9e86dae88c7a8412f4603b6b78690d")
os.environ.setdefault("BETA_PRIVATE_KEY",   "0x5de4111afa1a4b94908f83103eb1f1706367c2e68ca870fc3fb9a804cdab365a")
os.environ.setdefault("GAMMA_PRIVATE_KEY",  "0x7c852118294e51e653712a81e05800f419141751be58f605c371e15141b007a6")

# ---- 1. Shared fakeredis server (ONE server for whole process) ----
import fakeredis
import fakeredis.aioredis
import redis.asyncio as _aioredis

FAKE_SERVER = fakeredis.FakeServer()

def _fake_from_url(url, *args, **kwargs):
    kwargs.pop("encoding", None)
    return fakeredis.aioredis.FakeRedis(
        server=FAKE_SERVER,
        decode_responses=kwargs.get("decode_responses", False),
    )

_aioredis.Redis.from_url = staticmethod(_fake_from_url)
import redis.asyncio
redis.asyncio.from_url = _fake_from_url

print("[dev] Shared fakeredis server initialized")
print("[dev] DATABASE_URL = sqlite+aiosqlite:///./dev_all.db")

# ---- 2. Paths ----
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "packages", "orchestrator", "src"))
sys.path.insert(0, os.path.join(ROOT, "packages", "agents", "src"))

# ---- 3. Fix WebSocket relay bytes vs str (fakeredis returns str) ----
import orchestrator.websocket_manager as _wsm
_orig_relay = _wsm.WebSocketManager.relay_redis_logs
async def _fixed_relay(self, redis_client):
    pubsub = redis_client.pubsub()
    await pubsub.subscribe("orchestrator:logs")
    async for message in pubsub.listen():
        if message["type"] == "message":
            data = message["data"]
            if isinstance(data, bytes):
                data = data.decode()
            await self.broadcast_log(data)
_wsm.WebSocketManager.relay_redis_logs = _fixed_relay

# ---- 4. Import orchestrator app ----
from orchestrator.main import app as fastapi_app

# ---- 5. Import agents ----
from agents.alpha import AlphaAgent
from agents.beta import BetaAgent
from agents.gamma import GammaAgent

# ---- 6. Run everything ----
async def run_agents():
    """Wait for orchestrator, then start agents."""
    import aiohttp
    print("[agents] Waiting for orchestrator...")
    for _ in range(20):
        try:
            async with aiohttp.ClientSession() as s:
                async with s.get("http://localhost:8000/health", timeout=aiohttp.ClientTimeout(total=2)) as r:
                    if r.status == 200:
                        print("[agents] Orchestrator ready!")
                        break
        except Exception:
            pass
        await asyncio.sleep(0.5)

    alpha = AlphaAgent(private_key=os.environ["ALPHA_PRIVATE_KEY"])
    beta  = BetaAgent(private_key=os.environ["BETA_PRIVATE_KEY"])
    gamma = GammaAgent(private_key=os.environ["GAMMA_PRIVATE_KEY"])
    print(f"[agents] Alpha: {alpha.address}")
    print(f"[agents] Beta:  {beta.address}")
    print(f"[agents] Gamma: {gamma.address}")
    print("[agents] All running, listening for queries...")

    await asyncio.gather(
        alpha.start(),
        beta.start(),
        gamma.start(),
        return_exceptions=True,
    )

async def main():
    import uvicorn

    print()
    print("=" * 62)
    print("  MonadBlitz All-In-One Dev Server")
    print("  Orchestrator + Alpha + Beta + Gamma agents")
    print("=" * 62)
    print("  Web UI   -> http://localhost:3000  (run: cd packages/web && npx next dev)")
    print("  API Docs -> http://localhost:8000/docs")
    print("  Health   -> http://localhost:8000/health")
    print("=" * 62)
    print()

    config = uvicorn.Config(
        fastapi_app,
        host="0.0.0.0",
        port=8000,
        log_level="info",
        loop="asyncio",
    )
    server = uvicorn.Server(config)

    # Run orchestrator server + agents concurrently
    await asyncio.gather(
        server.serve(),
        run_agents(),
    )

if __name__ == "__main__":
    asyncio.run(main())
