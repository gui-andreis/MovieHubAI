# tools/moviehub_tools.py
from langchain_core.tools import tool
from clients.moviehub_client import MovieHubClient, MovieHubAPIError
import httpx


def _error_response(message: str) -> dict:
    """Formato padrão de erro que o responder consegue interpretar."""
    return {"error": True, "message": message}


@tool
async def search_movies(
    title: str | None = None,
    release_year: int | None = None,
    genre_ids: list[int] | None = None,
    min_rating: float | None = None,
    max_rating: float | None = None,
    order_by: str | None = None,
    page_number: int = 1,
    page_size: int = 5,
) -> dict:
    """
    Busca filmes no MovieHub com filtros opcionais.
    Use para responder perguntas como:
    - "quero ver filmes de terror"
    - "filmes do anos 90 com nota acima de 8"
    - "tem algum filme do Nolan?"
    Todos os parâmetros são opcionais — combine os que forem relevantes.
    order_by aceita: title, title_desc, year, year_desc.
    """
    params = {
        k: v for k, v in {
            "title":       title,
            "releaseYear": release_year,
            "genreIds":    genre_ids,
            "minRating":   min_rating,
            "maxRating":   max_rating,
            "orderBy":     order_by,
            "pageNumber":  page_number,
            "pageSize":    page_size,
        }.items()
        if v is not None
    }

    try:
        async with MovieHubClient() as client:
            return await client.get_movies(**params)
    except MovieHubAPIError as e:
        return _error_response(f"Erro ao buscar filmes: {e.message}")
    except httpx.ConnectError:
        return _error_response("Não foi possível conectar ao MovieHub.")
    except httpx.TimeoutException:
        return _error_response("O MovieHub demorou demais para responder.")


@tool
async def get_movie_details(movie_id: int) -> dict:
    """
    Retorna detalhes completos de um filme específico pelo ID.
    Use quando o usuário perguntar sobre um filme específico
    ou quando precisar de mais informações após um search_movies.
    """
    try:
        async with MovieHubClient() as client:
            return await client.get_movie(movie_id)
    except MovieHubAPIError as e:
        if e.status_code == 404:
            return _error_response(f"Filme com id {movie_id} não encontrado no MovieHub.")
        return _error_response(f"Erro ao buscar detalhes do filme: {e.message}")
    except httpx.ConnectError:
        return _error_response("Não foi possível conectar ao MovieHub.")
    except httpx.TimeoutException:
        return _error_response("O MovieHub demorou demais para responder.")


@tool
async def list_genres() -> dict:
    """
    Lista todos os gêneros disponíveis no MovieHub com seus IDs.
    Use ANTES de search_movies quando o usuário mencionar um gênero por nome
    (ex: "terror", "comédia") para descobrir o ID correto antes de filtrar.
    """
    try:
        async with MovieHubClient() as client:
            return await client.get_genres()
    except MovieHubAPIError as e:
        return _error_response(f"Erro ao listar gêneros: {e.message}")
    except httpx.ConnectError:
        return _error_response("Não foi possível conectar ao MovieHub.")
    except httpx.TimeoutException:
        return _error_response("O MovieHub demorou demais para responder.")


@tool
async def get_movie_reviews(movie_id: int) -> dict:
    """
    Retorna as reviews de um filme específico.
    Use quando o usuário quiser saber a opinião de outros usuários
    sobre um filme, ou pedir para ver avaliações.
    """
    try:
        async with MovieHubClient() as client:
            return await client.get_movie_reviews(movie_id)
    except MovieHubAPIError as e:
        if e.status_code == 404:
            return _error_response(f"Filme com id {movie_id} não encontrado.")
        return _error_response(f"Erro ao buscar reviews: {e.message}")
    except httpx.ConnectError:
        return _error_response("Não foi possível conectar ao MovieHub.")
    except httpx.TimeoutException:
        return _error_response("O MovieHub demorou demais para responder.")