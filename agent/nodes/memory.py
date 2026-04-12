# agent/nodes/memory.py
from agent.state import AgentState
from memory.redis_memory import load_history, save_history


async def memory_node(state: AgentState) -> dict:
    session_id = state["session_id"]
    current_messages = state["messages"]

    # Carrega histórico do Redis
    history = await load_history(session_id)

    # Junta histórico persistido + mensagem atual que veio na requisição
    # Evita duplicatas — a mensagem atual já está em current_messages
    if history:
        merged = history[:-len(current_messages)] + current_messages \
            if len(history) >= len(current_messages) else current_messages
    else:
        merged = current_messages

    # Salva o estado atual antes de processar
    await save_history(session_id, merged)

    return {"messages": merged}