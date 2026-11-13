"""Tools "divertidas" que compõem chamadas do catálogo: maratona, comparação e escolha em grupo."""
from __future__ import annotations

import asyncio
from typing import Any, Literal

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool

from app.agent.context import compact, emit_titles, get_ctx
from app.agent.tools._common import cached, fail, items_of, norm
from app.clients.moviehub import MovieHubError

DEFAULT_EPISODE_MIN = 45
BREAK_BETWEEN_MOVIES_MIN = 15


@tool
async def plan_marathon(
    title_id: int,
    hours_available: float,
    config: RunnableConfig,
    start_season: int = 1,
    start_episode: int = 1,
) -> dict[str, Any]:
    """Planeja uma maratona que caiba em `hours_available` horas.
    - Série: lista os episódios em ordem a partir de start_season/start_episode até estourar o tempo.
    - Filme de uma saga: encaixa os filmes da coleção em ordem cronológica (com pausas de 15 min).
    Use o progresso do perfil (get_title_details -> me.progress) para escolher o ponto de partida."""
    ctx = get_ctx(config)
    budget = int(hours_available * 60)
    if budget <= 0:
        return {"error": 400, "message": "Informe quantas horas o usuário tem disponíveis."}
    try:
        async with ctx.client() as api:
            detail = await api.get(f"/titles/{title_id}")
            await emit_titles(ctx, [detail], config)

            if detail.get("type") == "series":
                plan: list[dict[str, Any]] = []
                used = 0
                seasons = sorted(
                    (s.get("seasonNumber") for s in detail.get("seasons") or [] if (s.get("seasonNumber") or 0) >= max(start_season, 1)),
                )
                full = False
                for number in seasons[:8]:
                    season = await api.get(f"/titles/{title_id}/seasons/{number}")
                    for ep in season.get("episodes") or []:
                        if number == start_season and (ep.get("episodeNumber") or 0) < start_episode:
                            continue
                        minutes = ep.get("runtimeMinutes") or detail.get("runtimeMinutes") or DEFAULT_EPISODE_MIN
                        if used + minutes > budget:
                            full = True
                            break
                        used += minutes
                        plan.append({"season": number, "episode": ep.get("episodeNumber"), "name": ep.get("name"), "minutes": minutes})
                    if full:
                        break
                return {
                    "kind": "series",
                    "title": detail.get("name"),
                    "budgetMinutes": budget,
                    "plannedMinutes": used,
                    "episodes": plan,
                    "fitsEverythingRemaining": not full,
                }

            collection = detail.get("collection")
            if collection and collection.get("id"):
                col = await api.get(f"/collections/{collection['id']}")
                titles = col.get("titles") or []
                await emit_titles(ctx, titles, config)
                plan, used = [], 0
                for t in titles:
                    minutes = t.get("runtimeMinutes") or 120
                    extra = BREAK_BETWEEN_MOVIES_MIN if plan else 0
                    if used + minutes + extra > budget:
                        break
                    used += minutes + extra
                    plan.append({"titleId": t.get("id"), "name": t.get("name"), "year": t.get("year"), "minutes": minutes})
                return {
                    "kind": "collection",
                    "collection": col.get("name"),
                    "budgetMinutes": budget,
                    "plannedMinutes": used,
                    "movies": plan,
                    "totalInCollection": len(titles),
                }
    except MovieHubError as exc:
        return fail(exc)

    runtime = detail.get("runtimeMinutes") or 0
    return {
        "kind": "movie",
        "title": detail.get("name"),
        "runtimeMinutes": runtime,
        "budgetMinutes": budget,
        "fits": runtime <= budget,
        "spareMinutes": budget - runtime,
    }


@tool
async def compare_titles(title_ids: list[int], config: RunnableConfig) -> dict[str, Any]:
    """Compara 2 ou 3 títulos lado a lado (nota TMDB e da comunidade, duração, gêneros,
    classificação, direção, elenco principal, onde assistir). Descubra os ids com search_titles."""
    ctx = get_ctx(config)
    ids = list(dict.fromkeys(title_ids))[:3]
    if len(ids) < 2:
        return {"error": 400, "message": "Preciso de pelo menos dois títulos para comparar."}

    async def load(api, tid: int) -> dict[str, Any]:
        detail = await api.get(f"/titles/{tid}")
        try:
            summary = await api.get(f"/titles/{tid}/reviews/summary")
        except MovieHubError:
            summary = None
        return {"detail": detail, "summary": summary}

    try:
        async with ctx.client() as api:
            loaded = await asyncio.gather(*(load(api, tid) for tid in ids))
    except MovieHubError as exc:
        return fail(exc)

    await emit_titles(ctx, [x["detail"] for x in loaded], config)
    out = []
    for x in loaded:
        d = x["detail"]
        row = compact(d, overview_chars=300)
        row.update(
            {
                "voteCount": d.get("voteCount"),
                "communityAverage": (x["summary"] or {}).get("average"),
                "communityCount": (x["summary"] or {}).get("count"),
                "directorsOrCreators": [c.get("name") for c in d.get("crew") or [] if c.get("job") in ("Director", "Creator", "Diretor", "Criador")][:3],
                "mainCast": [c.get("name") for c in (d.get("cast") or [])[:4]],
                "whereToWatch": [p.get("name") for p in d.get("providers") or [] if p.get("kind") == "stream"],
            }
        )
        out.append(row)
    return {"comparison": out}


@tool
async def group_pick(
    tastes: list[str],
    config: RunnableConfig,
    type: Literal["movie", "series"] | None = "movie",
    max_runtime_minutes: int | None = None,
    max_age_rating: Literal["L", "10", "12", "14", "16", "18"] | None = None,
    limit: int = 5,
) -> dict[str, Any]:
    """Encontra títulos que agradem um GRUPO com gostos diferentes. `tastes` é a lista de gêneros
    preferidos de cada pessoa (ex.: ["Terror", "Comédia", "Ação"]). Prioriza títulos que combinam
    o maior número de gostos e têm nota alta."""
    ctx = get_ctx(config)
    try:
        catalog = items_of(await cached(ctx, "genres", "/genres"))
    except MovieHubError as exc:
        return fail(exc)
    by_norm = {norm(g.get("name", "")): g for g in catalog}
    wanted: list[dict[str, Any]] = []
    for taste in tastes:
        key = norm(taste)
        g = by_norm.get(key) or next((v for k, v in by_norm.items() if key in k or k in key), None)
        if g and g not in wanted:
            wanted.append(g)
    if not wanted:
        return {"error": 404, "message": "Não reconheci nenhum dos gêneros citados.", "available": [g.get("name") for g in catalog]}

    try:
        async with ctx.client() as api:
            pages = await asyncio.gather(
                *(
                    api.get("/titles", genreIds=g["id"], type=type, sort="rating", minRating=6.0,
                            maxAgeRating=max_age_rating, page=1, pageSize=40)
                    for g in wanted
                )
            )
    except MovieHubError as exc:
        return fail(exc)

    wanted_names = {norm(g["name"]) for g in wanted}
    candidates: dict[int, dict[str, Any]] = {}
    for page in pages:
        for item in items_of(page):
            if max_runtime_minutes and (item.get("runtimeMinutes") or 0) > max_runtime_minutes:
                continue
            candidates[item["id"]] = item

    def score(item: dict[str, Any]) -> tuple[int, float]:
        names = {norm(g.get("name") if isinstance(g, dict) else g) for g in item.get("genres") or []}
        return (len(names & wanted_names), float(item.get("voteAverage") or 0))

    ranked = sorted(candidates.values(), key=score, reverse=True)[: max(1, min(limit, 10))]
    await emit_titles(ctx, ranked, config)
    return {
        "matchedGenres": [g["name"] for g in wanted],
        "results": [dict(compact(i), matches=score(i)[0]) for i in ranked],
    }


FUN_TOOLS = [plan_marathon, compare_titles, group_pick]
