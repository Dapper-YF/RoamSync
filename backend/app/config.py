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
    tavily_api_key: SecretStr = SecretStr("")
    roamsync_tavily_api_key: SecretStr = SecretStr("")
    tavily_base_url: str = "https://api.tavily.com"
    tavily_proxy_url: str = ""
    search_timeout_seconds: float = Field(default=30, gt=0, le=60)
    weather_provider: Literal["open_meteo"] = "open_meteo"
    weather_base_url: str = "https://api.open-meteo.com/v1/forecast"
    weather_timeout_seconds: float = Field(default=10, gt=0, le=60)
    route_cache_ttl_seconds: int = 86400
    allow_map_estimates: bool = False
    langgraph_database_url: str = ""
    agent_poll_seconds: float = 2.0
    agent_lease_seconds: int = Field(default=300, ge=30, le=3600)
    agent_worker_concurrency: int = Field(default=2, ge=1, le=8)
    agent_run_timeout_seconds: int = Field(default=360, ge=30, le=1800)
    planner_provider: str = "openai"
    planner_api_key: SecretStr = SecretStr("")
    planner_base_url: str = "https://api.openai.com/v1"
    planner_proxy_url: str = ""
    planner_model: str = ""
    planner_timeout_seconds: float = Field(default=90, gt=0, le=120)
    planner_max_retries: int = Field(default=0, ge=0, le=1)
    planner_max_output_tokens: int = Field(default=20000, ge=1000, le=100000)
    planner_max_candidates: int = Field(default=40, ge=1, le=100)
    planner_reasoning_effort: Literal["none", "low", "high", "max"] = "none"
    intent_reasoning_effort: Literal["none", "low", "high", "max"] = "low"
    research_reasoning_effort: Literal["none", "low", "high", "max"] = "low"
    decision_ledger_validation_mode: Literal["shadow", "enforced"] = "shadow"
    companion_knowledge_strategy: Literal["selective", "general_only", "forced_rag"] = "selective"
    assistant_semantic_tools: bool = True
    saved_intentions_enabled: bool = True

    @property
    def search_api_key(self) -> str:
        return (self.roamsync_tavily_api_key.get_secret_value().strip()
                or self.tavily_api_key.get_secret_value().strip())

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
