# clients/moviehub_client.py
import httpx
from app.config import settings


class MovieHubAPIError(Exception):
    """Erro retornado pela API do MovieHub."""
    def __init__(self, status_code: int, message: str):
        self.status_code = status_code
        self.message = message
        super().__init__(f"MovieHub API error {status_code}: {message}")


class MovieHubClient:
    def __init__(self, user_token: str | None = None):
        headers = {"Content-Type": "application/json"}

        if user_token:
            headers["Authorization"] = f"Bearer {user_token}"

        self.client = httpx.AsyncClient(
            base_url=settings.moviehub_base_url,
            headers=headers,
            timeout=10.0,
        )

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        await self.client.aclose()

    def _handle_response(self, response: httpx.Response) -> dict:
        """
        Trata a resposta da API de forma centralizada.
        Lança exceções semânticas em vez de deixar estourar aleatoriamente.
        """
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as e:
            # Tenta extrair a mensagem de erro do envelope padrão do MovieHub
            try:
                body = e.response.json()
                message = body.get("message", str(e))
            except Exception:
                message = str(e)
            raise MovieHubAPIError(
                status_code=e.response.status_code,
                message=message,
            )
        return response.json()

    async def get_movies(self, **params) -> dict:
        response = await self.client.get("/api/movies", params=params)
        return self._handle_response(response)

    async def get_movie(self, movie_id: int) -> dict:
        response = await self.client.get(f"/api/movies/{movie_id}")
        return self._handle_response(response)

    async def get_genres(self) -> dict:
        response = await self.client.get("/api/genre")
        return self._handle_response(response)

    async def get_movie_reviews(self, movie_id: int) -> dict:
        response = await self.client.get(f"/api/review/movie/{movie_id}")
        return self._handle_response(response)

    async def get_my_reviews(self) -> dict:
        response = await self.client.get("/api/review/my")
        return self._handle_response(response)

    async def get_my_favorites(self) -> dict:
        response = await self.client.get("/api/favorite/my")
        return self._handle_response(response)

    async def add_favorite(self, movie_id: int) -> dict:
        response = await self.client.post(
            "/api/favorite",
            json={"movieId": movie_id}
        )
        return self._handle_response(response)

    async def remove_favorite(self, movie_id: int) -> dict:
        response = await self.client.delete(f"/api/favorite/{movie_id}")
        return self._handle_response(response)

    async def create_review(self, movie_id: int, rating: float, comment: str) -> dict:
        response = await self.client.post(
            "/api/review",
            json={"movieId": movie_id, "rating": rating, "comment": comment}
        )
        return self._handle_response(response)