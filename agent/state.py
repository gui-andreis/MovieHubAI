# agent/state.py
from typing import Annotated, Any
from typing_extensions import TypedDict
from langgraph.graph.message import add_messages

#Memória de curto praso, memória de estaado só, o formulário q cada um vai preencher

class AgentState(TypedDict):
    # Histórico de mensagens — add_messages é um reducer do LangGraph:
    # em vez de substituir a lista, ele ACUMULA as mensagens a cada nó.
    # Isso é o que permite o agente "lembrar" o que foi dito antes.
    messages: Annotated[list, add_messages]

    # Intenção detectada pelo router. Exemplos:
    # "search_movies", "get_recommendations", "add_favorite", "general_chat"
    intent: str | None

    # JWT do usuário logado, extraído do header da requisição.
    # As tools passam isso pro MovieHub client nas chamadas autenticadas.
    user_token: str | None

    # ID da sessão — usado como chave no Redis pra persistir o histórico.
    session_id: str

    # Resultado bruto das tools, antes de ser formatado pro usuário.
    # O nó responder usa isso pra montar a resposta final.
    tool_results: list[Any]
    
    
