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


# Fixed, safe message for out-of-catalog / unreal-item requests. We deliberately
# do NOT route no-result through Ollama: with no products to ground it, the
# rewriter tends to hallucinate (inventing product types, or echoing a wrongly
# normalized term such as "gizlilik perdesi"). A generic template keeps the
# reply honest and never fabricates a catalog item.
NO_RESULT_MESSAGE = (
    "Bu ürün şu anda katalogda bulunmuyor. "
    "İsterseniz farklı bir ürün türü veya kategori deneyebilirsiniz."
)


def _strip_markdown_emphasis(text: str) -> str:
    """Remove Markdown bold/italic markers the chat UI renders verbatim.

    The frontend prints the answer as plain text, so stray ``**`` / ``__`` from
    either the template or an Ollama rewrite would leak into the UI as literal
    asterisks. Dropping the markers (keeping the inner words) is safe and
    idempotent.
    """
    return text.replace("**", "").replace("__", "")


def _ensure_substitution_disclosure(text: str, unavailable_category: str | None) -> str:
    """Guarantee the answer admits a category substitution.

    The search layer can deterministically detect that the user's requested
    category isn't present in the results (see
    ``search_engine.detect_unavailable_category``). The model is *instructed* to
    own this, but small models follow conditional rules unreliably — so if the
    produced text shows no sign of acknowledging it (neither the category label
    nor an admission cue), we prepend a fixed honest clause. This makes the
    behavior model-independent and also covers the template/Ollama-off path.
    """
    if not unavailable_category:
        return text
    lowered = text.lower()
    # Only an explicit "couldn't find / instead of" admission counts. We do NOT
    # treat the mere presence of the category label as acknowledgement: a small
    # model almost always echoes the user's query term ("kadın çanta
    # aradığınızda ..."), which is not the same as admitting it has none.
    admission_cues = ("bulamad", "bulunmuyor", "bulunmama", "bulamıyor", "yerine", "maalesef")
    if any(cue in lowered for cue in admission_cues):
        return text
    return (
        f"Aradığınız {unavailable_category} kategorisinde uygun bir ürün bulamadım, "
        f"size en yakın alternatifleri listeledim. "
    ) + text


# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

REWRITER_SYSTEM_PROMPT = """\
Sen bir Türkçe e-ticaret alışveriş asistanısın. Görevin, arama sonuçlarına göre kullanıcıya doğal ve samimi bir Türkçe yanıt yazmak.

## Kurallar
1. Yalnızca sana verilen ürün listesindeki (top_products) ürünlerden bahset.
2. Ürün ismi, fiyat, stok veya marka UYDURMA.
3. Bir ürünün belirli bir özelliğe sahip olduğunu (ör. su geçirmez, deri, kablosuz, su soğutmalı) YALNIZCA o özellik ürünün "product_name", "tags" veya "description" alanında açıkça geçiyorsa söyle. Veride yoksa o özellikten hiç bahsetme; üründe varmış gibi gösterme.
3b. Bağlamda "unavailable_features" verilmişse, o özelliklere sahip ürün YOKTUR: hiçbir ürünün bu özelliği taşıdığını söyleme. Gerekirse "aradığınız [özellik] özelliğine tam uyan bir ürün bulamadım, size en yakın seçenekleri listeledim" gibi dürüst bir ifade kullan.
4. Ürünü yanlış kategoriye/türe koyma. Bir ürünün kategori veya türünü belirtirken yalnızca onun "tags" alanını kullan; bir montu "ayakkabı", bir çantayı "kulaklık" gibi gösterme.
5. Bağlamda "unavailable_category" verilmişse, kullanıcının istediği o kategoride/türde ürün YOKTUR. Yanıta MUTLAKA bunu dürüstçe söyleyerek başla ve listelenenlerin alternatif olduğunu belirt. Örnek: "Aradığınız [unavailable_category] kategorisinde uygun ürün bulamadım, ama size en yakın alternatifleri listeledim:". Sonra alternatif ürünlerden bahset.
6. Ürün sıralamasını DEĞİŞTİRME.
7. Yanıtın 1-3 cümle olsun, kısa ve öz.
8. Samimi ama profesyonel bir ton kullan.
9. Emoji kullanabilirsin ama abartma.

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
    unavailable_category: str | None = None,
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
    # No-result is answered with a fixed, safe template — never Ollama — so the
    # reply cannot invent a product or echo a hallucinated normalized term.
    if result_status == "no_result":
        return NO_RESULT_MESSAGE, False

    # Build context for the rewriter
    top_summaries = []
    for p in products[:5]:
        summary = {
            "product_name": p.get("name", ""),
            "price": p.get("price", ""),
            "main_category": (p.get("tags") or [""])[0] if p.get("tags") else "",
            # Grounding fields: the rewriter may ONLY assert attributes that
            # actually appear here. Without tags/description the model cannot
            # verify a requested feature (e.g. "su geçirmez") and tends to
            # fabricate a match for it.
            "tags": p.get("tags") or [],
            "description": p.get("description", ""),
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

    # Deterministic, server-side grounding signal. We do NOT pass the raw
    # requested features (doing so primes a small model to weave the requested
    # word — e.g. "su geçirmez" — into the answer even when no product has it).
    # Instead we compute which requested features are absent from EVERY listed
    # product and tell the model, plainly, that those features are unavailable.
    if parsed_query.get("features"):
        grounded = " ".join(
            f"{p.get('name','')} {' '.join(p.get('tags') or [])} {p.get('description','')}"
            for p in products[:5]
        ).lower()
        unavailable = [f for f in parsed_query["features"] if f.lower() not in grounded]
        if unavailable:
            context["unavailable_features"] = unavailable
    if parsed_query.get("product_type"):
        context["requested_product_type"] = parsed_query["product_type"]

    # Deterministic substitution signal computed by the search layer: the user
    # asked for this category but no listed product matches it (price filter
    # relaxed the category). The answer must own this honestly.
    if unavailable_category:
        context["unavailable_category"] = unavailable_category

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
        assistant_text = _strip_markdown_emphasis(str(data.get("assistant_text", "")).strip())
        if assistant_text:
            assistant_text = _ensure_substitution_disclosure(assistant_text, unavailable_category)
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
        base = _ensure_substitution_disclosure(base, unavailable_category)
        if clarification_question:
            return f"{base}\n\n{clarification_question}", False
        return base, False

    if result_status == "products_found":
        answer = build_answer(parsed_query, len(products))
        return _ensure_substitution_disclosure(answer, unavailable_category), False

    if result_status == "clarification_needed" and clarification_question:
        return clarification_question, False

    if result_status == "no_result":
        # Defensive: the early no_result short-circuit above already covers this,
        # but keep one source of truth for the message.
        return NO_RESULT_MESSAGE, False

    return build_answer(parsed_query, len(products)), False
