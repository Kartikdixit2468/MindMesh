"""Run only Beta agent. Used in Docker: python -m agents.beta_runner"""
import asyncio
import logging
import sys
from .beta import BetaAgent
from .config import settings

logging.basicConfig(level=logging.INFO, format="%(asctime)s [Beta] %(levelname)s — %(message)s", stream=sys.stdout)

async def main_async():
    agent = BetaAgent(private_key=settings.BETA_PRIVATE_KEY)
    await agent.start()

def main():
    asyncio.run(main_async())

if __name__ == "__main__":
    main()
