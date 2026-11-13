"""Rotas HTTP do assistente."""
import json
from typing import Annotated, Any, AsyncIterator

from fastapi import APIRouter, Depends, Header, HTTPException, Path, Request
from fastapi.responses import StreamingResponse

from app.api.schemas import ChatRequest, ChatResponse
from app.services.chat import ChatError, ChatService

router = APIRouter(prefix="/api/chat", tags=["chat"])

AuthHeader = Annotated[str | None, Header(alias="Authorization")]
ProfileHeader = Annotated[str | None, Header(alias="X-Profile-Id")]


def get_service(request: Request) -> ChatService:
    return request.app.state.chat_service


def _client_ip(request: Request) -> str:
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def enforce_rate_limit(request: Request, body: ChatRequest) -> None:
    limiter = request.app.state.rate_limiter
    for key in (f"ip:{_client_ip(request)}", f"session:{body.session_id}"):
        allowed, retry = limiter.hit(key)
        if not allowed:
            raise HTTPException(
                status_code=429,
                detail="Calma! Muitas mensagens em pouco tempo. Tente de novo em instantes.",
                headers={"Retry-After": str(retry)},
            )


def sse(event: str, data: Any) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


@router.post("", response_model=ChatResponse, response_model_by_alias=True)
async def chat(
    body: ChatRequest,
    request: Request,
    service: Annotated[ChatService, Depends(get_service)],
    authorization: AuthHeader = None,
    profile_id: ProfileHeader = None,
) -> ChatResponse:
    """Resposta completa de uma vez (sem streaming)."""
    enforce_rate_limit(request, body)
    try:
        data = await service.run(
            body.message, body.session_id, authorization=authorization, profile_id=profile_id
        )
    except ChatError as exc:
        raise HTTPException(status_code=exc.status, detail=exc.message) from exc
    return ChatResponse(
        reply=data["reply"],
        session_id=data["sessionId"],
        titles=data["titles"],
        actions=data["actions"],
        suggestions=data["suggestions"],
    )


@router.post("/stream")
async def chat_stream(
    body: ChatRequest,
    request: Request,
    service: Annotated[ChatService, Depends(get_service)],
    authorization: AuthHeader = None,
    profile_id: ProfileHeader = None,
) -> StreamingResponse:
    """Resposta via Server-Sent Events (token, tool, titles, action, done, error)."""
    enforce_rate_limit(request, body)

    async def events() -> AsyncIterator[str]:
        async for name, data in service.stream(
            body.message, body.session_id, authorization=authorization, profile_id=profile_id
        ):
            if await request.is_disconnected():
                break
            yield sse(name, data)

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache, no-transform", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
    )


@router.delete("/{session_id}", status_code=204)
async def clear_chat(
    service: Annotated[ChatService, Depends(get_service)],
    session_id: Annotated[str, Path(max_length=100, pattern=r"^[A-Za-z0-9_\-:.]+$")],
    authorization: AuthHeader = None,
    profile_id: ProfileHeader = None,
) -> None:
    """Apaga o histórico da sessão (do perfil atual)."""
    await service.clear(session_id, profile_id, authorization)
