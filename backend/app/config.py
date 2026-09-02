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

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
