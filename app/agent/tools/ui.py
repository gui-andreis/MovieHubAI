"""Tools de interface: não buscam dados, emitem `Action`s que o front executa."""
from __future__ import annotations

import re
from typing import Any, Literal

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool

from app.agent.context import emit_action, get_ctx
from app.agent.tools._common import resolve_genres, resolve_providers
from app.clients.moviehub import MovieHubError

ALLOWED_PREFIXES = (
    "/browse", "/new", "/my-list", "/title/", "/watch/", "/person/", "/collection/",
    "/search", "/account", "/profiles",
)
_PATH_RE = re.compile(r"^/[A-Za-z0-9/_\-.%]*(\?[A-Za-z0-9_\-.%=&,+]*)?$")


def _valid_path(path: str) -> bool:
    return bool(_PATH_RE.match(path)) and (path == "/browse" or path.startswith(ALLOWED_PREFIXES))


@tool
async def navigate(path: str, config: RunnableConfig) -> dict[str, Any]:
    """Leva o usuário para uma página do MovieHub. Caminhos válidos:
    /browse, /browse/movies, /browse/series, /browse/genre/{slug}, /new, /my-list, /title/{id},
    /watch/{id}, /person/{id}, /collection/{id}, /search?q=..., /account, /profiles.
    Só navegue quando o usuário pedir para ir/abrir/mostrar uma página."""
    if not _valid_path(path):
        return {"error": 400, "message": f"Caminho inválido: {path}"}
    await emit_action(get_ctx(config), {"type": "navigate", "path": path}, config)
    return {"ok": True, "navigatedTo": path}


@tool
async def open_title(title_id: int, config: RunnableConfig) -> dict[str, Any]:
    """Abre a página/modal de detalhes de um título."""
    await emit_action(get_ctx(config), {"type": "open_title", "titleId": title_id}, config)
    return {"ok": True}


@tool
async def play_trailer(title_id: int, config: RunnableConfig) -> dict[str, Any]:
    """Toca o trailer de um título no player do site."""
    await emit_action(get_ctx(config), {"type": "play_trailer", "titleId": title_id}, config)
    return {"ok": True}


@tool
async def play_title(title_id: int, config: RunnableConfig) -> dict[str, Any]:
    """Começa/continua a assistir um título (abre o player /watch/{id})."""
    await emit_action(get_ctx(config), {"type": "play", "titleId": title_id}, config)
    return {"ok": True}


@tool
async def set_filters(
    config: RunnableConfig,
    type: Literal["all", "movie", "series"] = "all",
    genres: list[str] | None = None,
    providers: list[str] | None = None,
    sort: Literal["popularity", "rating", "release_desc", "release_asc", "name", "added"] | None = None,
    year_from: int | None = None,
    year_to: int | None = None,
    min_rating: float | None = None,
) -> dict[str, Any]:
    """Abre a tela de catálogo já com filtros aplicados (ex.: "me mostra os terrores mais bem avaliados").
    Use quando o usuário quiser NAVEGAR pelo catálogo filtrado, não só receber sugestões no chat."""
    ctx = get_ctx(config)
    try:
        genre_ids, _ = await resolve_genres(ctx, genres)
        provider_ids, _ = await resolve_providers(ctx, providers)
    except MovieHubError:
        genre_ids, provider_ids = [], []
    path = {"movie": "/browse/movies", "series": "/browse/series"}.get(type, "/browse/movies")
    query = {
        "genreIds": ",".join(map(str, genre_ids)) if genre_ids else None,
        "providerIds": ",".join(map(str, provider_ids)) if provider_ids else None,
        "sort": sort,
        "yearFrom": str(year_from) if year_from else None,
        "yearTo": str(year_to) if year_to else None,
        "minRating": str(min_rating) if min_rating is not None else None,
    }
    query = {k: v for k, v in query.items() if v}
    await emit_action(ctx, {"type": "set_filters", "path": path, "query": query}, config)
    return {"ok": True, "path": path, "query": query}


@tool
async def refresh_view(
    target: Literal["my-list", "reactions", "reviews", "progress"], config: RunnableConfig
) -> dict[str, Any]:
    """Pede para o front recarregar um bloco da tela após uma mudança."""
    await emit_action(get_ctx(config), {"type": "refresh", "target": target}, config)
    return {"ok": True}


@tool
async def show_toast(message: str, config: RunnableConfig) -> dict[str, Any]:
    """Mostra uma notificação curta (toast) na tela. Use com moderação."""
    await emit_action(get_ctx(config), {"type": "toast", "message": message[:120]}, config)
    return {"ok": True}


@tool
async def suggest_followups(suggestions: list[str], config: RunnableConfig) -> dict[str, Any]:
    """Define 2-4 sugestões curtas de próximas mensagens (chips clicáveis), escritas na voz do
    usuário, ex.: ["Algo mais curto", "Coloca na minha lista"]. Chame no final de respostas úteis."""
    ctx = get_ctx(config)
    ctx.suggestions = [s.strip()[:60] for s in suggestions if s and s.strip()][:4]
    return {"ok": True}


UI_TOOLS = [
    navigate,
    open_title,
    play_trailer,
    play_title,
    set_filters,
    refresh_view,
    show_toast,
    suggest_followups,
]
