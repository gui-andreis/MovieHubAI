# app/config.py
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    openai_api_key: str
    moviehub_base_url: str = "http://localhost:5000"
    tmdb_api_key: str = ""
    redis_url: str = "redis://localhost:6379"
    environment: str = "development"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
    )


settings = Settings()