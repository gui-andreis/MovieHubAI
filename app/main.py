"""Entrypoint FastAPI do MovieHub AI."""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.rate_limit import SlidingWindowLimiter
from app.api.routes import router as chat_router
from app.config import Settings, get_settings
from app.memory.store import create_memory
from app.services.chat import ChatService

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("moviehub-ai")


def create_app(settings: Settings | None = None, *, llm=None, memory=None) -> FastAPI:
    settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        mem = memory or await create_memory(
            settings.redis_url,
            max_messages=settings.history_max_messages,
            ttl_seconds=settings.history_ttl_seconds,
        )
        app.state.chat_service = ChatService(settings, mem, llm=llm)
        app.state.rate_limiter = SlidingWindowLimiter(settings.rate_limit_per_minute)
        logger.info(
            "MovieHub AI pronto (env=%s, modelo=%s, api=%s, memória=%s, openai=%s)",
            settings.environment, settings.openai_model, settings.api_base, mem.backend,
            "ok" if settings.openai_api_key or llm else "SEM CHAVE",
        )
        yield
        await mem.close()

    app = FastAPI(
        title="MovieHub AI",
        description="Assistente conversacional do MovieHub — agente LangGraph com tool calling e SSE.",
        version="2.0.0",
        lifespan=lifespan,
    )

    origins = settings.cors_origins
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials="*" not in origins,
        allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "X-Profile-Id", "Content-Type"],
    )

    # Erros sempre no formato {"message": ...} para o front exibir direto.
    @app.exception_handler(StarletteHTTPException)
    async def http_error(_: Request, exc: StarletteHTTPException):
        return JSONResponse(
            {"message": exc.detail}, status_code=exc.status_code, headers=getattr(exc, "headers", None)
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error(_: Request, exc: RequestValidationError):
        errors = [{"field": ".".join(str(p) for p in e.get("loc", [])), "message": e.get("msg")} for e in exc.errors()]
        return JSONResponse({"message": "Requisição inválida.", "errors": errors}, status_code=422)

    app.include_router(chat_router)

    @app.get("/health", tags=["infra"])
    async def health():
        return {"status": "ok"}

    return app


app = create_app()
