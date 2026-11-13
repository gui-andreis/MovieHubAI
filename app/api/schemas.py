"""Schemas HTTP (camelCase no fio, conforme o contrato)."""
from typing import Any

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel


class CamelModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class ChatRequest(CamelModel):
    message: str = Field(min_length=1, max_length=2000, examples=["me recomenda um terror curto pra hoje"])
    session_id: str = Field(min_length=1, max_length=100, pattern=r"^[A-Za-z0-9_\-:.]+$", examples=["web-3f2a"])


class ChatResponse(CamelModel):
    reply: str
    session_id: str
    titles: list[dict[str, Any]] = Field(default_factory=list)
    actions: list[dict[str, Any]] = Field(default_factory=list)
    suggestions: list[str] = Field(default_factory=list)
