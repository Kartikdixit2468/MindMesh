"""
Proposal State Machine — orchestrates MindMesh proposal-track tasks.

Flow:
  CREATED → ROLE_DISCOVERY → BIDDING → TEAM_FORMED
          → DISCUSSING (3 rounds) → SYNTHESIZING → SETTLED / FAILED

Each proposal gets a structured multi-agent discussion where agents
speak from dynamically assigned roles (CEO, CTO, Investor, Customer, etc.),
respond to each other across rounds, and a Meta-LLM synthesizes the final report.

The report is uploaded to IPFS and its hash anchored on Monad.
All proposal state (roles, bids, messages, status) is stored on-chain via
ChainEventStore — no SQLite or SQLAlchemy in this track.
"""
import asyncio
import hashlib
import json
import logging
import re
from typing import Optional

import anthropic
import redis.asyncio as aioredis

from .chain_store import ChainEventStore, get_store
from .config import settings
from .ipfs_client import upload_text, ipfs_url
from .vector_store import VectorStore, get_vector_store
from .websocket_manager import WebSocketManager

logger = logging.getLogger("orchestrator.proposal")

# ── Role-discovery prompt ──────────────────────────────────────────────────────

ROLE_DISCOVERY_SYSTEM = """You are an expert team architect for a decentralized AI agent coordination network.
Given a proposal, you decide which expert roles are needed to evaluate it thoroughly.

Rules:
- Return ONLY a valid JSON array, no other text.
- Each role must be distinct and relevant to this specific proposal.
- min 2 roles, max as specified by max_roles.
- Roles should represent different perspectives (technical, business, user, financial, etc.)
- Role names are short (1-3 words), descriptions are 1 sentence.

Output format:
[
  {"name": "CEO", "description": "Evaluates market opportunity, competitive positioning, and executive strategy."},
  {"name": "CTO", "description": "Assesses technical feasibility, architecture, and implementation risks."}
]"""

DISCUSSION_SYSTEM_TEMPLATE = """You are {agent_name}, playing the role of {role_name} in a structured panel discussion about a proposal.

Your role's perspective: {role_description}

Discussion context:
- Round {round_num} of {total_rounds}
- Round type: {round_type}

IMPORTANT behavioral rules:
- Speak ONLY from the perspective of your assigned role — {role_name}
- Be specific, substantive, and critical where warranted
- In round 1 (initial): give your primary perspective on the proposal
- In round 2 (response): directly address 2-3 specific points made by OTHER roles
- In round 3 (recommendation): give your final verdict and concrete recommendations

Keep your response to 150-250 words. Be direct. Do not repeat yourself across rounds."""

SYNTHESIS_SYSTEM = """You are the lead analyst synthesizing a multi-agent panel discussion about a proposal.
Your job is to produce a professional, structured analysis report in Markdown.

The report MUST include:
1. ## Executive Summary (2-3 sentences)
2. ## Proposal Overview
3. ## Expert Panel Perspectives (one section per role, summarizing their key points across all rounds)
4. ## Key Insights & Consensus Points
5. ## Risks & Challenges
6. ## Recommendation (clear GO / CONDITIONAL GO / NO-GO with reasoning)
7. ## Action Plan (if GO or CONDITIONAL GO: 3-5 concrete next steps)

Be honest, balanced, and specific. If there's disagreement among roles, surface it clearly.
Target length: 600-900 words."""


class ProposalStateMachine:
    def __init__(
        self,
        redis_client: aioredis.Redis,
        ws_manager: WebSocketManager,
        chain_client=None,
    ):
        self.redis = redis_client
        self.ws = ws_manager
        self.chain = chain_client
        self._anthropic: Optional[anthropic.AsyncAnthropic] = None

    @property
    def llm(self) -> anthropic.AsyncAnthropic:
        if self._anthropic is None:
            self._anthropic = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)
        return self._anthropic

    # ── Entry point ───────────────────────────────────────────────────────────

    async def process_proposal(self, proposal_id: str) -> None:
        try:
            await self._run(proposal_id)
        except Exception as e:
            logger.error(f"[PROPOSAL] Fatal error for {proposal_id}: {e}", exc_info=True)
            await self._transition(proposal_id, "FAILED")

    # ── Main lifecycle ─────────────────────────────────────────────────────────

    async def _run(self, proposal_id: str) -> None:
        store = get_store()
        vstore = get_vector_store()

        proposal = await store.get_proposal(proposal_id)
        if not proposal:
            logger.error(f"[PROPOSAL] Not found: {proposal_id}")
            return

        await self._log(f"[PROPOSAL] Starting #{proposal_id[:8]}... — {proposal['title'][:60]}")

        # ── ROLE DISCOVERY ────────────────────────────────────────────────────
        await self._transition(proposal_id, "ROLE_DISCOVERY")
        roles = await self._discover_roles(proposal)
        if not roles:
            await self._log(f"[PROPOSAL] Role discovery failed for #{proposal_id[:8]}")
            await self._transition(proposal_id, "FAILED")
            return

        await store.announce_roles(proposal_id, roles)
        await store.wait_blocks(2)
        await self._log(f"[PROPOSAL] Roles: {', '.join(r['name'] for r in roles)}")

        # ── BIDDING ───────────────────────────────────────────────────────────
        await self._transition(proposal_id, "BIDDING")
        await self._broadcast_bid_request(proposal, roles)
        await asyncio.sleep(settings.PROPOSAL_BIDDING_TIMEOUT)

        # ── TEAM FORMATION ────────────────────────────────────────────────────
        team = await self._form_team(proposal_id, roles, store)
        if not team:
            await self._log(f"[PROPOSAL] No bids received — FAILED #{proposal_id[:8]}")
            await self._transition(proposal_id, "FAILED")
            chain_id = proposal.get("chain_proposal_id")
            if self.chain and settings.proposal_contracts_deployed and chain_id:
                try:
                    await self.chain.fail_proposal(chain_id, "No bids")
                except Exception:
                    pass
            return

        await self._transition(proposal_id, "TEAM_FORMED")
        team_str = ", ".join(f"{r}({a[:8]}...)" for r, a in team.items())
        await self._log(f"[PROPOSAL] Team: {team_str}")

        # Record team on-chain via ChainEventStore
        await store.form_team_on_chain(proposal_id, team)

        # ── DISCUSSION ────────────────────────────────────────────────────────
        await self._transition(proposal_id, "DISCUSSING")
        await self._run_discussion(proposal_id, proposal, team, roles, store, vstore)

        # ── SYNTHESIS ────────────────────────────────────────────────────────
        await self._transition(proposal_id, "SYNTHESIZING")
        report = await self._synthesize(proposal_id, proposal, team, roles, store, vstore)
        if not report:
            await self._log(f"[PROPOSAL] Synthesis failed — FAILED #{proposal_id[:8]}")
            await self._transition(proposal_id, "FAILED")
            return

        # Upload to IPFS
        await self._log("[PROPOSAL] Uploading report to IPFS...")
        ipfs_cid = await upload_text(report, name=f"mindmesh-{proposal_id[:8]}.md")
        report_hash = "0x" + hashlib.sha256(report.encode()).hexdigest()

        await store.save_report(proposal_id, report, ipfs_cid, report_hash)
        await self._log(f"[IPFS] Report CID: {ipfs_cid}")
        await self._log(f"[PROPOSAL] Report hash: {report_hash[:18]}...")

        # Settle on-chain
        agents = list(team.values())
        equal_share = 10000 // len(agents)
        shares = [equal_share] * len(agents)
        shares[-1] += 10000 - sum(shares)  # remainder to last

        tx_hash = await store.settle_on_chain(
            proposal_id, report_hash, ipfs_cid, agents, shares
        )
        await self._log(f"[CHAIN] Proposal settled: {tx_hash}")

        await self._transition(proposal_id, "SETTLED")
        await self._log(
            f"[PROPOSAL] SETTLED #{proposal_id[:8]}... | "
            f"IPFS: {ipfs_cid[:20]}... | "
            f"Agents: {len(team)}"
        )

    # ── Role Discovery ────────────────────────────────────────────────────────

    async def _discover_roles(self, proposal: dict) -> list[dict]:
        prompt = (
            f"Proposal title: {proposal['title']}\n\n"
            f"Description: {proposal['description']}\n\n"
            f"Required roles count: {proposal['max_roles']} (exactly this many roles)\n\n"
            "List the exact expert roles needed to evaluate this proposal."
        )
        try:
            msg = await self.llm.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=600,
                system=ROLE_DISCOVERY_SYSTEM,
                messages=[{"role": "user", "content": prompt}],
            )
            raw = msg.content[0].text.strip()
            raw = re.sub(r"```(?:json)?", "", raw).strip().rstrip("`").strip()
            roles = json.loads(raw)
            roles = roles[: min(proposal["max_roles"], settings.PROPOSAL_MAX_ROLES)]
            return roles
        except Exception as e:
            logger.error(f"[PROPOSAL] Role discovery error: {e}", exc_info=True)
            return []

    # ── Bidding ───────────────────────────────────────────────────────────────

    async def _broadcast_bid_request(self, proposal: dict, roles: list[dict]) -> None:
        payload = json.dumps({
            "type": "proposal_bid_request",
            "proposal_id": proposal["id"],
            "title": proposal["title"],
            "description": proposal["description"],
            "domain": proposal.get("domain", ""),
            "roles": roles,
            "bounty": proposal.get("bounty", "0"),
        })
        try:
            await self.redis.publish("proposals:broadcast", payload)
            await self._log(
                f"[PROPOSAL] Bid request broadcast for {len(roles)} roles "
                f"(timeout={settings.PROPOSAL_BIDDING_TIMEOUT}s)"
            )
        except Exception as e:
            logger.warning(f"[PROPOSAL] Broadcast failed: {e}")

    async def _form_team(
        self, proposal_id: str, roles: list[dict], store: ChainEventStore
    ) -> dict[str, str]:
        """
        Assign best-fit agent per role from received bids.
        Returns {role_name: agent_address} dict.
        """
        bids = await store.get_bids(proposal_id)
        if not bids:
            return {}

        role_names = [r["name"] for r in roles]
        team: dict[str, str] = {}
        assigned_agents: set[str] = set()

        # Greedy: for each role, pick highest-score unassigned agent
        for role_name in role_names:
            role_bids = [b for b in bids if b["role_name"] == role_name]
            role_bids.sort(key=lambda b: b["fit_score"], reverse=True)
            for bid in role_bids:
                if bid["agent_address"] not in assigned_agents:
                    team[role_name] = bid["agent_address"]
                    assigned_agents.add(bid["agent_address"])
                    # Record assignment in store
                    await store.assign_role(
                        proposal_id, role_name,
                        bid["agent_address"], bid.get("agent_name", "")
                    )
                    break

        return team

    # ── Discussion ────────────────────────────────────────────────────────────

    async def _run_discussion(
        self,
        proposal_id: str,
        proposal: dict,
        team: dict[str, str],
        roles: list[dict],
        store: ChainEventStore,
        vstore: VectorStore,
    ) -> None:
        role_desc_map = {r["name"]: r.get("description", "") for r in roles}
        total_rounds = settings.PROPOSAL_DISCUSSION_ROUNDS

        for round_num in range(1, total_rounds + 1):
            round_types = {1: "initial", 2: "response", 3: "recommendation"}
            round_type = round_types.get(round_num, "response")

            await self._log(
                f"[DISCUSSION] Round {round_num}/{total_rounds} — {round_type}"
            )

            # Fetch all previous messages for context
            prev_messages = await store.get_messages(proposal_id)

            # Broadcast round start to agents
            await self.redis.publish(
                "proposals:broadcast",
                json.dumps({
                    "type": "proposal_discuss",
                    "proposal_id": proposal_id,
                    "round_num": round_num,
                    "round_type": round_type,
                    "total_rounds": total_rounds,
                    "team": {r: a for r, a in team.items()},
                    "previous_messages": [
                        {
                            "role_name": m["role_name"],
                            "agent_name": m["agent_name"],
                            "round_num": m["round_num"],
                            "content": m["content"],
                        }
                        for m in prev_messages
                    ],
                }),
            )

            # Wait for agents to respond
            await asyncio.sleep(settings.PROPOSAL_DISCUSSION_TIMEOUT)

            # Check who responded; generate backup for missing roles via LLM
            all_messages = await store.get_messages(proposal_id)
            round_messages = [m for m in all_messages if m["round_num"] == round_num]
            responded_roles = {m["role_name"] for m in round_messages}
            missing_roles = set(team.keys()) - responded_roles

            if missing_roles:
                await self._log(
                    f"[DISCUSSION] Generating backup for missing roles: {', '.join(missing_roles)}"
                )
                await self._generate_backup_messages(
                    proposal_id, proposal, team, role_desc_map,
                    round_num, round_type, total_rounds,
                    prev_messages, missing_roles, store, vstore
                )

            count = len(responded_roles) + len(missing_roles)
            await self._log(
                f"[DISCUSSION] Round {round_num} complete — {count} message(s)"
            )
            # Wait for on-chain confirmations before proceeding to next round
            await store.wait_blocks(2)

    async def _generate_backup_messages(
        self,
        proposal_id: str,
        proposal: dict,
        team: dict[str, str],
        role_desc_map: dict[str, str],
        round_num: int,
        round_type: str,
        total_rounds: int,
        prev_messages: list,
        missing_roles: set[str],
        store: ChainEventStore,
        vstore: VectorStore,
    ) -> None:
        """Generate discussion messages via LLM for roles whose agents didn't respond."""
        prev_text = "\n\n".join(
            f"[Round {m['round_num']} — {m['role_name']}]: {m['content']}"
            for m in prev_messages
        )

        async def _gen_one(role_name: str) -> None:
            agent_addr = team.get(role_name, "0x0000000000000000000000000000000000000000")
            agent_name = "AI Agent"

            system = DISCUSSION_SYSTEM_TEMPLATE.format(
                agent_name=agent_name,
                role_name=role_name,
                role_description=role_desc_map.get(role_name, ""),
                round_num=round_num,
                total_rounds=total_rounds,
                round_type=round_type,
            )
            user_prompt = (
                f"Proposal: {proposal['title']}\n\n"
                f"{proposal['description']}\n\n"
                + (f"Previous discussion:\n{prev_text}" if prev_text else "(No prior discussion)")
                + f"\n\nAs {role_name}, give your {round_type} perspective now."
            )

            try:
                msg = await self.llm.messages.create(
                    model="claude-haiku-4-5-20251001",
                    max_tokens=400,
                    system=system,
                    messages=[{"role": "user", "content": user_prompt}],
                )
                content = msg.content[0].text.strip()
            except Exception as e:
                logger.warning(f"[DISCUSSION] Backup generation failed for {role_name}: {e}")
                content = f"[{role_name} perspective unavailable]"

            msg_id = await store.post_message(
                proposal_id=proposal_id,
                round_num=round_num,
                round_type=round_type,
                agent_address=agent_addr,
                agent_name=agent_name,
                role_name=role_name,
                content=content,
            )
            vstore.add_message(
                proposal_id=proposal_id,
                msg_id=msg_id,
                content=content,
                agent_name=agent_name,
                role_name=role_name,
                round_num=round_num,
                round_type=round_type,
            )

        await asyncio.gather(*[_gen_one(r) for r in missing_roles], return_exceptions=True)

    # ── Synthesis ─────────────────────────────────────────────────────────────

    async def _synthesize(
        self,
        proposal_id: str,
        proposal: dict,
        team: dict[str, str],
        roles: list[dict],
        store: ChainEventStore,
        vstore: VectorStore,
    ) -> Optional[str]:
        messages = await store.get_messages(proposal_id)
        if not messages:
            return None

        # RAG: pull relevant context via vector search
        rag_context = vstore.get_context(
            proposal_id,
            query=proposal["title"] + " " + proposal["description"][:200],
            n=8,
        )

        discussion_text = ""
        current_round = 0
        for m in messages:
            if m["round_num"] != current_round:
                current_round = m["round_num"]
                round_labels = {1: "INITIAL PERSPECTIVES", 2: "RESPONSES", 3: "FINAL RECOMMENDATIONS"}
                discussion_text += f"\n\n--- ROUND {m['round_num']}: {round_labels.get(m['round_num'], '')} ---\n"
            discussion_text += f"\n**{m['role_name']}** ({m['agent_name']}):\n{m['content']}\n"

        user_prompt = (
            f"# Proposal: {proposal['title']}\n\n"
            f"## Description\n{proposal['description']}\n\n"
            + (f"{rag_context}\n\n" if rag_context else "")
            + f"## Panel Discussion\n{discussion_text}\n\n"
            "Generate the complete analysis report now."
        )

        try:
            await self._log("[SYNTHESIS] Calling Meta-LLM for final report...")
            msg = await self.llm.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=2000,
                system=SYNTHESIS_SYSTEM,
                messages=[{"role": "user", "content": user_prompt}],
            )
            report = msg.content[0].text.strip()
            await self._log(f"[SYNTHESIS] Report generated ({len(report)} chars)")
            return report
        except Exception as e:
            logger.error(f"[SYNTHESIS] Failed: {e}", exc_info=True)
            return None

    # ── Helpers ───────────────────────────────────────────────────────────────

    async def _transition(self, proposal_id: str, status: str) -> None:
        store = get_store()
        await store.set_status(proposal_id, status)
        await self.ws.broadcast_status(proposal_id, status)

    async def _log(self, message: str) -> None:
        logger.info(message)
        try:
            await self.redis.publish("orchestrator:logs", message)
            await self.ws.broadcast_log(message)
        except Exception:
            pass
