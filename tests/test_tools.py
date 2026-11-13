import httpx
import pytest
import respx

from app.agent.tools.catalog import get_title_details, search_titles
from app.agent.tools.fun import group_pick, plan_marathon
from app.agent.tools.personal import add_to_my_list, get_my_list, react_to_title, write_review
from app.agent.tools.ui import navigate, set_filters
from tests.conftest import API, GENRES, PROFILE, TOKEN, card, cfg, env


@respx.mock
async def test_search_forwards_headers_and_resolves_genres(ctx):
    respx.get(f"{API}/genres").respond(json=env(GENRES))
    route = respx.get(f"{API}/titles").respond(
        json=env({"items": [card(1, "Hereditário"), card(2, "Corra!")], "page": 1, "pageSize": 8, "totalCount": 2, "totalPages": 1})
    )

    result = await search_titles.ainvoke({"genres": ["terror"], "min_rating": 7}, config=cfg(ctx))

    req = route.calls.last.request
    assert req.headers["Authorization"] == TOKEN
    assert req.headers["X-Profile-Id"] == PROFILE
    assert req.url.params["genreIds"] == "27"
    assert req.url.params["minRating"] == "7.0"
    assert req.url.params["sort"] == "popularity"
    assert result["total"] == 2
    assert [r["name"] for r in result["results"]] == ["Hereditário", "Corra!"]
    assert "posterUrl" not in result["results"][0]  # LLM recebe versão enxuta
    assert list(ctx.titles) == [1, 2]  # cards emitidos para o front
    assert ctx.titles[1]["posterUrl"] == "https://img/1.jpg"


@respx.mock
async def test_search_filters_runtime_client_side(anon_ctx):
    respx.get(f"{API}/titles").respond(
        json=env({"items": [card(1, "Longo", runtimeMinutes=180), card(2, "Curto", runtimeMinutes=85)], "totalCount": 2})
    )
    result = await search_titles.ainvoke({"max_runtime_minutes": 90}, config=cfg(anon_ctx))
    assert [r["name"] for r in result["results"]] == ["Curto"]
    assert respx.calls.last.request.url.params["pageSize"] == "50"
    assert "Authorization" not in respx.calls.last.request.headers


@respx.mock
@pytest.mark.parametrize(
    "status,expected",
    [(404, "Título 99 não encontrado."), (500, "O MovieHub teve um problema interno.")],
)
async def test_error_mapping(anon_ctx, status, expected):
    respx.get(f"{API}/titles/99").respond(status, json=env(None, status, "Título 99 não encontrado."))
    result = await get_title_details.ainvoke({"title_id": 99}, config=cfg(anon_ctx))
    assert result == {"error": status, "message": expected}


@respx.mock
async def test_401_becomes_login_required(ctx):
    respx.get(f"{API}/me/list").respond(401, json=env(None, 401, "Unauthorized"))
    result = await get_my_list.ainvoke({}, config=cfg(ctx))
    assert result["error"] == "LOGIN_REQUIRED"


@respx.mock
async def test_connection_and_timeout_errors(anon_ctx):
    respx.get(f"{API}/titles/1").mock(side_effect=httpx.ConnectError("boom"))
    respx.get(f"{API}/titles/2").mock(side_effect=httpx.ReadTimeout("slow"))
    r1 = await get_title_details.ainvoke({"title_id": 1}, config=cfg(anon_ctx))
    r2 = await get_title_details.ainvoke({"title_id": 2}, config=cfg(anon_ctx))
    assert r1 == {"error": 503, "message": "Não consegui me conectar ao MovieHub agora."}
    assert r2 == {"error": 504, "message": "O MovieHub demorou demais para responder."}


@respx.mock
async def test_personal_tools_require_profile(anon_ctx):
    result = await add_to_my_list.ainvoke({"title_id": 1}, config=cfg(anon_ctx))
    assert result["error"] == "LOGIN_REQUIRED"
    assert not respx.calls  # nem chega a chamar a API


@respx.mock
async def test_add_to_my_list_emits_refresh_and_toast(ctx):
    route = respx.put(f"{API}/me/list/7").respond(json=env(None))
    respx.get(f"{API}/titles/7").respond(json=env(card(7, "Duna")))
    result = await add_to_my_list.ainvoke({"title_id": 7}, config=cfg(ctx))
    assert result["ok"] is True
    assert route.calls.last.request.headers["X-Profile-Id"] == PROFILE
    assert ctx.actions == [
        {"type": "refresh", "target": "my-list"},
        {"type": "toast", "message": "Duna adicionado à Minha Lista"},
    ]


@respx.mock
async def test_react_none_deletes(ctx):
    ctx.titles[3] = card(3, "Up")
    route = respx.delete(f"{API}/me/reactions/3").respond(json=env(None))
    await react_to_title.ainvoke({"title_id": 3, "reaction": "none"}, config=cfg(ctx))
    assert route.called


@respx.mock
async def test_write_review_updates_on_conflict(ctx):
    ctx.titles[5] = card(5, "Matrix")
    respx.post(f"{API}/titles/5/reviews").respond(409, json=env(None, 409, "Já existe"))
    respx.get(f"{API}/titles/5").respond(json=env(dict(card(5, "Matrix"), me={"review": {"id": 42}})))
    put = respx.put(f"{API}/reviews/42").respond(json=env(None))
    result = await write_review.ainvoke({"title_id": 5, "rating": 9, "comment": "top"}, config=cfg(ctx))
    assert result["updated"] is True
    assert put.calls.last.request.read() == b'{"rating":9,"comment":"top","containsSpoilers":false}'


async def test_navigate_rejects_external_paths(anon_ctx):
    bad = await navigate.ainvoke({"path": "https://evil.com"}, config=cfg(anon_ctx))
    ok = await navigate.ainvoke({"path": "/title/12"}, config=cfg(anon_ctx))
    assert bad["error"] == 400
    assert ok["ok"] is True
    assert anon_ctx.actions == [{"type": "navigate", "path": "/title/12"}]


@respx.mock
async def test_set_filters_action(anon_ctx):
    respx.get(f"{API}/genres").respond(json=env(GENRES))
    await set_filters.ainvoke({"type": "movie", "genres": ["Terror"], "sort": "rating"}, config=cfg(anon_ctx))
    assert anon_ctx.actions == [
        {"type": "set_filters", "path": "/browse/movies", "query": {"genreIds": "27", "sort": "rating"}}
    ]


@respx.mock
async def test_plan_marathon_series(anon_ctx):
    respx.get(f"{API}/titles/10").respond(
        json=env(card(10, "Dark", type="series", runtimeMinutes=50, seasons=[{"seasonNumber": 1}, {"seasonNumber": 2}]))
    )
    eps = [{"id": i, "episodeNumber": i, "name": f"E{i}", "runtimeMinutes": 50} for i in range(1, 4)]
    respx.get(f"{API}/titles/10/seasons/1").respond(json=env({"seasonNumber": 1, "episodes": eps}))
    respx.get(f"{API}/titles/10/seasons/2").respond(json=env({"seasonNumber": 2, "episodes": eps}))
    result = await plan_marathon.ainvoke({"title_id": 10, "hours_available": 4}, config=cfg(anon_ctx))
    assert result["kind"] == "series"
    assert result["plannedMinutes"] == 200
    assert [(e["season"], e["episode"]) for e in result["episodes"]] == [(1, 1), (1, 2), (1, 3), (2, 1)]
    assert result["fitsEverythingRemaining"] is False


@respx.mock
async def test_group_pick_prefers_titles_matching_more_tastes(anon_ctx):
    respx.get(f"{API}/genres").respond(json=env(GENRES))
    respx.get(f"{API}/titles", params={"genreIds": "27"}).respond(
        json=env({"items": [card(1, "Só terror", voteAverage=9), card(3, "Terror cômico", genres=["Terror", "Comédia"], voteAverage=7)]})
    )
    respx.get(f"{API}/titles", params={"genreIds": "35"}).respond(
        json=env({"items": [card(2, "Só comédia", genres=["Comédia"], voteAverage=8), card(3, "Terror cômico", genres=["Terror", "Comédia"], voteAverage=7)]})
    )
    result = await group_pick.ainvoke({"tastes": ["terror", "comedia"]}, config=cfg(anon_ctx))
    assert result["matchedGenres"] == ["Terror", "Comédia"]
    assert result["results"][0]["name"] == "Terror cômico"
    assert result["results"][0]["matches"] == 2
