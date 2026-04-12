# agent/nodes/tool_executor.py
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, AIMessage, ToolMessage
from agent.state import AgentState
from app.config import settings
from tools.moviehub_tools import (
    search_movies,
    get_movie_details,
    list_genres,
    get_movie_reviews,
)
from tools.recommendation_tools import get_recommendations
from tools.authenticated_tools import (
    get_my_favorites,
    add_favorite,
    remove_favorite,
    get_my_reviews,
    create_review,
)

INTENT_TOOLS = {
    "search_movies":       [search_movies, list_genres],
    "get_recommendations": [get_recommendations, list_genres],
    "get_movie_details":   [get_movie_details],
    "get_movie_reviews":   [get_movie_reviews],
    "manage_favorites":    [get_my_favorites, add_favorite, remove_favorite],
    "manage_reviews":      [get_my_reviews, create_review],
    "list_my_favorites":   [get_my_favorites],
    "list_my_reviews":     [get_my_reviews],
}

SYSTEM_PROMPT = """Você é um assistente especializado em filmes do MovieHub.

Você tem acesso a ferramentas para buscar filmes, detalhes, recomendações,
gerenciar favoritos e criar reviews.

Regras:
- Use SEMPRE as ferramentas disponíveis antes de responder — nunca invente dados.
- Se um filme não existir no MovieHub, diga isso claramente.
- Para tools autenticadas, use SEMPRE o user_token exatamente como fornecido.
- Nunca tente adivinhar ou modificar o user_token.
- Se o usuário não estiver logado (user_token ausente), avise que ele precisa fazer login.
- Responda sempre em português.
"""


async def tool_executor_node(state: AgentState) -> dict:
    intent = state["intent"]
    messages = state["messages"]
    user_token = state.get("user_token")

    tools = INTENT_TOOLS.get(intent, [])

    if not tools:
        return {"tool_results": []}

    # Intenções autenticadas sem token — avisa o usuário sem chamar tools
    authenticated_intents = {
        "manage_favorites", "manage_reviews",
        "list_my_favorites", "list_my_reviews"
    }
    if intent in authenticated_intents and not user_token:
        return {"tool_results": [], "intent": "general_chat"}

    llm_with_tools = ChatOpenAI(
        model="gpt-4o-mini",
        temperature=0,
        api_key=settings.openai_api_key,
    ).bind_tools(tools)

    recent = messages[-6:] if len(messages) > 6 else messages

    # Injeta o token no system prompt pra o modelo saber que deve usá-lo
    system = SYSTEM_PROMPT
    if user_token:
        system += f"\n\nuser_token do usuário autenticado: {user_token}"

    ai_message = await llm_with_tools.ainvoke([
        SystemMessage(content=system),
        *recent,
    ])

    tool_results = []
    new_messages = [ai_message]

    if ai_message.tool_calls:
        for tool_call in ai_message.tool_calls:
            tool_fn = next(
                (t for t in tools if t.name == tool_call["name"]),
                None
            )
            if tool_fn is None:
                continue

            result = await tool_fn.ainvoke(tool_call["args"])

            tool_message = ToolMessage(
                content=str(result),
                tool_call_id=tool_call["id"],
            )

            new_messages.append(tool_message)
            tool_results.append({
                "tool": tool_call["name"],
                "args": tool_call["args"],
                "result": result,
            })

    return {
        "messages": new_messages,
        "tool_results": tool_results,
    }