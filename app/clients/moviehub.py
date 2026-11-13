"""Cliente HTTP assíncrono para a MovieHub API.

- Repassa `Authorization` e `X-Profile-Id` recebidos do front.
- Desembrulha o envelope `{status, message, data}` e devolve só `data`.
- Converte falhas em `MovieHubError` com mensagem amigável em português.
"""
from __future__ import annotations

from typing import Any

import httpx

from app.config import get_settings


class MovieHubError(Exception):
    """Erro tipado vindo da MovieHub API (ou da comunicação com ela)."""

    def __init__(self, status_code: int, message: str, *, detail: str | None = None):
        self.status_code = status_code
        self.message = message
        self.detail = detail
        super().__init__(f"[{status_code}] {message}")

    @property
    def friendly(self) -> str:
        return self.message


_FRIENDLY: dict[int, str] = {
    400: "Pedido inválido para o MovieHub.",
    401: "Você precisa estar logado (ou sua sessão expirou). Faça login novamente.",
    403: "Esse perfil não tem permissão para isso.",
    404: "Não encontrei isso no catálogo do MovieHub.",
    409: "Isso já foi feito antes (conflito).",
    429: "Muitas requisições ao MovieHub, tente de novo em instantes.",
}


def _clean_params(params: dict[str, Any] | None) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in (params or {}).items():
        if value is None or value == "" or value == []:
            continue
        if isinstance(value, (list, tuple, set)):
            value = ",".join(str(v) for v in value)
        elif isinstance(value, bool):
            value = str(value).lower()
        out[key] = value
    return out


class MovieHubClient:
    def __init__(
        self,
        authorization: str | None = None,
        profile_id: str | None = None,
        *,
        base_url: str | None = None,
        timeout: float | None = None,
    ):
        settings = get_settings()
        headers = {"Accept": "application/json"}
        if authorization:
            headers["Authorization"] = authorization
        if profile_id:
            headers["X-Profile-Id"] = profile_id
        self._client = httpx.AsyncClient(
            base_url=base_url or settings.api_base,
            headers=headers,
            timeout=timeout or settings.moviehub_timeout_seconds,
        )
        self.is_authenticated = bool(authorization)
        self.has_profile = bool(profile_id)

    async def __aenter__(self) -> "MovieHubClient":
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        await self._client.aclose()

    async def request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json: Any = None,
    ) -> Any:
        try:
            response = await self._client.request(
                method, f"/api{path}", params=_clean_params(params), json=json
            )
        except httpx.TimeoutException as exc:
            raise MovieHubError(504, "O MovieHub demorou demais para responder.") from exc
        except httpx.HTTPError as exc:
            raise MovieHubError(503, "Não consegui me conectar ao MovieHub agora.") from exc

        body: Any = None
        if response.content:
            try:
                body = response.json()
            except ValueError:
                body = None

        if response.status_code >= 400:
            api_message = body.get("message") if isinstance(body, dict) else None
            friendly = _FRIENDLY.get(response.status_code)
            if friendly is None:
                friendly = (
                    "O MovieHub teve um problema interno."
                    if response.status_code >= 500
                    else "O MovieHub recusou o pedido."
                )
            # Para 400/404/409 a mensagem da API costuma ser mais útil.
            message = api_message if api_message and response.status_code in (400, 404, 409) else friendly
            raise MovieHubError(response.status_code, message, detail=api_message)

        if isinstance(body, dict) and "data" in body and "status" in body:
            return body["data"]
        return body

    async def get(self, path: str, **params: Any) -> Any:
        return await self.request("GET", path, params=params)

    async def post(self, path: str, json: Any = None, **params: Any) -> Any:
        return await self.request("POST", path, json=json, params=params)

    async def put(self, path: str, json: Any = None) -> Any:
        return await self.request("PUT", path, json=json)

    async def delete(self, path: str) -> Any:
        return await self.request("DELETE", path)
