# tools/authenticated_tools.py
from langchain_core.tools import tool
from clients.moviehub_client import MovieHubClient, MovieHubAPIError
import httpx


def _error_response(message: str) -> dict:
    return {"error": True, "message": message}


@tool
async def get_my_favorites(user_token: str) -> dict:
    """
    Retorna a lista de filmes favoritos do usuário autenticado.
    Use quando o usuário pedir para ver seus favoritos. Exemplos:
    - "quais são meus filmes favoritos?"
    - "me mostra minha lista de favoritos"
    Requer que o usuário esteja logado.
    """
    try:
        async with MovieHubClient(user_token=user_token) as client:
            return await client.get_my_favorites()
    except MovieHubAPIError as e:
        if e.status_code == 401:
            return _error_response("Sessão expirada. Faça login novamente.")
        return _error_response(f"Erro ao buscar favoritos: {e.message}")
    except httpx.ConnectError:
        return _error_response("Não foi possível conectar ao MovieHub.")
    except httpx.TimeoutException:
        return _error_response("O MovieHub demorou demais para responder.")


@tool
async def add_favorite(user_token: str, movie_id: int) -> dict:
    """
    Adiciona um filme aos favoritos do usuário autenticado.
    Use quando o usuário pedir para favoritar ou salvar um filme. Exemplos:
    - "adiciona Inception nos meus favoritos"
    - "quero salvar esse filme"
    Requer que o usuário esteja logado e que o filme exista no MovieHub.
    """
    try:
        async with MovieHubClient(user_token=user_token) as client:
            return await client.add_favorite(movie_id)
    except MovieHubAPIError as e:
        if e.status_code == 401:
            return _error_response("Sessão expirada. Faça login novamente.")
        if e.status_code == 409:
            return _error_response("Esse filme já está nos seus favoritos.")
        if e.status_code == 404:
            return _error_response("Filme não encontrado no MovieHub.")
        return _error_response(f"Erro ao adicionar favorito: {e.message}")
    except httpx.ConnectError:
        return _error_response("Não foi possível conectar ao MovieHub.")
    except httpx.TimeoutException:
        return _error_response("O MovieHub demorou demais para responder.")


@tool
async def remove_favorite(user_token: str, movie_id: int) -> dict:
    """
    Remove um filme dos favoritos do usuário autenticado.
    Use quando o usuário pedir para desfavoritar ou remover um filme. Exemplos:
    - "remove Inception dos meus favoritos"
    - "não quero mais esse filme na minha lista"
    Requer que o usuário esteja logado.
    """
    try:
        async with MovieHubClient(user_token=user_token) as client:
            return await client.remove_favorite(movie_id)
    except MovieHubAPIError as e:
        if e.status_code == 401:
            return _error_response("Sessão expirada. Faça login novamente.")
        if e.status_code == 404:
            return _error_response("Filme não encontrado nos seus favoritos.")
        return _error_response(f"Erro ao remover favorito: {e.message}")
    except httpx.ConnectError:
        return _error_response("Não foi possível conectar ao MovieHub.")
    except httpx.TimeoutException:
        return _error_response("O MovieHub demorou demais para responder.")


@tool
async def get_my_reviews(user_token: str) -> dict:
    """
    Retorna todas as reviews escritas pelo usuário autenticado.
    Use quando o usuário quiser ver suas próprias avaliações. Exemplos:
    - "quais filmes eu já avaliei?"
    - "me mostra minhas reviews"
    Requer que o usuário esteja logado.
    """
    try:
        async with MovieHubClient(user_token=user_token) as client:
            return await client.get_my_reviews()
    except MovieHubAPIError as e:
        if e.status_code == 401:
            return _error_response("Sessão expirada. Faça login novamente.")
        return _error_response(f"Erro ao buscar reviews: {e.message}")
    except httpx.ConnectError:
        return _error_response("Não foi possível conectar ao MovieHub.")
    except httpx.TimeoutException:
        return _error_response("O MovieHub demorou demais para responder.")


@tool
async def create_review(
    user_token: str,
    movie_id: int,
    rating: float,
    comment: str,
) -> dict:
    """
    Cria uma review para um filme no MovieHub.
    Use quando o usuário quiser avaliar um filme. Exemplos:
    - "quero dar nota 9 pro Inception"
    - "vou avaliar esse filme com 8 e comentar que é ótimo"
    Regras:
    - rating deve ser entre 0 e 10.
    - O usuário só pode ter uma review por filme.
    - Requer que o usuário esteja logado.
    """
    try:
        async with MovieHubClient(user_token=user_token) as client:
            return await client.create_review(movie_id, rating, comment)
    except MovieHubAPIError as e:
        if e.status_code == 401:
            return _error_response("Sessão expirada. Faça login novamente.")
        if e.status_code == 409:
            return _error_response("Você já avaliou esse filme.")
        if e.status_code == 404:
            return _error_response("Filme não encontrado no MovieHub.")
        return _error_response(f"Erro ao criar review: {e.message}")
    except httpx.ConnectError:
        return _error_response("Não foi possível conectar ao MovieHub.")
    except httpx.TimeoutException:
        return _error_response("O MovieHub demorou demais para responder.")