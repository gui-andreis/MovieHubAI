# app/main.py
import logging
from fastapi import FastAPI
from contextlib import asynccontextmanager
from app.config import settings
from api.routes.chat import router as chat_router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("moviehub-ai")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info(f"iniciando em modo {settings.environment}")
    logger.info(f"conectando ao MovieHub em {settings.moviehub_base_url}")

    from agent.graph import agent_graph
    logger.info(f"grafo compilado — nós: {list(agent_graph.nodes.keys())}")

    yield

    logger.info("encerrando...")


app = FastAPI(
    title="MovieHub AI",
    description="Serviço de IA do MovieHub — agente conversacional com LangGraph.",
    version="0.1.0",
    lifespan=lifespan,
)

app.include_router(chat_router, prefix="/api")


@app.get("/health", tags=["infra"])
async def health():
    return {
        "status": "ok",
        "environment": settings.environment,
        "moviehub_url": settings.moviehub_base_url,
    }