import os

# Ambiente isolado: precisa vir antes de importar `app` (settings são cacheadas).
os.environ.update(
    {
        "MOVIEHUB_API_URL": "http://api.test",
        "OPENAI_API_KEY": "",
        "REDIS_URL": "",
        "ALLOWED_ORIGINS": "http://localhost:3000",
        "RATE_LIMIT_PER_MINUTE": "100",
        "ENVIRONMENT": "test",
    }
)

from typing import Any  # noqa: E402

import pytest  # noqa: E402
from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel  # noqa: E402

from app.agent.context import ChatContext  # noqa: E402
from app.agent.tools import _common  # noqa: E402
from app.services import chat as chat_service  # noqa: E402

API = "http://api.test/api"
TOKEN = "Bearer test-token"
PROFILE = "11111111-1111-1111-1111-111111111111"


class FakeToolModel(FakeMessagesListChatModel):
    """Modelo fake que aceita bind_tools e devolve as respostas roteirizadas em ordem."""

    def bind_tools(self, tools: Any, **kwargs: Any):  # noqa: D401
        return self


def env(data: Any, status: int = 200, message: str = "OK") -> dict[str, Any]:
    return {"status": status, "message": message, "data": data}


def card(id_: int, name: str, **extra: Any) -> dict[str, Any]:
    base = {
        "id": id_, "type": "movie", "name": name, "year": 2020, "posterUrl": f"https://img/{id_}.jpg",
        "backdropUrl": None, "logoUrl": None, "ageRating": "14", "voteAverage": 7.5,
        "runtimeMinutes": 110, "numberOfSeasons": None, "genres": ["Terror"],
        "trailerKey": "abc", "overview": "Uma história.",
    }
    base.update(extra)
    return base


GENRES = [
    {"id": 27, "name": "Terror", "slug": "terror", "titleCount": 10},
    {"id": 35, "name": "Comédia", "slug": "comedia", "titleCount": 12},
    {"id": 878, "name": "Ficção científica", "slug": "ficcao-cientifica", "titleCount": 8},
]


@pytest.fixture(autouse=True)
def _clear_caches():
    _common.clear_cache()
    chat_service._PROFILE_CACHE.clear()
    yield


@pytest.fixture
def ctx() -> ChatContext:
    return ChatContext(session_id="s1", authorization=TOKEN, profile_id=PROFILE, profile={"name": "Gui"})


@pytest.fixture
def anon_ctx() -> ChatContext:
    return ChatContext(session_id="s1")


def cfg(c: ChatContext) -> dict[str, Any]:
    return {"configurable": {"ctx": c}}
