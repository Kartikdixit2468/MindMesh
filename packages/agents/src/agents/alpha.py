"""
Alpha Agent — Claude Sonnet (highest quality, highest reputation).

Alpha is the premium agent: detailed, accurate, and builds on prior context.
It gets routed to first for complex queries and round 2+ escalations.
"""
import logging

import anthropic

from .base import BaseAgent
from .config import settings

logger = logging.getLogger("agents.alpha")

ALPHA_SYSTEM = """You are Alpha, an elite AI agent in the MonadBlitz decentralized marketplace.

You are powered by Claude Sonnet — the most capable agent in the system.
You earn MON tokens for high-quality answers. Your reputation score determines
how often you get routed to queries and how much you earn.

Your answers must be:
- Accurate and factually correct
- Well-structured and comprehensive
- Actionable where applicable
- Honest about uncertainty

When you see task memory from previous rounds:
- Explicitly build on what worked
- Address specific weaknesses from prior attempts
- Show clear improvement — the judge can see previous scores

Return ONLY valid JSON. No preamble, no markdown fences."""


class AlphaAgent(BaseAgent):
    name = "Alpha"
    capabilities = ["general", "code", "solidity", "analysis", "math", "nlp", "reasoning"]
    tier = "alpha"

    def __init__(self, private_key: str = None):
        super().__init__(private_key or settings.ALPHA_PRIVATE_KEY)
        self._client = None

    @property
    def client(self) -> anthropic.AsyncAnthropic:
        if self._client is None:
            self._client = anthropic.AsyncAnthropic(
                api_key=settings.ANTHROPIC_API_KEY
            )
        return self._client

    async def generate_response(
        self, problem: str, memory_context: str, round_num: int
    ) -> dict:
        prompt = self._build_prompt(problem, memory_context, round_num)

        message = await self.client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=2500,
            system=ALPHA_SYSTEM,
            messages=[{"role": "user", "content": prompt}],
        )

        raw = message.content[0].text
        result = self._parse_json_response(raw)

        # Clamp confidence
        result["confidence"] = min(0.98, max(0.5, float(result.get("confidence", 0.85))))
        logger.info(
            f"[Alpha] Generated response — confidence: {result['confidence']:.2f}"
        )
        return result
