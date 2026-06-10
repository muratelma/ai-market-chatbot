"""
Ollama-powered response rewriter.

After the search engine produces structured results, this module
optionally rewrites the ``answer`` text in natural, friendly Turkish.

Safety guarantees
-----------------
* Ollama **never** modifies the product list, prices, or ranking.
* If Ollama fails, the existing ``build_answer()`` template is returned.
* The rewriter only generates the assistant text — product cards remain
  structured backend data.
"""

from __future__ import annotations

import json
import logging

from ollama_client import call_ollama
from search_engine import build_answer

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

REWRITER_SYSTEM_PROMPT = """\
Sen bir Türkçe e-ticaret alışveriş asistanısın. Görevin, arama sonuçlarına göre kullanıcıya doğal ve samimi bir Türkçe yanıt yazmak.

## Kurallar
1. Yalnızca sana verilen ürün listesindeki ürünlerden bahset.
2. Ürün ismi, fiyat, stok veya marka UYDURMA.
3. Ürün sıralamasını DEĞİŞTİRME.
4. Yanıtın 1-3 cümle olsun, kısa ve öz.
5. Samimi ama profesyonel bir ton kullan.
6. Emoji kullanabilirsin ama abartma.

## Yanıt formatı
Yalnızca geçerli JSON döndür:

{"assistant_text": "..."}
"""


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def rewrite_response(
    *,
    original_query: str,
    normalized_query: str,
    parsed_query: dict,
    products: list[dict],
    result_status: str,
    clarification_question: str | None = None,
) -> tuple[str, bool]:
    """
    Generate a natural Turkish assistant response.

    Parameters
    ----------
    original_query : str
        The raw user message.
    normalized_query : str
        The normalized search query.
    parsed_query : dict
        Output of ``parse_query``.
    products : list[dict]
        The product list that will be sent to the frontend.
    result_status : str
        One of ``"products_found"``, ``"clarification_needed"``,
        ``"no_result"``.
    clarification_question : str | None
        The follow-up question from the parser, if any.

    Returns
    -------
    tuple[str, bool]
        ``(answer_text, ollama_used)`` — the answer string and whether
        Ollama was actually used or we fell back to the template.
    """
    # Build context for the rewriter
    top_summaries = []
    for p in products[:5]:
        summary = {
            "product_name": p.get("name", ""),
            "price": p.get("price", ""),
            "main_category": (p.get("tags") or [""])[0] if p.get("tags") else "",
            "match": p.get("match", ""),
        }
        top_summaries.append(summary)

    context = {
        "original_query": original_query,
        "normalized_query": normalized_query,
        "result_status": result_status,
        "product_count": len(products),
        "top_products": top_summaries,
    }

    if clarification_question:
        context["clarification_question"] = clarification_question

    # Build the prompt
    if result_status == "products_found":
        instruction = (
            "Kullanıcı bir ürün aradı ve sonuçlar bulundu. "
            "Bulunan ürünleri kısaca tanıt. İlk ürünün neden en uygun olduğunu belirt."
        )
    elif result_status == "clarification_needed":
        instruction = (
            "Kullanıcının ne aradığı tam anlaşılamadı veya çok genel bir arama yaptı. "
            "Kibarca daha fazla detay iste. "
            f"Şu soruyu baz al: \"{clarification_question or ''}\""
        )
    elif result_status == "no_result":
        instruction = (
            "Kullanıcının aradığı ürün bulunamadı veya katalogda yok. "
            "Kibarca durumu açıkla ve farklı kelimelerle tekrar denemesini öner."
        )
    else:
        instruction = "Kullanıcıya yardımcı bir yanıt yaz."

    prompt = f"{instruction}\n\nBağlam:\n{json.dumps(context, ensure_ascii=False, indent=2)}"

    data = call_ollama(prompt, REWRITER_SYSTEM_PROMPT)

    if data is not None:
        assistant_text = str(data.get("assistant_text", "")).strip()
        if assistant_text:
            return assistant_text, True
        logger.warning("Rewriter: Ollama returned empty assistant_text, using template.")

    # ---- Fallback to template ----
    if result_status == "products_found":
        return build_answer(parsed_query, len(products)), False

    if result_status == "clarification_needed" and clarification_question:
        return clarification_question, False

    if result_status == "no_result":
        return (
            "Maalesef aradığınız kriterlere uygun bir ürün bulunamadı. "
            "Farklı kelimelerle tekrar deneyebilirsiniz."
        ), False

    return build_answer(parsed_query, len(products)), False
