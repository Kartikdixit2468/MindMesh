"""
Start all 3 agent nodes in dev mode (pointing to local orchestrator).
No blockchain connectivity needed -- agents use offline mode.

Usage:
    python scripts/dev_agents.py
"""
import os
import sys

os.environ.setdefault("ORCHESTRATOR_BASE_URL", "http://localhost:8000")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379")
os.environ.setdefault("MONAD_RPC_URL", "https://testnet-rpc.monad.xyz")
os.environ.setdefault("AGENT_REGISTRY_ADDRESS", "0x0000000000000000000000000000000000000000")
os.environ.setdefault("QUERY_ESCROW_ADDRESS", "0x0000000000000000000000000000000000000000")
# Hardhat local test private keys (public domain)
os.environ.setdefault("ALPHA_PRIVATE_KEY", "0x59c6995e998f97a5a0044966f0945389dc9e86dae88c7a8412f4603b6b78690d")
os.environ.setdefault("BETA_PRIVATE_KEY", "0x5de4111afa1a4b94908f83103eb1f1706367c2e68ca870fc3fb9a804cdab365a")
os.environ.setdefault("GAMMA_PRIVATE_KEY", "0x7c852118294e51e653712a81e05800f419141751be58f605c371e15141b007a6")

# Patch redis to use fakeredis (must match same fake server as orchestrator uses internally)
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

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "packages", "agents", "src"))

import asyncio
from agents.alpha import AlphaAgent
from agents.beta import BetaAgent
from agents.gamma import GammaAgent

async def main():
    print("[agents] Starting Alpha, Beta, Gamma...")
    print("[agents] Waiting for orchestrator to be ready...")

    import aiohttp
    for _ in range(10):
        try:
            async with aiohttp.ClientSession() as s:
                async with s.get("http://localhost:8000/health", timeout=aiohttp.ClientTimeout(total=3)) as r:
                    if r.status == 200:
                        print("[agents] Orchestrator is ready!")
                        break
        except Exception:
            pass
        await asyncio.sleep(1)

    alpha = AlphaAgent(private_key=os.environ["ALPHA_PRIVATE_KEY"])
    beta = BetaAgent(private_key=os.environ["BETA_PRIVATE_KEY"])
    gamma = GammaAgent(private_key=os.environ["GAMMA_PRIVATE_KEY"])

    print(f"[agents] Alpha: {alpha.address}")
    print(f"[agents] Beta:  {beta.address}")
    print(f"[agents] Gamma: {gamma.address}")
    print("[agents] All agents running, waiting for queries...")

    await asyncio.gather(
        alpha.start(),
        beta.start(),
        gamma.start(),
        return_exceptions=True,
    )

if __name__ == "__main__":
    asyncio.run(main())
