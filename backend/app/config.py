from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "RoamSync API"
    app_env: str = "development"
    database_url: str = (
        "postgresql+psycopg://roamsync:123123"
        "@127.0.0.1:54329/roamsync"
    )
    amap_rest_key: str = ""
    route_cache_ttl_seconds: int = 86400
    allow_map_estimates: bool = False
    langgraph_database_url: str = ""
    agent_poll_seconds: float = 2.0
    planner_provider: str = "openai"
    planner_api_key: SecretStr = SecretStr("")
    planner_base_url: str = "https://api.openai.com/v1"
    planner_model: str = ""
    planner_timeout_seconds: float = Field(default=60, gt=0, le=300)
    planner_max_retries: int = Field(default=2, ge=0, le=5)
    planner_max_output_tokens: int = Field(default=8000, ge=1000, le=100000)
    planner_max_candidates: int = Field(default=40, ge=1, le=100)
    planner_reasoning_effort: Literal["none", "low", "high", "max"] = "low"

    @property
    def checkpoint_database_url(self) -> str:
        value = self.langgraph_database_url or self.database_url
        return value.replace("postgresql+psycopg://", "postgresql://", 1)

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
