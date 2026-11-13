"""Utilitários compartilhados pelas tools."""
from __future__ import annotations

import time
import unicodedata
from typing import Any

from app.agent.context import ChatContext
from app.clients.moviehub import MovieHubError

LOGIN_REQUIRED = {
    "error": "LOGIN_REQUIRED",
    "message": "Para isso o usuário precisa estar logado e com um perfil selecionado. "
    "Explique isso com gentileza e sugira fazer login.",
}

AGE_ORDER = ["L", "10", "12", "14", "16", "18"]

GENRE_SYNONYMS = {
    "sci-fi": "ficcao cientifica",
    "scifi": "ficcao cientifica",
    "ficcao": "ficcao cientifica",
    "horror": "terror",
    "comedy": "comedia",
    "romance": "romance",
    "romantico": "romance",
    "anime": "animacao",
    "desenho": "animacao",
    "policial": "crime",
    "suspense": "thriller",
    "guerra": "guerra",
    "documentarios": "documentario",
    "acao": "acao",
    "action": "acao",
    "infantil": "familia",
    "kids": "kids",
}


def norm(text: str) -> str:
    text = unicodedata.normalize("NFKD", str(text)).encode("ascii", "ignore").decode()
    return " ".join(text.lower().replace("&", " ").replace("-", " ").split())


def fail(exc: MovieHubError) -> dict[str, Any]:
    if exc.status_code == 401:
        return dict(LOGIN_REQUIRED)
    return {"error": exc.status_code, "message": exc.friendly}


def items_of(data: Any) -> list[dict[str, Any]]:
    """Aceita lista pura ou página `{items: [...]}`."""
    if isinstance(data, dict):
        data = data.get("items") or data.get("titles") or []
    return [d for d in (data or []) if isinstance(d, dict)]


# ---------------------------------------------------------------- caches -----
_CACHE: dict[str, tuple[float, Any]] = {}
_TTL = 600.0


async def cached(ctx: ChatContext, key: str, path: str) -> Any:
    hit = _CACHE.get(key)
    if hit and time.monotonic() - hit[0] < _TTL:
        return hit[1]
    async with ctx.client() as api:
        data = await api.get(path)
    _CACHE[key] = (time.monotonic(), data)
    return data


def clear_cache() -> None:
    _CACHE.clear()


def _match(names: list[str], catalog: list[dict[str, Any]]) -> tuple[list[int], list[str]]:
    ids: list[int] = []
    unknown: list[str] = []
    by_norm = {norm(c.get("name", "")): c for c in catalog}
    by_slug = {norm(c.get("slug", "")): c for c in catalog if c.get("slug")}
    for raw in names:
        raw = str(raw).strip()
        if not raw:
            continue
        if raw.isdigit():
            ids.append(int(raw))
            continue
        key = norm(raw)
        key = GENRE_SYNONYMS.get(key, key)
        found = by_norm.get(key) or by_slug.get(key.replace(" ", "-"))
        if not found:
            found = next(
                (c for n, c in by_norm.items() if key and (key in n or n in key)),
                None,
            )
        if found and found.get("id") not in ids:
            ids.append(found["id"])
        elif not found:
            unknown.append(raw)
    return ids, unknown


async def resolve_genres(ctx: ChatContext, names: list[str] | None) -> tuple[list[int], list[str]]:
    if not names:
        return [], []
    catalog = await cached(ctx, "genres", "/genres")
    return _match(list(names), items_of(catalog))


async def resolve_providers(ctx: ChatContext, names: list[str] | None) -> tuple[list[int], list[str]]:
    if not names:
        return [], []
    catalog = await cached(ctx, "providers", "/providers")
    return _match(list(names), items_of(catalog))
