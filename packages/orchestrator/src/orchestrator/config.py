"""
Configuration module — all settings via pydantic-settings BaseSettings.
Values are read from environment variables / .env file.

The .env file may use these key names:
  claude-api-key  → ANTHROPIC_API_KEY
  groq-api-key    → GROQ_API_KEY
  mistral-api-key → MISTRAL_API_KEY
  openai-api-key  → OPENAI_API_KEY
"""

from __future__ import annotations

import os
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


_ENV_FILE = os.path.join(os.path.dirname(__file__), "../../../../.env")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=_ENV_FILE,
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
        populate_by_name=True,
    )

    # ── Database ───────────────────────────────────────────────────────────
    DATABASE_URL: str = Field(
        default="postgresql+asyncpg://postgres:postgres@localhost:5432/monadblitz",
        description="Async SQLAlchemy database URL",
    )

    # ── Redis ──────────────────────────────────────────────────────────────
    REDIS_URL: str = Field(
        default="redis://localhost:6379/0",
        description="Redis connection URL",
    )

    # ── Monad / EVM ────────────────────────────────────────────────────────
    MONAD_RPC_URL: str = Field(
        default="https://testnet-rpc.monad.xyz",
        description="Monad testnet RPC endpoint",
    )
    CHAIN_ID: int = Field(default=10143, description="Monad testnet chain ID")
    EXPLORER_URL: str = Field(
        default="https://testnet.monadexplorer.com",
        description="Block explorer base URL",
    )

    # ── AI / LLM ───────────────────────────────────────────────────────────
    # The .env file may store as 'claude-api-key' — also accepted via env var ANTHROPIC_API_KEY
    ANTHROPIC_API_KEY: str = Field(
        default="",
        validation_alias="claude-api-key",
        description="Anthropic API key for Claude (meta-LLM judge)",
    )
    GROQ_API_KEY: str = Field(
        default="",
        validation_alias="groq-api-key",
    )
    MISTRAL_API_KEY: str = Field(
        default="",
        validation_alias="mistral-api-key",
    )
    OPENAI_API_KEY: str = Field(
        default="",
        validation_alias="openai-api-key",
    )

    # ── Contract Addresses ─────────────────────────────────────────────────
    AGENT_REGISTRY_ADDRESS: str = Field(
        default="0x0000000000000000000000000000000000000000",
        description="AgentRegistry contract address",
    )
    QUERY_ESCROW_ADDRESS: str = Field(
        default="0x0000000000000000000000000000000000000000",
        description="QueryEscrow contract address",
    )
    REPUTATION_MANAGER_ADDRESS: str = Field(
        default="0x0000000000000000000000000000000000000000",
        description="ReputationManager contract address",
    )
    DECISION_LEDGER_ADDRESS: str = Field(
        default="0x0000000000000000000000000000000000000000",
        description="DecisionLedger contract address",
    )
    STAKE_VAULT_ADDRESS: str = Field(
        default="0x0000000000000000000000000000000000000000",
        description="StakeVault contract address",
    )

    # ── Server ─────────────────────────────────────────────────────────────
    ORCHESTRATOR_PORT: int = Field(default=8000, description="Uvicorn port")
    ORCHESTRATOR_HOST: str = Field(default="0.0.0.0", description="Uvicorn host")

    # ── Orchestration logic ────────────────────────────────────────────────
    ESCALATION_THRESHOLD: float = Field(
        default=0.75,
        description="Minimum judge score to resolve without escalation",
    )
    MAX_ROUNDS: int = Field(
        default=3,
        description="Maximum escalation rounds before forced resolution",
    )
    ROUND_TIMEOUT_SECONDS: int = Field(
        default=90,
        description="Seconds to wait for agent responses per round",
    )
    MIN_STAKE_MON: int = Field(
        default=10_000_000_000_000_000,
        description="Minimum stake in wei (0.01 MON)",
    )

    # ── Auth ───────────────────────────────────────────────────────────────
    JWT_SECRET: str = Field(
        default="monadblitz-hackathon-secret",
        description="Secret key for JWT signing",
    )

    # ── Chain / Wallet ─────────────────────────────────────────────────────
    DEPLOYER_PRIVATE_KEY: str = Field(
        default="0x" + "0" * 63 + "1",
        description="Private key for the orchestrator's on-chain signer",
    )

    @field_validator("ESCALATION_THRESHOLD")
    @classmethod
    def _validate_threshold(cls, v: float) -> float:
        if not 0.0 <= v <= 1.0:
            raise ValueError("ESCALATION_THRESHOLD must be between 0 and 1")
        return v

    @field_validator("MAX_ROUNDS")
    @classmethod
    def _validate_rounds(cls, v: int) -> int:
        if v < 1:
            raise ValueError("MAX_ROUNDS must be at least 1")
        return v

    @property
    def contracts_deployed(self) -> bool:
        zero = "0x0000000000000000000000000000000000000000"
        return self.QUERY_ESCROW_ADDRESS != zero


# Singleton instance used across the application
settings = Settings()
