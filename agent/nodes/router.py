# agent/nodes/router.py
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage
from agent.state import AgentState

# Cérebro q decide pra onde a conversa vai baseado na intenção do usuário.

llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)

from app.config import settings

llm = ChatOpenAI(
    model="gpt-4o-mini",
    temperature=0,
    api_key=settings.openai_api_key,
)

INTENTS = [
    "search_movies",        # buscar filmes por título, gênero, ano, nota
    "get_recommendations",  # pedir sugestões baseadas em preferências
    "get_movie_details",    # detalhes de um filme específico
    "manage_favorites",     # adicionar ou remover favoritos
    "manage_reviews",       # criar, editar ou deletar reviews
    "list_my_favorites",    # listar favoritos do usuário
    "list_my_reviews",      # listar reviews do usuário
    "general_chat",         # saudações, dúvidas gerais, fora de escopo
]

SYSTEM_PROMPT = f"""Você é um classificador de intenções para o MovieHub, uma plataforma de filmes.

Sua única tarefa é analisar a última mensagem do usuário e retornar UMA das seguintes intenções:
{chr(10).join(f"- {i}" for i in INTENTS)}

Regras:
- Retorne APENAS o nome da intenção, sem explicações, sem pontuação.
- Se a mensagem não se encaixar claramente em nenhuma intenção específica, retorne: general_chat
- Considere o histórico da conversa para disambiguar quando necessário.
- Exemplos:
    "quero ver filmes de terror" → search_movies
    "me recomenda algo parecido com Inception" → get_recommendations
    "adiciona Interestelar nos meus favoritos" → manage_favorites
    "oi, tudo bem?" → general_chat
"""


def router_node(state: AgentState) -> dict:
    messages = state["messages"]

    # Pega só as últimas 6 mensagens pro contexto não crescer demais
    recent = messages[-6:] if len(messages) > 6 else messages

    response = llm.invoke([
        SystemMessage(content=SYSTEM_PROMPT),
        *recent,
    ])

    detected_intent = response.content.strip().lower()

    # Garante que só intenções válidas passam — fallback pra general_chat
    if detected_intent not in INTENTS:
        detected_intent = "general_chat"

    return {"intent": detected_intent}