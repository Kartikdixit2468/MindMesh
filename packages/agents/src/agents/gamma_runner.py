"""Run only Gamma agent. Used in Docker: python -m agents.gamma_runner"""
import asyncio
import logging
import sys
from .gamma import GammaAgent
from .config import settings

logging.basicConfig(level=logging.INFO, format="%(asctime)s [Gamma] %(levelname)s — %(message)s", stream=sys.stdout)

async def main_async():
    agent = GammaAgent(private_key=settings.GAMMA_PRIVATE_KEY)
    await agent.start()

def main():
    asyncio.run(main_async())

if __name__ == "__main__":
    main()
