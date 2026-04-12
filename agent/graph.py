# agent/graph.py
from langgraph.graph import StateGraph, END
from agent.state import AgentState
from agent.nodes.router import router_node
from agent.nodes.tool_executor import tool_executor_node
from agent.nodes.memory import memory_node
from agent.nodes.responder import responder_node
#Mapa do Cérebro do Agente, o fluxo de dados, a ordem das operações, quais nós existem.

def route_after_router(state: AgentState) -> str:
    """
    Edge condicional chamada após o router.
    Decide pra onde o grafo vai baseado na intenção detectada.
    """
    if state["intent"] == "general_chat":
        return "responder"
    return "tool_executor"


def build_graph():
    graph = StateGraph(AgentState)

    # Registra os nós
    graph.add_node("memory",       memory_node)
    graph.add_node("router",       router_node)
    graph.add_node("tool_executor", tool_executor_node)
    graph.add_node("responder",    responder_node)

    # Nó de entrada
    graph.set_entry_point("memory")

    # Edges fixas
    graph.add_edge("memory", "router")

    # Edge condicional: router → tool_executor OU responder
    graph.add_conditional_edges(
        "router",
        route_after_router,
        {
            "tool_executor": "tool_executor",
            "responder":     "responder",
        }
    )

    # Após executar tools, sempre vai pro responder
    graph.add_edge("tool_executor", "responder")

    # Responder é o fim
    graph.add_edge("responder", END)

    return graph.compile()


# Instância global — compilada uma vez, reutilizada em todas as requisições
agent_graph = build_graph()
