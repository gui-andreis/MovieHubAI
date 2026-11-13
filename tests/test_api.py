import json
from typing import Any

import httpx
import openai
import pytest
import respx
from langchain_core.messages import AIMessage

from app.agent.prompts import build_system_prompt
from app.agent.context import ChatContext
from app.config import Settings
from app.main import create_app
from app.memory.store import InMemoryChatMemory, session_key
from tests.conftest import API, PROFILE, TOKEN, FakeToolModel, card, env


def settings(**kw: Any) -> Settings:
    base = dict(openai_api_key="", moviehub_api_url="http://api.test", redis_url="", rate_limit_per_minute=100, max_tool_iterations=3)
    base.update(kw)
    return Settings(**base)


def parse_sse(text: str) -> list[tuple[str, Any]]:
    events = []
    for block in text.strip().split("\n\n"):
        lines = dict(line.split(": ", 1) for line in block.splitlines() if ": " in line)
        events.append((lines["event"], json.loads(lines["data"])))
    return events


def tool_call(name: str, args: dict[str, Any], id_: str = "call_1") -> AIMessage:
    return AIMessage(content="", tool_calls=[{"name": name, "args": args, "id": id_, "type": "tool_call"}])


async def client_for(app):
    # dispara o lifespan manualmente (ASGITransport não roda startup)
    ctx = app.router.lifespan_context(app)
    await ctx.__aenter__()
    client = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://ai.test")
    return client, ctx


@pytest.fixture
def memory():
    return InMemoryChatMemory()


@respx.mock
async def test_stream_full_flow(memory):
    respx.get(f"{API}/profiles").respond(json=env([{"id": PROFILE, "name": "Gui", "isKids": False, "maturityLimit": "18"}]))
    respx.get(f"{API}/titles").respond(json=env({"items": [card(1, "Hereditário")], "totalCount": 1}))
    llm = FakeToolModel(
        responses=[
            AIMessage(
                content="",
                tool_calls=[
                    {"name": "search_titles", "args": {"query": "hereditario"}, "id": "c1", "type": "tool_call"},
                    {"name": "open_title", "args": {"title_id": 1}, "id": "c2", "type": "tool_call"},
                    {"name": "suggest_followups", "args": {"suggestions": ["Algo parecido"]}, "id": "c3", "type": "tool_call"},
                ],
            ),
            AIMessage(content="Achei **Hereditário** (2020) pra você!"),
        ]
    )
    app = create_app(settings(), llm=llm, memory=memory)
    client, lifespan = await client_for(app)
    try:
        resp = await client.post(
            "/api/chat/stream",
            json={"message": "quero um terror", "sessionId": "abc"},
            headers={"Authorization": TOKEN, "X-Profile-Id": PROFILE},
        )
    finally:
        await client.aclose()
        await lifespan.__aexit__(None, None, None)

    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/event-stream")
    events = parse_sse(resp.text)
    names = [e[0] for e in events]

    assert ("tool", {"name": "search_titles", "status": "start", "label": "Procurando no catálogo…"}) in events
    assert names.index("titles") < names.index("token") < names.index("done")
    assert "suggest_followups" not in json.dumps([e for e in events if e[0] == "tool"])  # tool silenciosa
    titles = next(d for n, d in events if n == "titles")
    assert titles[0]["id"] == 1 and titles[0]["posterUrl"]
    assert ("action", {"type": "open_title", "titleId": 1}) in events

    done = events[-1]
    assert done[0] == "done"
    assert done[1]["reply"] == "Achei **Hereditário** (2020) pra você!"
    assert done[1]["sessionId"] == "abc"
    assert done[1]["actions"] == [{"type": "open_title", "titleId": 1}]
    assert done[1]["suggestions"] == ["Algo parecido"]
    assert [t["id"] for t in done[1]["titles"]] == [1]

    # histórico salvo por perfil, com nota interna dos ids mostrados
    saved = await memory.load(session_key("abc", PROFILE))
    assert saved[0] == {"role": "user", "content": "quero um terror"}
    assert "id 1" in saved[1]["content"]


@respx.mock
async def test_non_stream_endpoint_and_history(memory):
    llm = FakeToolModel(responses=[AIMessage(content="Oi! Bora achar um filme?")])
    app = create_app(settings(), llm=llm, memory=memory)
    client, lifespan = await client_for(app)
    try:
        r1 = await client.post("/api/chat", json={"message": "oi", "sessionId": "s"})
        r2 = await client.post("/api/chat", json={"message": "tudo bem?", "session_id": "s"})
        cleared = await client.delete("/api/chat/s")
    finally:
        await client.aclose()
        await lifespan.__aexit__(None, None, None)

    assert r1.status_code == 200
    body = r1.json()
    assert body["reply"] == "Oi! Bora achar um filme?"
    assert body["sessionId"] == "s"
    assert body["titles"] == [] and body["actions"] == []
    assert len(body["suggestions"]) >= 2
    assert r2.status_code == 200
    assert cleared.status_code == 204
    assert await memory.load(session_key("s", None)) == []


async def test_missing_openai_key_is_clean_error(memory):
    app = create_app(settings(openai_api_key=""), memory=memory)
    client, lifespan = await client_for(app)
    try:
        r = await client.post("/api/chat", json={"message": "oi", "sessionId": "s"})
        s = await client.post("/api/chat/stream", json={"message": "oi", "sessionId": "s"})
        health = await client.get("/health")
    finally:
        await client.aclose()
        await lifespan.__aexit__(None, None, None)

    assert r.status_code == 503
    assert "OPENAI_API_KEY" in r.json()["message"]
    events = parse_sse(s.text)
    assert events == [("error", {"message": r.json()["message"], "status": 503})]
    assert health.json() == {"status": "ok"}


class ExplodingModel(FakeToolModel):
    async def _agenerate(self, *args, **kwargs):
        request = httpx.Request("POST", "https://api.openai.com/v1/chat/completions")
        raise openai.AuthenticationError("bad key", response=httpx.Response(401, request=request), body=None)


async def test_openai_auth_error_surfaces_as_error_event(memory):
    app = create_app(settings(), llm=ExplodingModel(responses=[AIMessage(content="x")]), memory=memory)
    client, lifespan = await client_for(app)
    try:
        s = await client.post("/api/chat/stream", json={"message": "oi", "sessionId": "s"})
        r = await client.post("/api/chat", json={"message": "oi", "sessionId": "s"})
    finally:
        await client.aclose()
        await lifespan.__aexit__(None, None, None)
    name, data = parse_sse(s.text)[-1]
    assert name == "error" and "chave da OpenAI" in data["message"]
    assert r.status_code == 502


@respx.mock
async def test_iteration_limit_forces_final_answer(memory):
    respx.get(f"{API}/titles/trending").respond(json=env([card(1, "A")]))
    llm = FakeToolModel(
        responses=[tool_call("get_trending", {}, "c1"), tool_call("get_trending", {}, "c2"), AIMessage(content="Resposta final.")]
    )
    app = create_app(settings(max_tool_iterations=2), llm=llm, memory=memory)
    client, lifespan = await client_for(app)
    try:
        r = await client.post("/api/chat", json={"message": "em alta?", "sessionId": "s"})
    finally:
        await client.aclose()
        await lifespan.__aexit__(None, None, None)
    assert r.status_code == 200
    assert r.json()["reply"] == "Resposta final."


async def test_rate_limit(memory):
    llm = FakeToolModel(responses=[AIMessage(content="ok")])
    app = create_app(settings(rate_limit_per_minute=2), llm=llm, memory=memory)
    client, lifespan = await client_for(app)
    try:
        codes = [(await client.post("/api/chat", json={"message": "oi", "sessionId": "rl"})).status_code for _ in range(3)]
    finally:
        await client.aclose()
        await lifespan.__aexit__(None, None, None)
    assert codes == [200, 200, 429]


async def test_validation_error(memory):
    app = create_app(settings(), llm=FakeToolModel(responses=[AIMessage(content="ok")]), memory=memory)
    client, lifespan = await client_for(app)
    try:
        r = await client.post("/api/chat", json={"message": "", "sessionId": "s s"})
    finally:
        await client.aclose()
        await lifespan.__aexit__(None, None, None)
    assert r.status_code == 422
    assert r.json()["message"] == "Requisição inválida."


def test_kids_prompt_restricts_content():
    kids = ChatContext(session_id="s", authorization=TOKEN, profile_id=PROFILE, profile={"name": "Bia", "isKids": True})
    prompt = build_system_prompt(kids)
    assert "PERFIL INFANTIL" in prompt and "Bia" in prompt
    anon = build_system_prompt(ChatContext(session_id="s"))
    assert "Visitante não logado" in anon


async def test_memory_trims_and_namespaces():
    mem = InMemoryChatMemory(max_messages=3)
    await mem.append("k", [{"role": "user", "content": str(i)} for i in range(5)])
    assert [m["content"] for m in await mem.load("k")] == ["2", "3", "4"]
    assert session_key("s", None) != session_key("s", PROFILE)
