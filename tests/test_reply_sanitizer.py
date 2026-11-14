from app.agent.context import ChatContext
from app.services.chat import _extract_inline_suggestions


def test_removes_leaked_tool_call_line():
    ctx = ChatContext(session_id="s")
    assert _extract_inline_suggestions("Quer o trailer?\n\nfunctions.suggest_followups", ctx) == "Quer o trailer?"


def test_moves_inline_suggestions_to_chips():
    ctx = ChatContext(session_id="s")
    reply = _extract_inline_suggestions('Pronto!\n\n[sugestões: "Toca o trailer", "Outra opção"]', ctx)
    assert reply == "Pronto!"
    assert ctx.suggestions == ["Toca o trailer", "Outra opção"]


def test_keeps_normal_reply_untouched():
    ctx = ChatContext(session_id="s")
    text = "**Psicose** (1960) · ⭐ 8.4 — clássico do suspense."
    assert _extract_inline_suggestions(text, ctx) == text
    assert ctx.suggestions == []
