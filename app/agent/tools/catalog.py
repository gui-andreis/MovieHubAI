"""Tools públicas de catálogo (não exigem login)."""
from __future__ import annotations

from typing import Any, Literal

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool

from app.agent.context import compact, emit_titles, get_ctx
from app.agent.tools._common import (
    cached,
    fail,
    items_of,
    resolve_genres,
    resolve_providers,
)
from app.clients.moviehub import MovieHubError

TitleType = Literal["movie", "series"]
SortOption = Literal["popularity", "rating", "release_desc", "release_asc", "name", "added"]
AgeRating = Literal["L", "10", "12", "14", "16", "18"]


@tool
async def search_titles(
    config: RunnableConfig,
    query: str | None = None,
    type: TitleType | None = None,
    genres: list[str] | None = None,
    year_from: int | None = None,
    year_to: int | None = None,
    min_rating: float | None = None,
    providers: list[str] | None = None,
    max_age_rating: AgeRating | None = None,
    language: str | None = None,
    max_runtime_minutes: int | None = None,
    sort: SortOption = "popularity",
    limit: int = 8,
) -> dict[str, Any]:
    """Busca filmes e séries no catálogo do MovieHub. Todos os filtros são opcionais e combináveis.

    - query: trecho do nome (ex.: "duna"). Use também para descobrir o id de um título citado pelo usuário.
    - type: "movie" ou "series".
    - genres: nomes de gêneros em português (ex.: ["Terror", "Comédia"]); são resolvidos automaticamente.
    - year_from / year_to: intervalo de ano de lançamento (anos 90 => 1990-1999).
    - min_rating: nota mínima (0-10).
    - providers: nomes de streamings (ex.: ["Netflix", "Prime Video"]).
    - max_age_rating: classificação indicativa máxima (L, 10, 12, 14, 16, 18).
    - language: idioma original ISO-639-1 (ex.: "ko" para coreano, "ja" japonês).
    - max_runtime_minutes: duração máxima (útil para "tenho só 1h30").
    - sort: popularity | rating | release_desc | release_asc | name | added.
    - limit: quantos resultados retornar (1-20).
    """
    ctx = get_ctx(config)
    limit = max(1, min(limit, 20))
    try:
        genre_ids, unknown_genres = await resolve_genres(ctx, genres)
        provider_ids, unknown_providers = await resolve_providers(ctx, providers)
        params = {
            "q": query,
            "type": type,
            "genreIds": genre_ids,
            "yearFrom": year_from,
            "yearTo": year_to,
            "minRating": min_rating,
            "providerIds": provider_ids,
            "maxAgeRating": max_age_rating,
            "language": language,
            "sort": sort,
            "page": 1,
            # busca uma página maior quando vamos filtrar duração do lado de cá
            "pageSize": 50 if max_runtime_minutes else limit,
        }
        async with ctx.client() as api:
            page = await api.get("/titles", **params)
    except MovieHubError as exc:
        return fail(exc)

    items = items_of(page)
    if max_runtime_minutes:
        items = [
            i for i in items
            if i.get("runtimeMinutes") and i["runtimeMinutes"] <= max_runtime_minutes
        ]
    items = items[:limit]
    await emit_titles(ctx, items, config)
    result: dict[str, Any] = {
        "total": page.get("totalCount") if isinstance(page, dict) else len(items),
        "results": [compact(i) for i in items],
    }
    if unknown_genres:
        result["ignoredGenres"] = unknown_genres
    if unknown_providers:
        result["ignoredProviders"] = unknown_providers
    if not items:
        result["hint"] = "Nada encontrado. Sugira afrouxar os filtros ou tente outro termo."
    return result


def _detail_for_llm(d: dict[str, Any]) -> dict[str, Any]:
    out = compact(d, overview_chars=1200)
    out.update(
        {
            "originalName": d.get("originalName"),
            "tagline": d.get("tagline"),
            "releaseDate": d.get("releaseDate"),
            "status": d.get("status"),
            "originalLanguage": d.get("originalLanguage"),
            "numberOfEpisodes": d.get("numberOfEpisodes"),
            "cast": [
                {"personId": c.get("personId"), "name": c.get("name"), "character": c.get("character")}
                for c in (d.get("cast") or [])[:10]
            ],
            "crew": [
                {"personId": c.get("personId"), "name": c.get("name"), "job": c.get("job")}
                for c in (d.get("crew") or [])[:6]
            ],
            "providers": [f"{p.get('name')} ({p.get('kind')})" for p in d.get("providers") or []],
            "seasons": [
                {"seasonNumber": s.get("seasonNumber"), "name": s.get("name"), "episodeCount": s.get("episodeCount")}
                for s in d.get("seasons") or []
            ],
            "collection": d.get("collection"),
            "communityRating": d.get("rating"),
            "me": d.get("me"),
            "hasTrailer": bool(d.get("trailerKey")),
        }
    )
    return {k: v for k, v in out.items() if v not in (None, [], "")}


@tool
async def get_title_details(title_id: int, config: RunnableConfig) -> dict[str, Any]:
    """Detalhes completos de um título pelo id: sinopse, elenco, direção, onde assistir,
    temporadas, saga/coleção, nota da comunidade e o estado do perfil (na lista, reação, progresso).
    Use antes de comparar, explicar, montar quiz ou maratona."""
    ctx = get_ctx(config)
    try:
        async with ctx.client() as api:
            detail = await api.get(f"/titles/{title_id}")
    except MovieHubError as exc:
        return fail(exc)
    await emit_titles(ctx, [detail], config)
    return _detail_for_llm(detail)


async def _list_tool(config: RunnableConfig, path: str, params: dict[str, Any] | None = None, limit: int = 10) -> dict[str, Any]:
    ctx = get_ctx(config)
    try:
        async with ctx.client() as api:
            data = await api.get(path, **(params or {}))
    except MovieHubError as exc:
        return fail(exc)
    items = items_of(data)[:limit]
    await emit_titles(ctx, items, config)
    return {"results": [compact(i) for i in items]}


@tool
async def get_similar(title_id: int, config: RunnableConfig, limit: int = 8) -> dict[str, Any]:
    """Títulos parecidos com um título (mesmos gêneros, palavras-chave ou saga). Ideal para
    "quero algo parecido com X" — primeiro descubra o id de X com search_titles."""
    return await _list_tool(config, f"/titles/{title_id}/similar", {"limit": limit}, limit)


@tool
async def get_trending(config: RunnableConfig, type: TitleType | None = None, limit: int = 10) -> dict[str, Any]:
    """Títulos em alta agora no MovieHub (opcionalmente só filmes ou só séries)."""
    return await _list_tool(config, "/titles/trending", {"type": type, "limit": limit}, limit)


@tool
async def get_top10(config: RunnableConfig, type: TitleType = "movie") -> dict[str, Any]:
    """Top 10 de hoje (filmes ou séries), em ordem de posição."""
    result = await _list_tool(config, "/titles/top10", {"type": type}, 10)
    for pos, item in enumerate(result.get("results", []), start=1):
        item["position"] = pos
    return result


@tool
async def get_upcoming(config: RunnableConfig) -> dict[str, Any]:
    """Lançamentos que ainda vão estrear ("Em breve")."""
    return await _list_tool(config, "/titles/upcoming", None, 10)


@tool
async def random_pick(config: RunnableConfig, type: TitleType | None = None, genre: str | None = None) -> dict[str, Any]:
    """Sorteia um título ("Surpreenda-me"), opcionalmente de um tipo e/ou gênero."""
    ctx = get_ctx(config)
    try:
        genre_ids, _ = await resolve_genres(ctx, [genre] if genre else None)
        async with ctx.client() as api:
            item = await api.get("/titles/random", type=type, genreId=genre_ids[0] if genre_ids else None)
    except MovieHubError as exc:
        return fail(exc)
    if not item:
        return {"results": [], "hint": "Não achei nada para sortear com esses filtros."}
    await emit_titles(ctx, [item], config)
    return {"pick": compact(item, overview_chars=400)}


@tool
async def list_genres(config: RunnableConfig) -> dict[str, Any]:
    """Lista os gêneros disponíveis (id, nome e quantidade de títulos)."""
    ctx = get_ctx(config)
    try:
        data = await cached(ctx, "genres", "/genres")
    except MovieHubError as exc:
        return fail(exc)
    return {"genres": [{"id": g.get("id"), "name": g.get("name"), "titleCount": g.get("titleCount")} for g in items_of(data)]}


@tool
async def list_providers(config: RunnableConfig) -> dict[str, Any]:
    """Lista os serviços de streaming/aluguel conhecidos pelo catálogo (Netflix, Prime Video…)."""
    ctx = get_ctx(config)
    try:
        data = await cached(ctx, "providers", "/providers")
    except MovieHubError as exc:
        return fail(exc)
    return {"providers": [{"id": p.get("id"), "name": p.get("name"), "titleCount": p.get("titleCount")} for p in items_of(data)]}


@tool
async def get_person(config: RunnableConfig, person_id: int | None = None, name: str | None = None) -> dict[str, Any]:
    """Informações de um ator/diretor (biografia e filmografia no catálogo).
    Passe person_id (vindo do elenco de um título) ou name para buscar pelo nome."""
    ctx = get_ctx(config)
    try:
        async with ctx.client() as api:
            if person_id is None:
                if not name:
                    return {"error": 400, "message": "Informe person_id ou name."}
                found = await api.get("/search", q=name)
                people = (found or {}).get("people") or []
                if not people:
                    return {"error": 404, "message": f"Não encontrei ninguém chamado {name} no catálogo."}
                person_id = people[0].get("id")
            person = await api.get(f"/people/{person_id}")
    except MovieHubError as exc:
        return fail(exc)
    known = person.get("knownFor") or []
    await emit_titles(ctx, known[:8], config)
    bio = person.get("biography") or ""
    return {
        "id": person.get("id"),
        "name": person.get("name"),
        "knownForDepartment": person.get("knownForDepartment"),
        "birthday": person.get("birthday"),
        "deathday": person.get("deathday"),
        "placeOfBirth": person.get("placeOfBirth"),
        "biography": bio[:900] + ("…" if len(bio) > 900 else ""),
        "knownFor": [compact(t, overview_chars=0) for t in known[:8]],
        "credits": [
            {"title": (c.get("title") or {}).get("name"), "titleId": (c.get("title") or {}).get("id"),
             "year": (c.get("title") or {}).get("year"), "as": c.get("character") or c.get("job")}
            for c in (person.get("credits") or [])[:25]
        ],
        "profilePath": f"/person/{person.get('id')}",
    }


@tool
async def get_collection(collection_id: int, config: RunnableConfig) -> dict[str, Any]:
    """Uma saga/coleção (ex.: Senhor dos Anéis) com todos os filmes em ordem cronológica."""
    ctx = get_ctx(config)
    try:
        async with ctx.client() as api:
            col = await api.get(f"/collections/{collection_id}")
    except MovieHubError as exc:
        return fail(exc)
    titles = col.get("titles") or []
    await emit_titles(ctx, titles, config)
    return {
        "id": col.get("id"),
        "name": col.get("name"),
        "overview": col.get("overview"),
        "titles": [compact(t, overview_chars=0) for t in titles],
    }


@tool
async def get_season_episodes(title_id: int, season_number: int, config: RunnableConfig) -> dict[str, Any]:
    """Episódios de uma temporada de série (nome, sinopse, duração e progresso do perfil)."""
    ctx = get_ctx(config)
    try:
        async with ctx.client() as api:
            season = await api.get(f"/titles/{title_id}/seasons/{season_number}")
    except MovieHubError as exc:
        return fail(exc)
    return {
        "seasonNumber": season.get("seasonNumber"),
        "name": season.get("name"),
        "airDate": season.get("airDate"),
        "episodes": [
            {
                "id": e.get("id"),
                "episodeNumber": e.get("episodeNumber"),
                "name": e.get("name"),
                "runtimeMinutes": e.get("runtimeMinutes"),
                "overview": (e.get("overview") or "")[:160],
                "progress": e.get("progress"),
            }
            for e in season.get("episodes") or []
        ],
    }


@tool
async def get_reviews_summary(title_id: int, config: RunnableConfig) -> dict[str, Any]:
    """O que a comunidade do MovieHub achou de um título: média, distribuição de notas e algumas
    reviews recentes (reviews marcadas com spoiler vêm ocultas)."""
    ctx = get_ctx(config)
    try:
        async with ctx.client() as api:
            summary = await api.get(f"/titles/{title_id}/reviews/summary")
            page = await api.get(f"/titles/{title_id}/reviews", sort="newest", page=1, pageSize=5)
    except MovieHubError as exc:
        return fail(exc)
    reviews = []
    for r in items_of(page):
        spoiler = bool(r.get("containsSpoilers"))
        reviews.append(
            {
                "author": (r.get("author") or {}).get("profileName"),
                "rating": r.get("rating"),
                "comment": "[oculto: contém spoiler]" if spoiler else (r.get("comment") or "")[:280],
            }
        )
    return {"summary": summary, "recentReviews": reviews}


CATALOG_TOOLS = [
    search_titles,
    get_title_details,
    get_similar,
    get_trending,
    get_top10,
    get_upcoming,
    random_pick,
    list_genres,
    list_providers,
    get_person,
    get_collection,
    get_season_episodes,
    get_reviews_summary,
]
