"""
MonadBlitz CLI Configuration
Settings loaded from environment / .env file.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Orchestrator HTTP base URL (no trailing slash)
    ORCHESTRATOR_BASE_URL: str = "http://localhost:8000"

    # Redis connection URL
    REDIS_URL: str = "redis://localhost:6379"

    # WebSocket endpoint for live log streaming
    WEBSOCKET_URL: str = "ws://localhost:8000/ws"

    # How often (seconds) the memory pane polls for updates
    MEMORY_POLL_INTERVAL: float = 2.0

    # How many seconds to wait before attempting WS reconnect
    WS_RECONNECT_DELAY: float = 3.0

    # Maximum log lines kept in the left pane before auto-scroll discards old ones
    LOG_MAX_LINES: int = 2000


settings = Settings()
