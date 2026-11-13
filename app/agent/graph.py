"""Grafo do agente: loop clássico agent ⇄ tools (ReAct com tool calling nativo).

    START → agent ──(tem tool_calls?)──► tools ─┐
              ▲                                 │
              └─────────────────────────────────┘
              └──(resposta final)──► END

- O LLM decide sozinho quais tools usar (sem classificador de intenção).
- `iterations` limita o número de rodadas de tools; ao atingir o limite o
  agente é obrigado a responder sem tools.
"""
from __future__ import annotations

from typing import Annotated, Any

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, AnyMessage, SystemMessage
from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode
from typing_extensions import TypedDict

from app.agent.context import get_ctx
from app.agent.prompts import FINALIZE_PROMPT, build_system_prompt
from app.agent.tools import ALL_TOOLS


class AgentState(TypedDict):
    messages: Annotated[list[AnyMessage], add_messages]
    iterations: int


AGENT_NODE = "agent"
TOOLS_NODE = "tools"


def build_graph(llm: BaseChatModel, *, max_iterations: int = 6, tools: list | None = None):
    tools = tools if tools is not None else ALL_TOOLS
    llm_with_tools = llm.bind_tools(tools)

    async def agent(state: AgentState, config: RunnableConfig) -> dict[str, Any]:
        ctx = get_ctx(config)
        iterations = state.get("iterations", 0)
        messages = [SystemMessage(content=build_system_prompt(ctx)), *state["messages"]]
        if iterations >= max_iterations:
            response = await llm.ainvoke([*messages, SystemMessage(content=FINALIZE_PROMPT)], config)
        else:
            response = await llm_with_tools.ainvoke(messages, config)
        return {"messages": [response], "iterations": iterations + 1}

    def route(state: AgentState) -> str:
        last = state["messages"][-1]
        if isinstance(last, AIMessage) and last.tool_calls:
            return TOOLS_NODE
        return END

    graph = StateGraph(AgentState)
    graph.add_node(AGENT_NODE, agent)
    graph.add_node(TOOLS_NODE, ToolNode(tools, handle_tool_errors=True))
    graph.add_edge(START, AGENT_NODE)
    graph.add_conditional_edges(AGENT_NODE, route, {TOOLS_NODE: TOOLS_NODE, END: END})
    graph.add_edge(TOOLS_NODE, AGENT_NODE)
    return graph.compile()
