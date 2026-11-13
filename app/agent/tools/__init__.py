"""Registro de todas as tools do agente + rótulos amigáveis para o evento SSE `tool`."""
from app.agent.tools.catalog import CATALOG_TOOLS
from app.agent.tools.fun import FUN_TOOLS
from app.agent.tools.personal import PERSONAL_TOOLS
from app.agent.tools.ui import UI_TOOLS

ALL_TOOLS = [*CATALOG_TOOLS, *PERSONAL_TOOLS, *UI_TOOLS, *FUN_TOOLS]

TOOL_LABELS: dict[str, str] = {
    "search_titles": "Procurando no catálogo…",
    "get_title_details": "Lendo os detalhes do título…",
    "get_similar": "Buscando títulos parecidos…",
    "get_trending": "Vendo o que está em alta…",
    "get_top10": "Consultando o Top 10 de hoje…",
    "get_upcoming": "Checando os próximos lançamentos…",
    "random_pick": "Sorteando um título…",
    "list_genres": "Listando gêneros…",
    "list_providers": "Listando streamings…",
    "get_person": "Pesquisando sobre essa pessoa…",
    "get_collection": "Abrindo a saga…",
    "get_season_episodes": "Listando episódios…",
    "get_reviews_summary": "Lendo o que a galera achou…",
    "get_my_list": "Abrindo sua lista…",
    "add_to_my_list": "Adicionando à Minha Lista…",
    "remove_from_my_list": "Removendo da Minha Lista…",
    "react_to_title": "Registrando sua reação…",
    "get_continue_watching": "Vendo o que você estava assistindo…",
    "write_review": "Publicando sua review…",
    "get_my_reviews": "Buscando suas reviews…",
    "get_my_stats": "Calculando suas estatísticas…",
    "navigate": "Abrindo a página…",
    "open_title": "Abrindo o título…",
    "play_trailer": "Preparando o trailer…",
    "play_title": "Dando o play…",
    "set_filters": "Aplicando filtros…",
    "refresh_view": "Atualizando a tela…",
    "show_toast": "Notificando…",
    "suggest_followups": "Pensando em próximos passos…",
    "plan_marathon": "Montando sua maratona…",
    "compare_titles": "Comparando títulos…",
    "group_pick": "Juntando os gostos do grupo…",
}

# Tools que não devem aparecer como "status" na UI (são instantâneas / internas).
SILENT_TOOLS = {"suggest_followups", "refresh_view", "show_toast"}

__all__ = ["ALL_TOOLS", "TOOL_LABELS", "SILENT_TOOLS"]
