"""Orquestra uma rodada de conversa e a traduz para o protocolo SSE do contrato.

Eventos emitidos (nome, payload):
    token  {"text": "..."}
    tool   {"name", "status": "start"|"end", "label"}
    titles [TitleCard, ...]
    action Action
    done   {"reply", "sessionId", "titles", "actions", "suggestions"}
    error  {"message"}
"""
from __future__ import annotations

import hashlib
import logging
import re
import time
from typing import Any, AsyncIterator

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage

from app.agent.context import ChatContext
from app.agent.graph import AGENT_NODE, build_graph
from app.agent.tools import SILENT_TOOLS, TOOL_LABELS
from app.clients.moviehub import MovieHubClient, MovieHubError
from app.config import Settings
from app.memory.store import ChatMemory, session_key

logger = logging.getLogger("moviehub-ai.chat")

Event = tuple[str, Any]

_PROFILE_CACHE: dict[str, tuple[float, dict[str, Any] | None]] = {}
_PROFILE_TTL = 300.0


class ChatUnavailable(Exception):
    """O serviço não consegue responder (ex.: sem chave da OpenAI)."""


def _text_of(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(
            part.get("text", "") if isinstance(part, dict) else str(part)
            for part in content
            if not isinstance(part, dict) or part.get("type") in (None, "text")
        )
    return ""


def friendly_error(exc: BaseException) -> tuple[int, str]:
    """Mapeia exceções para (status HTTP, mensagem amigável)."""
    if isinstance(exc, ChatUnavailable):
        return 503, str(exc)
    try:
        import openai

        if isinstance(exc, openai.AuthenticationError):
            return 502, "A chave da OpenAI é inválida ou expirou. Verifique OPENAI_API_KEY."
        if isinstance(exc, openai.RateLimitError):
            return 503, "O limite/cota da OpenAI foi atingido. Tente de novo em instantes."
        if isinstance(exc, (openai.APIConnectionError, openai.APITimeoutError)):
            return 503, "Não consegui falar com a OpenAI agora. Tente de novo em instantes."
        if isinstance(exc, openai.BadRequestError):
            return 502, "A OpenAI recusou a requisição. Tente reformular a mensagem."
        if isinstance(exc, openai.OpenAIError):
            return 502, "Erro ao falar com a OpenAI."
    except ImportError:  # pragma: no cover
        pass
    try:
        from langgraph.errors import GraphRecursionError

        if isinstance(exc, GraphRecursionError):
            return 500, "Me enrolei pensando demais nessa. Pode reformular a pergunta?"
    except ImportError:  # pragma: no cover
        pass
    return 500, "Tive um problema inesperado. Tente novamente."


def _memory_note(ctx: ChatContext) -> str:
    if not ctx.titles:
        return ""
    refs = "; ".join(
        f"{c.get('name')} (id {c.get('id')}, {'série' if c.get('type') == 'series' else 'filme'})"
        for c in list(ctx.titles.values())[:12]
    )
    return f"\n\n[contexto interno — títulos mostrados nesta resposta: {refs}]"


_LEAKED_TOOL_CALL = re.compile(r"^[ \t]*`?(?:functions\.)?(?:suggest_followups|refresh_view|show_toast)\b.*$\n?", re.MULTILINE)
_INLINE_SUGGESTIONS = re.compile(r"\n*\s*\[\s*sugest(?:ões|oes)\s*:\s*(.+?)\]\s*$", re.IGNORECASE | re.DOTALL)


def _extract_inline_suggestions(reply: str, ctx: ChatContext) -> str:
    """Rede de segurança: se o modelo escrever '[sugestões: "a", "b"]' no texto em vez de
    chamar suggest_followups, move isso para ctx.suggestions e limpa a resposta."""
    # o modelo às vezes "escreve" a chamada da tool em vez de chamá-la (ex.: "functions.suggest_followups")
    reply = _LEAKED_TOOL_CALL.sub("", reply).rstrip()
    match = _INLINE_SUGGESTIONS.search(reply)
    if not match:
        return reply
    if not ctx.suggestions:
        parts = re.findall(r'"([^"]+)"', match.group(1)) or match.group(1).split(",")
        ctx.suggestions = [p.strip()[:60] for p in parts if p.strip()][:4]
    return reply[: match.start()].rstrip()


def _default_suggestions(ctx: ChatContext) -> list[str]:
    if ctx.suggestions:
        return ctx.suggestions
    if ctx.titles:
        return ["Me conta mais sobre o primeiro", "Quero algo parecido", "Tem algo mais curto?"]
    return ["O que está em alta hoje?", "Me surpreenda", "Quero algo leve pra hoje"]


class ChatService:
    def __init__(
        self,
        settings: Settings,
        memory: ChatMemory,
        llm: BaseChatModel | None = None,
    ):
        self.settings = settings
        self.memory = memory
        self._llm = llm
        self._graph = None

    # ------------------------------------------------------------- setup ----
    def _get_graph(self):
        if self._graph is None:
            llm = self._llm
            if llm is None:
                if not self.settings.openai_api_key:
                    raise ChatUnavailable(
                        "O assistente está sem chave da OpenAI configurada (OPENAI_API_KEY)."
                    )
                from langchain_openai import ChatOpenAI

                llm = ChatOpenAI(
                    model=self.settings.openai_model,
                    api_key=self.settings.openai_api_key,
                    temperature=self.settings.openai_temperature,
                    timeout=self.settings.openai_timeout_seconds,
                    max_retries=2,
                    streaming=True,
                )
            self._graph = build_graph(llm, max_iterations=self.settings.max_tool_iterations)
        return self._graph

    async def _load_profile(self, ctx: ChatContext) -> None:
        if not ctx.has_profile:
            return
        cache_key = hashlib.sha256(f"{ctx.authorization}|{ctx.profile_id}".encode()).hexdigest()
        hit = _PROFILE_CACHE.get(cache_key)
        if hit and time.monotonic() - hit[0] < _PROFILE_TTL:
            ctx.profile = hit[1]
            return
        profile = None
        try:
            async with MovieHubClient(ctx.authorization, ctx.profile_id) as api:
                profiles = await api.get("/profiles")
            items = profiles if isinstance(profiles, list) else (profiles or {}).get("items", [])
            profile = next((p for p in items if str(p.get("id")) == str(ctx.profile_id)), None)
        except MovieHubError as exc:
            logger.info("Não consegui carregar o perfil (%s)", exc)
        ctx.profile = profile
        _PROFILE_CACHE[cache_key] = (time.monotonic(), profile)

    @staticmethod
    def _to_messages(history: list[dict[str, str]]) -> list[BaseMessage]:
        out: list[BaseMessage] = []
        for m in history:
            if m.get("role") == "user":
                out.append(HumanMessage(content=m.get("content", "")))
            elif m.get("role") == "assistant":
                out.append(AIMessage(content=m.get("content", "")))
        return out

    # --------------------------------------------------------------- run ----
    async def stream(
        self,
        message: str,
        session_id: str,
        *,
        authorization: str | None = None,
        profile_id: str | None = None,
    ) -> AsyncIterator[Event]:
        ctx = ChatContext(
            session_id=session_id,
            authorization=authorization if authorization and authorization.lower().startswith("bearer ") else None,
            profile_id=profile_id or None,
        )
        key = session_key(session_id, ctx.profile_id if ctx.authorization else None)

        try:
            graph = self._get_graph()
            await self._load_profile(ctx)
            history = await self.memory.load(key)
            inputs = {
                "messages": [*self._to_messages(history), HumanMessage(content=message)],
                "iterations": 0,
            }
            config = {
                "configurable": {"ctx": ctx},
                "recursion_limit": self.settings.max_tool_iterations * 2 + 6,
            }

            streamed: list[str] = []
            final_text = ""
            async for ev in graph.astream_events(inputs, config=config, version="v2"):
                kind = ev["event"]
                node = (ev.get("metadata") or {}).get("langgraph_node")

                if kind == "on_chat_model_stream" and node == AGENT_NODE:
                    text = _text_of(getattr(ev["data"].get("chunk"), "content", ""))
                    if text:
                        streamed.append(text)
                        yield "token", {"text": text}

                elif kind == "on_chat_model_end" and node == AGENT_NODE:
                    output = ev["data"].get("output")
                    if isinstance(output, AIMessage) and not output.tool_calls:
                        final_text = _text_of(output.content)

                elif kind == "on_tool_start" and ev["name"] not in SILENT_TOOLS:
                    yield "tool", {
                        "name": ev["name"],
                        "status": "start",
                        "label": TOOL_LABELS.get(ev["name"], "Trabalhando nisso…"),
                    }

                elif kind == "on_tool_end" and ev["name"] not in SILENT_TOOLS:
                    yield "tool", {
                        "name": ev["name"],
                        "status": "end",
                        "label": TOOL_LABELS.get(ev["name"], "Trabalhando nisso…"),
                    }

                elif kind == "on_custom_event" and ev["name"] in ("titles", "action"):
                    yield ev["name"], ev["data"]

            reply = _extract_inline_suggestions(final_text or "".join(streamed).strip(), ctx)
            if not reply:
                reply = "Hmm, não consegui formular uma resposta. Pode tentar de outro jeito?"
            if not streamed:
                # modelo sem streaming (ou fake em testes): manda tudo de uma vez
                yield "token", {"text": reply}

            await self.memory.append(
                key,
                [
                    {"role": "user", "content": message},
                    {"role": "assistant", "content": reply + _memory_note(ctx)},
                ],
            )

            yield "done", {
                "reply": reply,
                "sessionId": session_id,
                "titles": list(ctx.titles.values()),
                "actions": ctx.actions,
                "suggestions": _default_suggestions(ctx),
            }
        except Exception as exc:  # noqa: BLE001
            status, msg = friendly_error(exc)
            # traceback só para erros inesperados; problemas de config/OpenAI viram warning
            log = logger.exception if status == 500 else logger.warning
            log("Falha no chat (session=%s): %s", session_id, exc)
            yield "error", {"message": msg, "status": status}

    async def run(self, message: str, session_id: str, **kwargs: Any) -> dict[str, Any]:
        """Versão não-streaming: consome o stream e devolve o payload de `done`."""
        async for name, data in self.stream(message, session_id, **kwargs):
            if name == "done":
                return data
            if name == "error":
                raise ChatError(data["status"], data["message"])
        raise ChatError(500, "A conversa terminou sem resposta.")

    async def clear(self, session_id: str, profile_id: str | None, authorization: str | None) -> None:
        await self.memory.clear(session_key(session_id, profile_id if authorization else None))


class ChatError(Exception):
    def __init__(self, status: int, message: str):
        self.status = status
        self.message = message
        super().__init__(message)
