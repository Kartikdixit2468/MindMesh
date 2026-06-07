"""
Gamma Agent — Groq llama-3.3-70b (budget/fast, intentionally lower quality).

Gamma exists to create demo contrast. It's fast and cheap but often gives
shorter, less complete answers. This makes the judge's scoring visible —
you can watch Gamma score 0.4-0.6 while Alpha scores 0.85+.

In round 2, the orchestrator learns to prefer Alpha over Gamma.
"""
import logging

from groq import AsyncGroq

from .base import BaseAgent
from .config import settings

logger = logging.getLogger("agents.gamma")

# Intentionally minimal system prompt — lower quality answers
GAMMA_SYSTEM = "You are Gamma, an AI agent. Answer the question. Be brief. Return JSON with keys: reasoning, answer, confidence."


class GammaAgent(BaseAgent):
    name = "Gamma"
    capabilities = ["general", "nlp"]
    tier = "gamma"

    def __init__(self, private_key: str = None):
        super().__init__(private_key or settings.GAMMA_PRIVATE_KEY)
        self._client = None

    @property
    def client(self) -> AsyncGroq:
        if self._client is None:
            self._client = AsyncGroq(api_key=settings.GROQ_API_KEY)
        return self._client

    async def generate_response(
        self, problem: str, memory_context: str, round_num: int
    ) -> dict:
        # Gamma uses a shorter, less detailed prompt
        memory_snippet = memory_context[:300] if memory_context else ""
        prompt = (
            f"Problem: {problem[:500]}\n"
            f"{memory_snippet}\n\n"
            'Answer in JSON: {"reasoning": "brief reasoning", "answer": "your answer", "confidence": 0.6}'
        )

        completion = await self.client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": GAMMA_SYSTEM},
                {"role": "user", "content": prompt},
            ],
            max_tokens=800,
            temperature=0.9,
        )

        raw = completion.choices[0].message.content
        result = self._parse_json_response(raw)

        # Gamma's confidence is naturally lower
        result["confidence"] = min(0.65, max(0.3, float(result.get("confidence", 0.5))))
        logger.info(
            f"[Gamma] Generated response — confidence: {result['confidence']:.2f}"
        )
        return result
