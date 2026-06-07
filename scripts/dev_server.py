"""
Development server -- runs orchestrator with SQLite + fakeredis.
No PostgreSQL or Redis installation needed.

Usage:
    python scripts/dev_server.py
"""
import os
import sys

# -- 1. Override env before any imports --
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///./dev.db"
os.environ["REDIS_URL"] = "redis://localhost:6379"
os.environ.setdefault("ORCHESTRATOR_HOST", "0.0.0.0")
os.environ.setdefault("ORCHESTRATOR_PORT", "8000")
os.environ.setdefault("ESCALATION_THRESHOLD", "0.75")
os.environ.setdefault("MAX_ROUNDS", "3")
os.environ.setdefault("ROUND_TIMEOUT_SECONDS", "60")
os.environ.setdefault("AGENT_REGISTRY_ADDRESS", "0x0000000000000000000000000000000000000000")
os.environ.setdefault("QUERY_ESCROW_ADDRESS", "0x0000000000000000000000000000000000000000")
os.environ.setdefault("DEPLOYER_PRIVATE_KEY", "0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80")
os.environ.setdefault("ALPHA_PRIVATE_KEY", "0x59c6995e998f97a5a0044966f0945389dc9e86dae88c7a8412f4603b6b78690d")
os.environ.setdefault("BETA_PRIVATE_KEY", "0x5de4111afa1a4b94908f83103eb1f1706367c2e68ca870fc3fb9a804cdab365a")
os.environ.setdefault("GAMMA_PRIVATE_KEY", "0x7c852118294e51e653712a81e05800f419141751be58f605c371e15141b007a6")

# -- 2. Patch redis.asyncio to use fakeredis --
import fakeredis
import fakeredis.aioredis
import redis.asyncio as _aioredis

_fake_server = fakeredis.FakeServer()

def _patched_from_url(url, *args, **kwargs):
    kwargs.pop("encoding", None)
    return fakeredis.aioredis.FakeRedis(server=_fake_server, decode_responses=kwargs.get("decode_responses", False))

_aioredis.Redis.from_url = staticmethod(_patched_from_url)
import redis.asyncio
redis.asyncio.from_url = _patched_from_url

print("[dev] Patched redis.asyncio -> fakeredis OK")
print("[dev] DATABASE_URL = sqlite+aiosqlite:///./dev.db OK")

# -- 3. Add orchestrator src to path --
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "packages", "orchestrator", "src"))

import uvicorn

def main():
    print()
    print("=" * 60)
    print("  MonadBlitz Dev Server  (SQLite + fakeredis mode)")
    print("=" * 60)
    print("  API Docs  ->  http://localhost:8000/docs")
    print("  Health    ->  http://localhost:8000/health")
    print("  WS        ->  ws://localhost:8000/ws")
    print("=" * 60)
    print("  Press Ctrl+C to stop")
    print()

    uvicorn.run(
        "orchestrator.main:app",
        host="0.0.0.0",
        port=8000,
        reload=False,
        log_level="info",
    )

if __name__ == "__main__":
    main()
