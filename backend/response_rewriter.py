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
from response_planner import ResponsePlan

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

## Yanıt modları

### focused_search
Kullanıcı belirli bir ürün tipi veya kategori istedi. O kategoriye odaklan.
- Eğer user_problem varsa, problemi ve ürün tipini birlikte belirt.
  Örnek: "Saç dökülmesi sorununa yönelik şampuan seçeneklerini listeledim."
- Eğer user_problem yoksa, ürün tipine odaklan.
  Örnek: "Aradığınız powerbank modelleri arasından en uygun seçenekleri listeledim."
- Eğer should_ask_followup değeri true ise ve bir takip sorusu (clarification_question) verilmişse, yanıtının sonuna mutlaka kelimesi kelimesine o takip sorusunu ekle.

### broad_search
Farklı ürün tipleri listelendi. Çeşitliliği vurgula.
- Eğer user_problem varsa: "X probleminize yönelik farklı ürün tiplerinden seçenekleri listeledim."
- Eğer context_area varsa: "X kategorisinden farklı ürünleri listeledim."
- Eğer top_product_types verilmişse, hangi ürün tiplerinin listelendiğini kısaca belirt.
- Eğer should_ask_followup değeri true ise ve bir takip sorusu (clarification_question) verilmişse, yanıtının sonuna mutlaka kelimesi kelimesine o takip sorusunu ekle.

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
    response_plan: ResponsePlan | None = None,
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
        One of ``"products_found"``, ``"products_found_with_followup"``,
        ``"clarification_needed"``, ``"no_result"``.
    clarification_question : str | None
        The follow-up question from the parser, if any.
    response_plan : ResponsePlan | None
        The response plan with mode and metadata flags.

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

    # Add response plan metadata for mode-aware rewriting
    if response_plan is not None:
        context["response_mode"] = response_plan.mode
        context["should_ask_followup"] = response_plan.should_ask_followup
        if response_plan.user_problem:
            context["user_problem"] = response_plan.user_problem
        if response_plan.context_area:
            context["context_area"] = response_plan.context_area
        if response_plan.top_product_types:
            context["top_product_types"] = response_plan.top_product_types

    # Build the prompt
    if result_status == "products_found_with_followup":
        # Broad search or focused search with followup
        mode = response_plan.mode if response_plan else "broad_search"
        problem_part = ""
        if response_plan and response_plan.user_problem:
            problem_part = f' Kullanıcının problemi: "{response_plan.user_problem}".'
        context_part = ""
        if response_plan and response_plan.context_area:
            context_part = f' Kullanım alanı: "{response_plan.context_area}".'
        types_part = ""
        if response_plan and response_plan.top_product_types:
            types_part = f' Listelenen ürün tipleri: {", ".join(response_plan.top_product_types)}.'
        followup_part = ""
        if clarification_question:
            followup_part = f' Yanıtının sonuna mutlaka kelimesi kelimesine şu takip sorusunu ekle: "{clarification_question}"'

        if mode == "focused_search":
            instruction = (
                "Kullanıcı belirli bir kategori veya ürün tipi için arama yaptı."
                f"{problem_part}{context_part}"
                " Bulunan ürünleri kısaca tanıt."
                f"{followup_part}"
            )
        else:
            instruction = (
                "Kullanıcı geniş bir arama yaptı ve farklı ürün tiplerinden sonuçlar listelendi."
                f"{problem_part}{context_part}{types_part}"
                " Çeşitliliği vurgula."
                f"{followup_part}"
            )
    elif result_status == "products_found":
        problem_part = ""
        if response_plan and response_plan.user_problem:
            problem_part = f' Kullanıcının problemi "{response_plan.user_problem}" ve bu probleme yönelik ürünler listelendi.'
        instruction = (
            "Kullanıcı bir ürün aradı ve sonuçlar bulundu. "
            "Bulunan ürünleri kısaca tanıt. İlk ürünün neden en uygun olduğunu belirt."
            f"{problem_part}"
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
            # Enforce safeguard: If should_ask_followup is true, the follow-up question must be in the assistant_text.
            if response_plan and response_plan.should_ask_followup and clarification_question:
                clar_q = clarification_question.strip()
                if clar_q not in assistant_text:
                    # Append it if not present
                    assistant_text = f"{assistant_text}\n\n{clar_q}"
            return assistant_text, True
        logger.warning("Rewriter: Ollama returned empty assistant_text, using template.")

    # ---- Fallback to template ----
    if result_status == "products_found_with_followup":
        # Build a template that mentions diversity + follow-up
        if response_plan and response_plan.mode == "broad_search" and response_plan.top_product_types:
            types_str = ", ".join(response_plan.top_product_types[:5])
            base = f"Farklı ürün tiplerinden ({types_str}) seçenekleri listeledim. 🛍️"
        else:
            base = build_answer(parsed_query, len(products))
        if clarification_question:
            return f"{base}\n\n{clarification_question}", False
        return base, False

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
