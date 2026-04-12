# api/routes/chat.py
from fastapi import APIRouter, HTTPException, Header
from langchain_core.messages import HumanMessage, AIMessage
from api.schemas.chat import ChatRequest, ChatResponse
from agent.graph import agent_graph
from agent.state import AgentState

router = APIRouter(prefix="/chat", tags=["chat"])


def _build_history(history: list) -> list:
    """
    Converte o histórico do schema Pydantic para
    objetos de mensagem que o LangGraph entende.
    """
    messages = []
    for msg in history:
        if msg.role == "user":
            messages.append(HumanMessage(content=msg.content))
        elif msg.role == "assistant":
            messages.append(AIMessage(content=msg.content))
    return messages


@router.post("", response_model=ChatResponse)
async def chat(
    body: ChatRequest,
    authorization: str | None = Header(default=None),
):
    # Extrai o token JWT do header Authorization se existir
    # Formato esperado: "Bearer <token>"
    user_token = None
    if authorization and authorization.startswith("Bearer "):
        user_token = authorization.removeprefix("Bearer ").strip()

    # Monta o histórico + mensagem atual como lista de mensagens
    history_messages = _build_history(body.history)
    current_message = HumanMessage(content=body.message)

    # Estado inicial que entra no grafo
    initial_state: AgentState = {
        "messages":    [*history_messages, current_message],
        "intent":      None,
        "user_token":  user_token,
        "session_id":  body.session_id,
        "tool_results": [],
    }

    try:
        final_state = await agent_graph.ainvoke(initial_state)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    # A última mensagem sempre é a resposta do assistente
    last_message = final_state["messages"][-1]

    return ChatResponse(
        reply=last_message.content,
        session_id=body.session_id,
        intent=final_state.get("intent"),
    )