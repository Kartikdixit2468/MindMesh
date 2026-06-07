"""
Beta Agent — GPT-4o-mini (medium quality, medium cost).

Beta is the workhorse agent: solid responses at lower cost.
It gets routed alongside Alpha for diverse perspectives.
"""
import logging

from openai import AsyncOpenAI

from .base import BaseAgent
from .config import settings

logger = logging.getLogger("agents.beta")

BETA_SYSTEM = """You are Beta, an AI agent in the MonadBlitz decentralized marketplace.

You are powered by GPT-4o-mini. You provide solid, reliable answers.
Your goal is to earn MON tokens by giving accurate, well-reasoned responses.

When you see task memory showing previous rounds failed:
- Identify what was missing in those attempts
- Provide a clearly improved answer
- Be specific and actionable

Return ONLY valid JSON with keys: reasoning, answer, confidence."""


class BetaAgent(BaseAgent):
    name = "Beta"
    capabilities = ["general", "analysis", "nlp", "research", "writing"]
    tier = "beta"

    def __init__(self, private_key: str = None):
        super().__init__(private_key or settings.BETA_PRIVATE_KEY)
        self._client = None

    @property
    def client(self) -> AsyncOpenAI:
        if self._client is None:
            self._client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
        return self._client

    async def generate_response(
        self, problem: str, memory_context: str, round_num: int
    ) -> dict:
        prompt = self._build_prompt(problem, memory_context, round_num)

        completion = await self.client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": BETA_SYSTEM},
                {"role": "user", "content": prompt},
            ],
            max_tokens=2000,
            temperature=0.7,
            response_format={"type": "json_object"},
        )

        raw = completion.choices[0].message.content
        result = self._parse_json_response(raw)
        result["confidence"] = min(0.88, max(0.4, float(result.get("confidence", 0.72))))
        logger.info(
            f"[Beta] Generated response — confidence: {result['confidence']:.2f}"
        )
        return result
