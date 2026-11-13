"""Tools pessoais (exigem login + perfil selecionado)."""
from __future__ import annotations

from typing import Any, Literal

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool

from app.agent.context import compact, emit_action, emit_titles, get_ctx
from app.agent.tools._common import LOGIN_REQUIRED, fail, items_of
from app.clients.moviehub import MovieHubError


def _guard(config: RunnableConfig):
    ctx = get_ctx(config)
    return ctx, (None if ctx.has_profile else dict(LOGIN_REQUIRED))


async def _title_name(ctx, title_id: int) -> str | None:
    card = ctx.titles.get(title_id)
    if card:
        return card.get("name")
    try:
        async with ctx.client() as api:
            detail = await api.get(f"/titles/{title_id}")
        return detail.get("name")
    except MovieHubError:
        return None


@tool
async def get_my_list(config: RunnableConfig) -> dict[str, Any]:
    """Títulos na "Minha Lista" do perfil atual."""
    ctx, err = _guard(config)
    if err:
        return err
    try:
        async with ctx.client() as api:
            data = await api.get("/me/list")
    except MovieHubError as exc:
        return fail(exc)
    items = items_of(data)
    await emit_titles(ctx, items[:12], config)
    return {"count": len(items), "results": [compact(i, overview_chars=0) for i in items[:30]]}


@tool
async def add_to_my_list(title_id: int, config: RunnableConfig) -> dict[str, Any]:
    """Adiciona um título à "Minha Lista" do perfil. Descubra o id com search_titles se preciso."""
    ctx, err = _guard(config)
    if err:
        return err
    try:
        async with ctx.client() as api:
            await api.put(f"/me/list/{title_id}")
    except MovieHubError as exc:
        if exc.status_code == 409:
            return {"ok": True, "message": "Já estava na Minha Lista."}
        return fail(exc)
    name = await _title_name(ctx, title_id) or "Título"
    await emit_action(ctx, {"type": "refresh", "target": "my-list"}, config)
    await emit_action(ctx, {"type": "toast", "message": f"{name} adicionado à Minha Lista"}, config)
    return {"ok": True, "message": f"{name} adicionado à Minha Lista."}


@tool
async def remove_from_my_list(title_id: int, config: RunnableConfig) -> dict[str, Any]:
    """Remove um título da "Minha Lista" do perfil."""
    ctx, err = _guard(config)
    if err:
        return err
    try:
        async with ctx.client() as api:
            await api.delete(f"/me/list/{title_id}")
    except MovieHubError as exc:
        if exc.status_code == 404:
            return {"ok": True, "message": "Esse título não estava na Minha Lista."}
        return fail(exc)
    name = await _title_name(ctx, title_id) or "Título"
    await emit_action(ctx, {"type": "refresh", "target": "my-list"}, config)
    await emit_action(ctx, {"type": "toast", "message": f"{name} removido da Minha Lista"}, config)
    return {"ok": True, "message": f"{name} removido da Minha Lista."}


_REACTION_LABEL = {"like": "Gostei", "love": "Amei", "dislike": "Não é pra mim"}


@tool
async def react_to_title(
    title_id: int,
    reaction: Literal["like", "love", "dislike", "none"],
    config: RunnableConfig,
) -> dict[str, Any]:
    """Registra a reação do perfil a um título: like (gostei), love (amei), dislike (não é pra mim)
    ou none (remove a reação). Reações melhoram as recomendações da home."""
    ctx, err = _guard(config)
    if err:
        return err
    try:
        async with ctx.client() as api:
            if reaction == "none":
                await api.delete(f"/me/reactions/{title_id}")
            else:
                await api.put(f"/me/reactions/{title_id}", json={"value": reaction})
    except MovieHubError as exc:
        return fail(exc)
    name = await _title_name(ctx, title_id) or "Título"
    msg = f"Reação removida de {name}" if reaction == "none" else f"{_REACTION_LABEL[reaction]}: {name}"
    await emit_action(ctx, {"type": "refresh", "target": "reactions"}, config)
    await emit_action(ctx, {"type": "toast", "message": msg}, config)
    return {"ok": True, "message": msg}


@tool
async def get_continue_watching(config: RunnableConfig) -> dict[str, Any]:
    """O que o perfil começou a assistir e não terminou (com episódio e % de progresso)."""
    ctx, err = _guard(config)
    if err:
        return err
    try:
        async with ctx.client() as api:
            data = await api.get("/me/continue-watching")
    except MovieHubError as exc:
        return fail(exc)
    entries = items_of(data)
    await emit_titles(ctx, [e.get("title") or {} for e in entries[:10]], config)
    return {
        "results": [
            {
                "title": compact(e.get("title") or {}, overview_chars=0),
                "episode": e.get("episode"),
                "percent": e.get("percent"),
                "updatedAt": e.get("updatedAt"),
            }
            for e in entries[:15]
        ]
    }


@tool
async def write_review(
    title_id: int,
    rating: int,
    config: RunnableConfig,
    comment: str | None = None,
    contains_spoilers: bool = False,
) -> dict[str, Any]:
    """Publica (ou atualiza, se já existir) a review do perfil para um título.
    rating é um inteiro de 1 a 10. Só use quando o usuário pedir explicitamente para avaliar;
    confirme a nota se ela não estiver clara."""
    ctx, err = _guard(config)
    if err:
        return err
    if not 1 <= rating <= 10:
        return {"error": 400, "message": "A nota precisa ser um número inteiro de 1 a 10."}
    payload = {"rating": rating, "comment": comment, "containsSpoilers": contains_spoilers}
    updated = False
    try:
        async with ctx.client() as api:
            try:
                await api.post(f"/titles/{title_id}/reviews", json=payload)
            except MovieHubError as exc:
                if exc.status_code != 409:
                    raise
                # já existe review deste perfil -> atualiza
                detail = await api.get(f"/titles/{title_id}")
                review_id = ((detail.get("me") or {}).get("review") or {}).get("id")
                if not review_id:
                    raise
                await api.put(f"/reviews/{review_id}", json=payload)
                updated = True
    except MovieHubError as exc:
        return fail(exc)
    name = await _title_name(ctx, title_id) or "título"
    msg = f"Review de {name} {'atualizada' if updated else 'publicada'} ({rating}/10)"
    await emit_action(ctx, {"type": "refresh", "target": "reviews"}, config)
    await emit_action(ctx, {"type": "toast", "message": msg}, config)
    return {"ok": True, "updated": updated, "message": msg}


@tool
async def get_my_reviews(config: RunnableConfig) -> dict[str, Any]:
    """Reviews já escritas pelo perfil atual."""
    ctx, err = _guard(config)
    if err:
        return err
    try:
        async with ctx.client() as api:
            data = await api.get("/me/reviews")
    except MovieHubError as exc:
        return fail(exc)
    reviews = items_of(data)
    return {
        "count": len(reviews),
        "results": [
            {
                "titleId": r.get("titleId") or (r.get("title") or {}).get("id"),
                "title": r.get("titleName") or (r.get("title") or {}).get("name"),
                "rating": r.get("rating"),
                "comment": (r.get("comment") or "")[:200],
            }
            for r in reviews[:30]
        ],
    }


@tool
async def get_my_stats(config: RunnableConfig) -> dict[str, Any]:
    """Estatísticas do perfil: quantos títulos assistiu, minutos assistidos, gêneros favoritos,
    reviews e tamanho da lista. Ótimo para uma "retrospectiva" divertida."""
    ctx, err = _guard(config)
    if err:
        return err
    try:
        async with ctx.client() as api:
            return await api.get("/me/stats")
    except MovieHubError as exc:
        return fail(exc)


PERSONAL_TOOLS = [
    get_my_list,
    add_to_my_list,
    remove_from_my_list,
    react_to_title,
    get_continue_watching,
    write_review,
    get_my_reviews,
    get_my_stats,
]
