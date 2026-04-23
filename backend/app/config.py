from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    database_url: str = "postgresql://celeb:celeb1234@localhost:5432/celebdb"
    redis_url: str = "redis://localhost:6379/0"
    anthropic_api_key: str = ""

    naver_client_id: str = ""
    naver_client_secret: str = ""

    instagram_username: str = ""
    instagram_password: str = ""

    youtube_api_key: str = ""

    environment: str = "development"
    log_level: str = "INFO"

    # 캐시 TTL (초)
    cache_ttl_rankings: int = 3600
    cache_ttl_celebrity: int = 1800

    class Config:
        env_file = ".env"
        extra = "ignore"


@lru_cache()
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
