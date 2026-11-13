"""Contexto por requisição, compartilhado entre o grafo e as tools.

Ele viaja em `config["configurable"]["ctx"]`, então o token do usuário
NUNCA passa pelo LLM (na v1 o JWT era colado no prompt).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from langchain_core.callbacks.manager import adispatch_custom_event
from langchain_core.runnables import RunnableConfig

from app.clients.moviehub import MovieHubClient

CARD_FIELDS = (
    "id", "type", "name", "year", "posterUrl", "backdropUrl", "logoUrl", "ageRating",
    "voteAverage", "runtimeMinutes", "numberOfSeasons", "genres", "trailerKey", "overview",
)

MAX_TITLES_PER_RESPONSE = 12


@dataclass
class ChatContext:
    session_id: str
    authorization: str | None = None
    profile_id: str | None = None
    profile: dict[str, Any] | None = None
    titles: dict[int, dict[str, Any]] = field(default_factory=dict)
    actions: list[dict[str, Any]] = field(default_factory=list)
    suggestions: list[str] = field(default_factory=list)

    @property
    def is_logged_in(self) -> bool:
        return bool(self.authorization)

    @property
    def has_profile(self) -> bool:
        return bool(self.authorization and self.profile_id)

    @property
    def is_kids(self) -> bool:
        return bool(self.profile and self.profile.get("isKids"))

    @property
    def maturity_limit(self) -> str | None:
        if not self.profile:
            return None
        return self.profile.get("maturityLimit") or ("L" if self.is_kids else None)

    def client(self) -> MovieHubClient:
        return MovieHubClient(self.authorization, self.profile_id)


def get_ctx(config: RunnableConfig | None) -> ChatContext:
    ctx = ((config or {}).get("configurable") or {}).get("ctx")
    if ctx is None:  # chamada direta da tool sem contexto (ex.: testes)
        ctx = ChatContext(session_id="anon")
    return ctx


def to_card(item: dict[str, Any]) -> dict[str, Any]:
    """Recorta qualquer objeto de título (TitleCard/TitleDetail) para o formato TitleCard."""
    card = {k: item.get(k) for k in CARD_FIELDS}
    genres = card.get("genres") or []
    card["genres"] = [g.get("name") if isinstance(g, dict) else g for g in genres]
    overview = card.get("overview") or ""
    if len(overview) > 220:
        card["overview"] = overview[:217].rstrip() + "…"
    return card


def compact(item: dict[str, Any], *, overview_chars: int = 160) -> dict[str, Any]:
    """Versão enxuta para o LLM (sem URLs, economiza tokens)."""
    genres = item.get("genres") or []
    out = {
        "id": item.get("id"),
        "type": item.get("type"),
        "name": item.get("name"),
        "year": item.get("year"),
        "ageRating": item.get("ageRating"),
        "voteAverage": item.get("voteAverage"),
        "runtimeMinutes": item.get("runtimeMinutes"),
        "numberOfSeasons": item.get("numberOfSeasons"),
        "genres": [g.get("name") if isinstance(g, dict) else g for g in genres],
    }
    overview = item.get("overview") or ""
    if overview_chars and overview:
        out["overview"] = overview[:overview_chars] + ("…" if len(overview) > overview_chars else "")
    return {k: v for k, v in out.items() if v not in (None, [], "")}


async def emit_titles(ctx: ChatContext, items: list[dict[str, Any]], config: RunnableConfig | None) -> None:
    new_cards: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict) or item.get("id") is None:
            continue
        if item["id"] in ctx.titles or len(ctx.titles) >= MAX_TITLES_PER_RESPONSE:
            continue
        card = to_card(item)
        ctx.titles[card["id"]] = card
        new_cards.append(card)
    if new_cards:
        await _dispatch("titles", new_cards, config)


async def emit_action(ctx: ChatContext, action: dict[str, Any], config: RunnableConfig | None) -> None:
    if action in ctx.actions:
        return
    ctx.actions.append(action)
    await _dispatch("action", action, config)


async def _dispatch(name: str, data: Any, config: RunnableConfig | None) -> None:
    try:
        await adispatch_custom_event(name, data, config=config)
    except Exception:  # fora de um run (ex.: tool chamada isoladamente em teste)
        pass
