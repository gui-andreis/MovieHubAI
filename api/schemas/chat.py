# api/schemas/chat.py
from pydantic import BaseModel, Field


class MessageSchema(BaseModel):
    role: str = Field(
        description="Papel do autor da mensagem.",
        examples=["user", "assistant"]
    )
    content: str = Field(
        description="Conteúdo da mensagem.",
        examples=["quero ver filmes de terror"]
    )


class ChatRequest(BaseModel):
    message: str = Field(
        description="Mensagem atual do usuário.",
        examples=["me recomenda um filme de ficção científica"]
    )
    session_id: str = Field(
        description="ID único da sessão — identifica a conversa no histórico.",
        examples=["user_123_session_456"]
    )
    history: list[MessageSchema] = Field(
        default=[],
        description="Histórico de mensagens anteriores da conversa."
    )


class ChatResponse(BaseModel):
    reply: str = Field(
        description="Resposta gerada pelo assistente."
    )
    session_id: str = Field(
        description="Mesmo session_id recebido — o frontend usa pra continuar a conversa."
    )
    intent: str | None = Field(
        default=None,
        description="Intenção detectada pelo router. Útil pra debug."
    )