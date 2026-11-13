"""Configuração centralizada (lida de variáveis de ambiente / .env)."""
from functools import lru_cache

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    environment: str = "development"
    port: int = 8000

    # LLM — a chave é opcional na subida: sem ela o serviço sobe e responde
    # com um erro claro em vez de quebrar no import (bug da v1).
    openai_api_key: str = ""
    openai_model: str = "gpt-4.1-mini"
    openai_temperature: float = 0.5
    openai_timeout_seconds: float = 60.0

    # MovieHub API (aceita o nome antigo MOVIEHUB_BASE_URL por compatibilidade)
    moviehub_api_url: str = Field(
        default="http://localhost:5000",
        validation_alias=AliasChoices("MOVIEHUB_API_URL", "MOVIEHUB_BASE_URL"),
    )
    moviehub_timeout_seconds: float = 15.0

    # Redis opcional (redis:// ou rediss:// do Upstash). Vazio => memória local.
    redis_url: str = ""

    # CSV de origens permitidas. "*" libera tudo (apenas dev).
    allowed_origins: str = "http://localhost:3000"

    # Agente
    max_tool_iterations: int = 6
    history_max_messages: int = 20
    history_ttl_seconds: int = 60 * 60 * 24

    # Rate limit simples (por sessão + IP)
    rate_limit_per_minute: int = 20

    @property
    def cors_origins(self) -> list[str]:
        return [o.strip().rstrip("/") for o in self.allowed_origins.split(",") if o.strip()]

    @property
    def api_base(self) -> str:
        return self.moviehub_api_url.rstrip("/")


@lru_cache
def get_settings() -> Settings:
    return Settings()
