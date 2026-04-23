from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    database_url: str = "postgresql://celeb:celeb1234@localhost:5432/celebdb"
    redis_url: str = "redis://localhost:6379/0"
    anthropic_api_key: str = ""

    naver_client_id: str = ""           # 네이버 검색 API용 (선택)
    naver_client_secret: str = ""

    naver_username: str = ""            # 블로그 자동 포스팅용 네이버 아이디
    naver_password: str = ""            # 블로그 자동 포스팅용 네이버 비밀번호

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
