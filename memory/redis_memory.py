# memory/redis_memory.py
import json
import redis.asyncio as aioredis
from app.config import settings
from langchain_core.messages import HumanMessage, AIMessage, ToolMessage

MAX_HISTORY = 20
TTL_SECONDS = 60 * 60 * 24  # 24 horas


def _get_client() -> aioredis.Redis:
    return aioredis.from_url(settings.redis_url, decode_responses=True)


def _serialize(messages: list) -> str:
    serialized = []
    for msg in messages:
        if isinstance(msg, HumanMessage):
            serialized.append({"role": "user", "content": msg.content})
        elif isinstance(msg, AIMessage):
            serialized.append({"role": "assistant", "content": msg.content})
        # ToolMessages não persistem — são contexto interno do grafo
    return json.dumps(serialized, ensure_ascii=False)


def _deserialize(raw: str) -> list:
    messages = []
    for item in json.loads(raw):
        if item["role"] == "user":
            messages.append(HumanMessage(content=item["content"]))
        elif item["role"] == "assistant":
            messages.append(AIMessage(content=item["content"]))
    return messages


async def load_history(session_id: str) -> list:
    client = _get_client()
    try:
        raw = await client.get(f"chat:{session_id}")
        if not raw:
            return []
        return _deserialize(raw)
    finally:
        await client.aclose()


async def save_history(session_id: str, messages: list) -> None:
    # Filtra só user e assistant — descarta ToolMessages e AIMessages com tool_calls
    clean = [
        m for m in messages
        if isinstance(m, (HumanMessage, AIMessage))
        and not getattr(m, "tool_calls", None)
    ]

    # Mantém só as últimas MAX_HISTORY mensagens
    clean = clean[-MAX_HISTORY:]

    client = _get_client()
    try:
        await client.set(
            f"chat:{session_id}",
            _serialize(clean),
            ex=TTL_SECONDS,
        )
    finally:
        await client.aclose()