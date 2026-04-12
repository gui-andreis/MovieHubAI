# tools/recommendation_tools.py
from langchain_core.tools import tool
from clients.moviehub_client import MovieHubClient, MovieHubAPIError
import httpx


def _error_response(message: str) -> dict:
    return {"error": True, "message": message}


@tool
async def get_recommendations(
    genre_ids: list[int] | None = None,
    min_rating: float | None = None,
    order_by: str = "year_desc",
    page_size: int = 5,
) -> dict:
    """
    Retorna recomendações de filmes do MovieHub.
    Use quando o usuário pedir sugestões, recomendações ou
    não souber o que assistir. Exemplos:
    - "me recomenda algo bom"
    - "quero uma sugestão de comédia"
    - "o que tem de melhor pra assistir?"
    Prioriza filmes recentes e bem avaliados por padrão.
    Se o usuário mencionar um gênero, descubra o ID com list_genres antes.
    """
    params = {
        k: v for k, v in {
            "minRating": min_rating,
            "genreIds":  genre_ids,
            "orderBy":   order_by,
            "pageSize":  page_size,
        }.items()
        if v is not None
    }

    try:
        async with MovieHubClient() as client:
            return await client.get_movies(**params)
    except MovieHubAPIError as e:
        return _error_response(f"Erro ao buscar recomendações: {e.message}")
    except httpx.ConnectError:
        return _error_response("Não foi possível conectar ao MovieHub.")
    except httpx.TimeoutException:
        return _error_response("O MovieHub demorou demais para responder.")