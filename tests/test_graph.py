# tests/test_graph.py
import pytest
from langchain_core.messages import HumanMessage
from agent.graph import agent_graph
from agent.state import AgentState


@pytest.mark.asyncio
async def test_graph_busca_filme(mock_moviehub_client):
    """Fluxo completo: busca de filme sem auth."""
    initial_state: AgentState = {
        "messages":    [HumanMessage(content="quero ver filmes de ficção científica")],
        "intent":      None,
        "user_token":  None,
        "session_id":  "test-session-1",
        "tool_results": [],
    }

    final_state = await agent_graph.ainvoke(initial_state)

    assert final_state["intent"] == "search_movies"
    assert len(final_state["messages"]) > 1
    assert final_state["messages"][-1].content != ""


@pytest.mark.asyncio
async def test_graph_conversa_geral(mock_moviehub_client):
    """Fluxo curto: general_chat não chama nenhuma tool."""
    initial_state: AgentState = {
        "messages":    [HumanMessage(content="oi, tudo bem?")],
        "intent":      None,
        "user_token":  None,
        "session_id":  "test-session-2",
        "tool_results": [],
    }

    final_state = await agent_graph.ainvoke(initial_state)

    assert final_state["intent"] == "general_chat"
    assert final_state["tool_results"] == []
    assert final_state["messages"][-1].content != ""
    
@pytest.mark.asyncio
async def test_graph_memoria_persiste(mock_moviehub_client, mock_redis):
    """Verifica se o histórico é salvo no Redis após a resposta."""
    initial_state: AgentState = {
        "messages":    [HumanMessage(content="oi!")],
        "intent":      None,
        "user_token":  None,
        "session_id":  "test-session-memoria",
        "tool_results": [],
    }

    await agent_graph.ainvoke(initial_state)

    # Redis.set deve ter sido chamado ao menos uma vez (save_history)
    assert mock_redis.set.called
    
@pytest.mark.asyncio
async def test_graph_sem_token_retorna_aviso(mock_moviehub_client, mock_redis):
    """Intenção autenticada sem token não chama tools e avisa o usuário."""
    initial_state: AgentState = {
        "messages":    [HumanMessage(content="quais são meus favoritos?")],
        "intent":      None,
        "user_token":  None,  # sem token
        "session_id":  "test-session-auth",
        "tool_results": [],
    }

    final_state = await agent_graph.ainvoke(initial_state)

    # Sem token, tool_results deve estar vazio
    assert final_state["tool_results"] == []
    # Deve ter gerado uma resposta mesmo assim
    assert final_state["messages"][-1].content != ""


@pytest.mark.asyncio
async def test_graph_favoritos_com_token(mock_authenticated_client, mock_redis):
    """Intenção autenticada com token chama a tool correta."""
    initial_state: AgentState = {
        "messages":    [HumanMessage(content="quais são meus filmes favoritos?")],
        "intent":      None,
        "user_token":  "token-fake-123",
        "session_id":  "test-session-favoritos",
        "tool_results": [],
    }

    final_state = await agent_graph.ainvoke(initial_state)

    assert final_state["intent"] == "list_my_favorites"
    assert final_state["messages"][-1].content != ""