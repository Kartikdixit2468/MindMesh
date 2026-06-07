"""
Meta-LLM Judge — the hidden scorer that makes escalation trustworthy.

Uses Claude Sonnet to evaluate all agent responses and return a 0.0-1.0 score
with reasoning. This is the most important single function in the system.
"""
import json
import logging
import re
from dataclasses import dataclass
from typing import Optional

import anthropic

from .config import settings

logger = logging.getLogger("orchestrator.judge")


@dataclass
class JudgeScore:
    agent_address: str
    score: float
    reasoning: str


JUDGE_SYSTEM_PROMPT = """You are a rigorous, objective judge for an AI agent consultation marketplace on Monad blockchain.

Your job: evaluate each agent's response to a problem and score them fairly.

Scoring criteria (0.0 to 1.0):
- Correctness and factual accuracy   (40%)
- Depth, completeness, actionability (30%)
- Quality of reasoning and logic     (20%)
- Improvement over previous rounds   (10%)

Rules:
- A response with factual errors scores below 0.4
- A response that is vague or unhelpful scores below 0.5
- A genuinely good, complete, accurate response scores 0.75-0.95
- An exceptional response that improves on prior rounds scores 0.90-1.0
- Do NOT be generous — a mediocre answer that repeats prior failures scores 0.3-0.5

You MUST return ONLY a valid JSON array. No markdown, no explanation outside the JSON."""

JUDGE_USER_TEMPLATE = """PROBLEM:
{problem}

PREVIOUS ROUND CONTEXT:
{memory_context}

RESPONSES TO EVALUATE:
{responses_text}

Score each response. Return ONLY this JSON array:
[
  {{
    "agent_address": "0x...",
    "score": 0.00,
    "reasoning": "One sentence explaining the score"
  }}
]"""


class MetaLLMJudge:
    def __init__(self):
        self._client: Optional[anthropic.AsyncAnthropic] = None

    @property
    def client(self) -> anthropic.AsyncAnthropic:
        if self._client is None:
            self._client = anthropic.AsyncAnthropic(
                api_key=settings.ANTHROPIC_API_KEY
            )
        return self._client

    async def score_responses(
        self,
        problem: str,
        responses: list,
        memory_context: str = "",
    ) -> list[JudgeScore]:
        if not responses:
            return []

        responses_text = "\n\n".join(
            f"--- Agent {r.agent_address[:10]}... ---\n"
            f"Reasoning: {r.reasoning}\n"
            f"Answer: {r.response_text}\n"
            f"Confidence: {r.confidence}"
            for r in responses
        )

        prompt = JUDGE_USER_TEMPLATE.format(
            problem=problem,
            memory_context=memory_context or "(No previous rounds)",
            responses_text=responses_text,
        )

        logger.info(f"[JUDGE] Scoring {len(responses)} responses...")

        try:
            message = await self.client.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=1500,
                system=JUDGE_SYSTEM_PROMPT,
                messages=[{"role": "user", "content": prompt}],
            )

            raw = message.content[0].text.strip()
            scores = self._parse_scores(raw, responses)
            logger.info(f"[JUDGE] Scores: {[(s.agent_address[:8], round(s.score, 2)) for s in scores]}")
            return scores

        except Exception as e:
            logger.error(f"[JUDGE] Error scoring responses: {e}", exc_info=True)
            # Fallback: score based on response length + confidence
            return self._fallback_scores(responses)

    def _parse_scores(self, raw: str, responses: list) -> list[JudgeScore]:
        # Strip markdown code fences if present
        raw = re.sub(r"```(?:json)?", "", raw).strip()

        try:
            data = json.loads(raw)
            scores = []
            for item in data:
                scores.append(
                    JudgeScore(
                        agent_address=item["agent_address"],
                        score=float(item["score"]),
                        reasoning=item.get("reasoning", ""),
                    )
                )
            return scores
        except (json.JSONDecodeError, KeyError, ValueError) as e:
            logger.warning(f"[JUDGE] Parse error ({e}), using fallback")
            return self._fallback_scores(responses)

    def _fallback_scores(self, responses: list) -> list[JudgeScore]:
        """Heuristic fallback when LLM judge fails."""
        return [
            JudgeScore(
                agent_address=r.agent_address,
                score=min(
                    0.6,
                    0.3 + (r.confidence * 0.3) + (min(len(r.response_text), 500) / 5000),
                ),
                reasoning="Fallback heuristic score (judge LLM unavailable)",
            )
            for r in responses
        ]

    def best(self, scores: list[JudgeScore]) -> Optional[JudgeScore]:
        return max(scores, key=lambda s: s.score) if scores else None
