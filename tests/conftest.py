# tests/conftest.py
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from dotenv import load_dotenv

load_dotenv()


@pytest.fixture
def mock_moviehub_client():
    mock_instance = AsyncMock()
    mock_instance.get_movies = AsyncMock(return_value={
        "status": 200,
        "message": "Filmes recuperados com sucesso.",
        "data": {
            "items": [
                {
                    "id": 1,
                    "title": "Inception",
                    "releaseYear": 2010,
                    "rating": 9.0,
                    "genres": ["Ficção Científica"]
                }
            ],
            "totalCount": 1,
        }
    })
    mock_instance.get_genres = AsyncMock(return_value={
        "status": 200,
        "data": [
            {"id": 1, "name": "Ficção Científica"},
            {"id": 2, "name": "Terror"},
        ]
    })

    # Mocka o context manager __aenter__ pra retornar o mock_instance
    mock_cm = MagicMock()
    mock_cm.__aenter__ = AsyncMock(return_value=mock_instance)
    mock_cm.__aexit__ = AsyncMock(return_value=None)

    with patch("tools.moviehub_tools.MovieHubClient", return_value=mock_cm):
        yield mock_instance
        
@pytest.fixture
def mock_redis():
    with patch("memory.redis_memory.aioredis.from_url") as mock:
        client = AsyncMock()
        client.get = AsyncMock(return_value=None)
        client.set = AsyncMock(return_value=True)
        client.aclose = AsyncMock()
        mock.return_value = client
        yield client
        
@pytest.fixture
def mock_authenticated_client():
    mock_instance = AsyncMock()
    mock_instance.get_my_favorites = AsyncMock(return_value={
        "status": 200,
        "data": [
            {"id": 1, "title": "Inception", "releaseYear": 2010}
        ]
    })
    mock_instance.add_favorite = AsyncMock(return_value={
        "status": 200,
        "message": "Filme adicionado aos favoritos."
    })
    mock_instance.get_my_reviews = AsyncMock(return_value={
        "status": 200,
        "data": []
    })
    mock_instance.create_review = AsyncMock(return_value={
        "status": 201,
        "message": "Review criada com sucesso."
    })

    mock_cm = MagicMock()
    mock_cm.__aenter__ = AsyncMock(return_value=mock_instance)
    mock_cm.__aexit__ = AsyncMock(return_value=None)

    with patch("tools.authenticated_tools.MovieHubClient", return_value=mock_cm):
        yield mock_instance