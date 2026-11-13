"""Histórico de conversa por sessão.

Redis (inclui `rediss://` do Upstash) quando configurado e disponível; caso
contrário — ou se o Redis cair no meio do caminho — usa memória local.
Guarda só mensagens de texto user/assistant (nunca ToolMessages órfãs, que
quebravam a v1 com erro 400 da OpenAI).
"""
from __future__ import annotations

import json
import logging
import time
from collections import OrderedDict
from typing import Any, Protocol

logger = logging.getLogger("moviehub-ai.memory")

Message = dict[str, str]  # {"role": "user"|"assistant", "content": "..."}


def session_key(session_id: str, profile_id: str | None) -> str:
    return f"moviehub-ai:chat:{profile_id or 'anon'}:{session_id}"


class ChatMemory(Protocol):
    backend: str

    async def load(self, key: str) -> list[Message]: ...
    async def append(self, key: str, messages: list[Message]) -> None: ...
    async def clear(self, key: str) -> None: ...
    async def close(self) -> None: ...


class InMemoryChatMemory:
    backend = "memory"

    def __init__(self, max_messages: int = 20, ttl_seconds: int = 86400, max_sessions: int = 5000):
        self.max_messages = max_messages
        self.ttl = ttl_seconds
        self.max_sessions = max_sessions
        self._data: OrderedDict[str, tuple[float, list[Message]]] = OrderedDict()

    async def load(self, key: str) -> list[Message]:
        item = self._data.get(key)
        if not item:
            return []
        ts, messages = item
        if time.monotonic() - ts > self.ttl:
            self._data.pop(key, None)
            return []
        return list(messages)

    async def append(self, key: str, messages: list[Message]) -> None:
        current = await self.load(key)
        current.extend(messages)
        self._data[key] = (time.monotonic(), current[-self.max_messages:])
        self._data.move_to_end(key)
        while len(self._data) > self.max_sessions:
            self._data.popitem(last=False)

    async def clear(self, key: str) -> None:
        self._data.pop(key, None)

    async def close(self) -> None:
        return None


class RedisChatMemory:
    backend = "redis"

    def __init__(self, client: Any, max_messages: int = 20, ttl_seconds: int = 86400):
        self.client = client
        self.max_messages = max_messages
        self.ttl = ttl_seconds
        self.fallback = InMemoryChatMemory(max_messages, ttl_seconds)

    async def load(self, key: str) -> list[Message]:
        try:
            raw = await self.client.lrange(key, -self.max_messages, -1)
            return [json.loads(r) for r in raw]
        except Exception as exc:  # noqa: BLE001
            logger.warning("Redis indisponível no load (%s); usando memória local", exc)
            return await self.fallback.load(key)

    async def append(self, key: str, messages: list[Message]) -> None:
        if not messages:
            return
        try:
            pipe = self.client.pipeline()
            pipe.rpush(key, *[json.dumps(m, ensure_ascii=False) for m in messages])
            pipe.ltrim(key, -self.max_messages, -1)
            pipe.expire(key, self.ttl)
            await pipe.execute()
        except Exception as exc:  # noqa: BLE001
            logger.warning("Redis indisponível no append (%s); usando memória local", exc)
            await self.fallback.append(key, messages)

    async def clear(self, key: str) -> None:
        await self.fallback.clear(key)
        try:
            await self.client.delete(key)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Redis indisponível no clear (%s)", exc)

    async def close(self) -> None:
        try:
            await self.client.aclose()
        except Exception:  # noqa: BLE001
            pass


async def create_memory(redis_url: str, *, max_messages: int, ttl_seconds: int) -> ChatMemory:
    if redis_url:
        try:
            import redis.asyncio as aioredis

            client = aioredis.from_url(
                redis_url, decode_responses=True, socket_connect_timeout=3, socket_timeout=3,
                health_check_interval=30,
            )
            await client.ping()
            logger.info("Memória de conversa: Redis conectado")
            return RedisChatMemory(client, max_messages, ttl_seconds)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Não foi possível conectar ao Redis (%s); usando memória local", exc)
    else:
        logger.info("REDIS_URL vazio; usando memória local")
    return InMemoryChatMemory(max_messages, ttl_seconds)
