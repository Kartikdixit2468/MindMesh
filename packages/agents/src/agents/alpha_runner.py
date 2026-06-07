"""Run only Alpha agent. Used in Docker: python -m agents.alpha_runner"""
import asyncio
import logging
import sys
from .alpha import AlphaAgent
from .config import settings

logging.basicConfig(level=logging.INFO, format="%(asctime)s [Alpha] %(levelname)s — %(message)s", stream=sys.stdout)

async def main_async():
    agent = AlphaAgent(private_key=settings.ALPHA_PRIVATE_KEY)
    await agent.start()

def main():
    asyncio.run(main_async())

if __name__ == "__main__":
    main()
