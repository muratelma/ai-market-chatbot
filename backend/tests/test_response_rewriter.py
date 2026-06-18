"""Regression locks for response_rewriter safety behaviour.

These are deterministic: the no_result path never calls Ollama, and the
Markdown stripper is pure, so they run safely in CI without a model.
"""

from response_rewriter import (
    NO_RESULT_MESSAGE,
    _strip_markdown_emphasis,
    rewrite_response,
)
from search_engine import build_answer


def _parsed(**overrides):
    base = {
        "main_category": None, "sub_category": None, "product_type": None,
        "target_group": None, "features": [], "contexts": [],
        "min_price": None, "max_price": None,
    }
    base.update(overrides)
    return base


def test_no_result_returns_safe_template_without_ollama():
    # Even with Ollama reachable, no_result must short-circuit to the fixed
    # message so it can never invent a product or echo a hallucinated term.
    answer, used = rewrite_response(
        original_query="Görünmezlik pelerini almak istiyorum",
        normalized_query="gizlilik perdesi",  # hallucinated term must NOT leak
        parsed_query=_parsed(),
        products=[],
        result_status="no_result",
    )
    assert answer == NO_RESULT_MESSAGE
    assert used is False
    assert "perde" not in answer.lower()
    assert "katalogda bulunmuyor" in answer.lower()


def test_strip_markdown_emphasis():
    assert _strip_markdown_emphasis("**Kişisel Bakım** bölümünde") == "Kişisel Bakım bölümünde"
    assert _strip_markdown_emphasis("__bold__ ve **kalın**") == "bold ve kalın"
    assert _strip_markdown_emphasis("düz metin") == "düz metin"


def test_build_answer_has_no_markdown():
    # The template must not emit raw ** markers the chat UI would show literally.
    answer = build_answer(
        _parsed(main_category="Kişisel Bakım", product_type="Şampuan",
                target_group="Kadın"),
        product_count=5,
    )
    assert "**" not in answer
