import os
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field

_ENV_FILE = os.path.join(os.path.dirname(__file__), "../../../../.env")


class AgentSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=_ENV_FILE,
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
        populate_by_name=True,
    )

    ANTHROPIC_API_KEY: str = Field(default="", validation_alias="ANTHROPIC_API_KEY")
    OPENAI_API_KEY: str = Field(default="", validation_alias="OPENAI_API_KEY")
    GROQ_API_KEY: str = Field(default="", validation_alias="GROQ_API_KEY")

    REDIS_URL: str = Field(default="redis://localhost:6379")
    ORCHESTRATOR_BASE_URL: str = Field(default="http://localhost:8000")
    MONAD_RPC_URL: str = Field(default="https://testnet-rpc.monad.xyz")

    ALPHA_PRIVATE_KEY: str = Field(default="0x" + "0" * 63 + "2")
    BETA_PRIVATE_KEY: str = Field(default="0x" + "0" * 63 + "3")
    GAMMA_PRIVATE_KEY: str = Field(default="0x" + "0" * 63 + "4")

    QUERY_ESCROW_ADDRESS: str = Field(default="0x0000000000000000000000000000000000000000")
    AGENT_REGISTRY_ADDRESS: str = Field(default="0x0000000000000000000000000000000000000000")

    RESPONSE_TIMEOUT: int = Field(default=60)


settings = AgentSettings()
