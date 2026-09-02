from functools import lru_cache

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
