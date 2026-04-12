# agent/nodes/responder.py — adiciona o save no final
from agent.state import AgentState
from memory.redis_memory import save_history
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage
from app.config import settings
import json

llm = ChatOpenAI(
    model="gpt-4o-mini",
    temperature=0.4,
    api_key=settings.openai_api_key,
)

SYSTEM_PROMPT = """Você é o assistente do MovieHub, uma plataforma de filmes.

Seu tom é amigável, direto e apaixonado por cinema.

Regras:
- Se houver resultados de ferramentas no contexto, baseie sua resposta EXCLUSIVAMENTE neles.
- Nunca invente títulos, notas, anos ou qualquer dado de filme.
- Se nenhum filme foi encontrado, diga isso com clareza e sugira que o usuário refine a busca.
- Para listas de filmes, apresente de forma organizada: título, ano e nota quando disponíveis.
- Mantenha respostas concisas — no máximo 4 filmes por resposta, salvo pedido explícito.
- Responda sempre em português.
"""


def _format_tool_results(tool_results: list) -> str:
    if not tool_results:
        return ""
    parts = []
    for tr in tool_results:
        parts.append(
            f"[{tr['tool']}]\n"
            f"Parâmetros: {json.dumps(tr['args'], ensure_ascii=False)}\n"
            f"Resultado: {json.dumps(tr['result'], ensure_ascii=False)}"
        )
    return "\n\n".join(parts)


async def responder_node(state: AgentState) -> dict:
    messages = state["messages"]
    tool_results = state.get("tool_results", [])
    session_id = state["session_id"]

    recent = messages[-6:] if len(messages) > 6 else messages

    system_parts = [SYSTEM_PROMPT]
    if tool_results:
        formatted = _format_tool_results(tool_results)
        system_parts.append(f"\n\nDados recuperados pelas ferramentas:\n{formatted}")

    response = llm.invoke([
        SystemMessage(content="\n".join(system_parts)),
        *recent,
    ])

    # Persiste o histórico completo incluindo a resposta gerada
    await save_history(session_id, [*messages, response])

    return {"messages": [response]}