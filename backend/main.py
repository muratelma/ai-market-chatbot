import logging
import re
from typing import Optional

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import numpy as np
import faiss
from sentence_transformers import SentenceTransformer

from config import (
    MODEL_NAME_OR_PATH,
    SEARCH_TOP_K,
    TAXONOMY_CSV_PATH,
    TAXONOMY_MATCH_THRESHOLD,
    OLLAMA_ENABLED,
)
from data_loader import load_products, load_taxonomy
from query_parser import parse_query, build_taxonomy_embeddings, get_clarification_response
from search_engine import (
    create_search_text,
    apply_filters,
    semantic_search,
    diversify_results,
    build_answer,
)
from chat_intent import classify_intent, INTENT_PRODUCT_SEARCH, INTENT_CLARIFICATION_FOLLOWUP, INTENT_NONSENSE
from chat_memory import get_or_create_session, resolve_follow_up, update_session
from chat_normalizer import normalize_query
from response_rewriter import rewrite_response
from response_planner import build_response_plan, MODE_BROAD_SEARCH, MODE_FOCUSED_SEARCH

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)


app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class QueryRequest(BaseModel):
    query: str
    session_id: Optional[str] = None


# Seasonal modifier words. When one of these appears alongside an explicit
# product category, the explicit category must win (see step 7): the seasonal
# word is only a preference, not a category switch.
_SEASONAL_WORDS: frozenset[str] = frozenset({
    "kışlık", "kislik", "yazlık", "yazlik", "mevsimlik",
    "ilkbahar", "sonbahar", "kışlığı", "yazlığı",
})


# Tokens that, taken alone, signal a vague request ("ürün öner",
# "bir şey lazım", "ne almalıyım") rather than a specific missing item
# ("uzay mekiği", "zihin okuma cihazı").  When no parser signal fires
# AND every token is in this set, return a clarification prompt instead
# of the no-result template.
_VAGUE_TOKENS: frozenset[str] = frozenset({
    "ürün", "urun", "ürünü", "urunu", "ürüne", "urune",
    "ürünler", "urunler", "ürünleri", "urunleri",
    "ürünlerden", "urunlerden", "ürününü", "urununu",
    "şey", "sey", "şeyi", "seyi", "şeyler", "seyler",
    "bir", "biraz", "ne", "neyi", "nesi", "neler",
    "öner", "oner", "öneri", "oneri", "tavsiye", "önerir", "onerir",
    "ver", "versene", "verir", "verebilir", "verebilirsin",
    "arıyorum", "ariyorum", "istiyorum", "lazım", "lazim",
    "almalıyım", "almaliyim", "alabilirim", "alabilir",
    "yapabilirim", "yapabilir", "almak", "alalım", "alalim",
    "için", "icin", "lütfen", "lutfen",
})

_VAGUE_CLARIFICATION_QUESTION = (
    "Tam olarak ne aradığını yazar mısın? Kategori, kullanım amacı veya "
    "bütçe gibi bilgilerle yardımcı olabilirim — örneğin \"yağlı saç için "
    "şampuan\" veya \"1500 TL altında erkek ayakkabı\" gibi."
)


def _is_vague_query(query: str) -> bool:
    """Return True when the query consists only of generic intent/filler
    tokens and contains no concrete content noun."""
    tokens = re.findall(r"\w+", query.lower())
    if not tokens:
        return True
    return all(t in _VAGUE_TOKENS for t in tokens)


print("Model yükleniyor...")
model = SentenceTransformer(MODEL_NAME_OR_PATH)

print("Ürünler PostgreSQL'den yükleniyor...")
df = load_products()

print("Ürün metinleri hazırlanıyor...")
search_texts = create_search_text(df)

print("Ürün embeddingleri oluşturuluyor...")
# EMBEDDING ORDER CONTRACT: product_embeddings[i] corresponds to df row i.
# This positional alignment is relied on by search_engine.semantic_search
# (it indexes product_embeddings by df.index). Never reorder/filter `df`
# in place after this point, and after DB migration rebuild embeddings from
# the exact DB-loaded product order (ORDER BY id). See data_loader.load_products.
product_embeddings = model.encode(search_texts)
product_embeddings = np.array(product_embeddings).astype("float32")
faiss.normalize_L2(product_embeddings)

print("Taksonomi verisi okunuyor...")
taxonomy_records = load_taxonomy(TAXONOMY_CSV_PATH)

print("Taksonomi embeddingleri oluşturuluyor...")
taxonomy_embeddings = build_taxonomy_embeddings(model, taxonomy_records)

print(f"AI-Market API hazır. (Ollama: {'aktif' if OLLAMA_ENABLED else 'devre dışı'})")


@app.get("/")
def root():
    return {"message": "AI-Market API çalışıyor"}


@app.post("/search")
def search_products(req: QueryRequest):
    original_query = req.query.strip()

    # ---- 0. Session memory: get or create ----
    session = get_or_create_session(req.session_id)

    # ---- 1. Intent classification ----
    intent_result = classify_intent(
        original_query,
        has_pending_clarification=session.pending_clarification,
    )

    # Non-search intents: return immediately without touching search
    if intent_result.intent not in (
        INTENT_PRODUCT_SEARCH,
        INTENT_CLARIFICATION_FOLLOWUP,
        INTENT_NONSENSE,
    ):
        logger.info("Intent: %s → returning direct response.", intent_result.intent)
        return {
            "answer": intent_result.response,
            "products": [],
            "parsed_query": {},
            "needs_clarification": False,
            "follow_up_question": None,
            "original_query": original_query,
            "normalized_query": original_query,
            "normalization_used": False,
            "normalization_confidence": 0.0,
            "ollama_used": False,
            "ollama_fallback_reason": None,
            "session_id": session.session_id,
            "intent": intent_result.intent,
            "response_source": f"intent_{intent_result.intent}",
        }

    # Nonsense intent with high confidence: return a friendly no-result message
    # instead of sending impossible queries through the search pipeline
    if intent_result.intent == INTENT_NONSENSE and intent_result.confidence >= 0.7:
        logger.info("Intent: nonsense (confidence=%.2f) → returning no-result.", intent_result.confidence)
        return {
            "answer": "Maalesef bu tür bir ürün katalogumuzda bulunmuyor. 😅 "
                      "Farklı bir ürün aramak ister misin? Örneğin "
                      "\"kamp ocağı\", \"spor ayakkabı\" veya \"kablosuz kulaklık\" gibi.",
            "products": [],
            "parsed_query": {},
            "needs_clarification": False,
            "follow_up_question": None,
            "original_query": original_query,
            "normalized_query": original_query,
            "normalization_used": False,
            "normalization_confidence": 0.0,
            "ollama_used": intent_result.method == "ollama",
            "ollama_fallback_reason": None,
            "session_id": session.session_id,
            "intent": intent_result.intent,
            "response_source": "intent_nonsense",
        }

    # ---- 1b. Short-circuit vague requests before normalization ----
    # When Ollama is enabled, "ürün öner" gets normalized into a concrete
    # category (e.g. "saç bakım ürünü"), which the parser then resolves to a
    # real sub-category and returns products for.  That hides the fact that the
    # user never told us *what* they want.  Catch vague queries on the raw text
    # first and ask for clarification — without running normalize/parse/search.
    if _is_vague_query(original_query):
        update_session(
            session,
            user_query=original_query,
            normalized_query=original_query,
            pending_clarification=True,
        )

        answer, rewriter_used = rewrite_response(
            original_query=original_query,
            normalized_query=original_query,
            parsed_query={},
            products=[],
            result_status="clarification_needed",
            clarification_question=_VAGUE_CLARIFICATION_QUESTION,
        )

        return {
            "answer": answer,
            "products": [],
            "parsed_query": {},
            "needs_clarification": True,
            "follow_up_question": _VAGUE_CLARIFICATION_QUESTION,
            "original_query": original_query,
            "normalized_query": original_query,
            "normalization_used": False,
            "normalization_confidence": 0.0,
            "ollama_used": False,
            "ollama_fallback_reason": None,
            "session_id": session.session_id,
            "intent": intent_result.intent,
            "response_mode": "clarification_only",
            "response_source": "ollama_vague_clarification" if rewriter_used else "template_vague_clarification",
        }

    # ---- 2. Resolve follow-ups ----
    effective_query = resolve_follow_up(original_query, session)

    # ---- 3. Ollama query normalization (with fallback) ----
    normalization = normalize_query(effective_query)
    search_query = normalization.normalized_query

    # Debug fields for response
    debug_info = {
        "original_query": original_query,
        "normalized_query": normalization.normalized_query,
        "normalization_used": normalization.used,
        "normalization_confidence": normalization.confidence,
        "ollama_used": normalization.used,
        "ollama_fallback_reason": normalization.fallback_reason,
        "session_id": session.session_id,
        "intent": intent_result.intent,
    }

    # ---- 4. Existing parse_query ----
    # ``original_query`` is forwarded so the parser's broad-intent strip
    # checks the user's actual words (Ollama can expand "ürün öner" into
    # "saç bakım ürünü", which would otherwise mask the broad request).
    parsed_query = parse_query(
        search_query,
        df,
        model,
        taxonomy_embeddings,
        taxonomy_records,
        taxonomy_match_threshold=TAXONOMY_MATCH_THRESHOLD,
        original_query=effective_query,
    )

    # ---- 4b. Fall back to the original query when normalization broke parsing ----
    # Ollama normalization is non-deterministic and can corrupt a perfectly
    # parseable phrase in several ways:
    #   (a) inflect it past the parser, e.g. "özel gün için kadın elbise öner"
    #       → "kadın elbiseleri", which yields NO category signal;
    #   (b) hallucinate an unrelated main category, e.g. "elbise tavsiye et" →
    #       "baharatlık" (Mutfak instead of Giyim); or
    #   (c) flip the sub-category / product_type while keeping the main category,
    #       e.g. "cilt serumu öner" → "saç serumu" (Cilt Serumu → Saç Serumu) or
    #       "kışlık elbise öner" → "kışlık kadın elbiseleri" (Elbise → Mont).
    # The user's literal words are authoritative for category identity. When the
    # original query parses to a category signal that the normalized query lost
    # or contradicts at ANY level (main/sub/product_type), re-parse and search
    # on the original instead.  Explicit product/category terms must outrank the
    # seasonal/context words ("kışlık", "yazlık", ...) the normalizer leans on.
    def _has_category_signal(pq: dict) -> bool:
        return any([pq.get("main_category"), pq.get("sub_category"), pq.get("product_type")])

    def _contradicts(field: str, original_pq: dict, normalized_pq: dict) -> bool:
        # Only a contradiction when BOTH sides committed to a value and they
        # differ — this lets normalization legitimately *add* specificity
        # (e.g. original sub=Saç Bakımı, normalized adds product_type=Şampuan).
        ov, nv = original_pq.get(field), normalized_pq.get(field)
        return bool(ov and nv and ov != nv)

    if effective_query.strip() and effective_query != search_query:
        original_parsed = parse_query(
            effective_query,
            df,
            model,
            taxonomy_embeddings,
            taxonomy_records,
            taxonomy_match_threshold=TAXONOMY_MATCH_THRESHOLD,
            original_query=effective_query,
        )
        if _has_category_signal(original_parsed):
            normalization_lost_category = not _has_category_signal(parsed_query)
            normalization_changed_category = any(
                _contradicts(field, original_parsed, parsed_query)
                for field in ("main_category", "sub_category", "product_type")
            )
            if normalization_lost_category or normalization_changed_category:
                logger.info(
                    "Normalization %s category (%r → %r); falling back to original query.",
                    "dropped" if normalization_lost_category else "changed",
                    effective_query,
                    search_query,
                )
                parsed_query = original_parsed
                search_query = effective_query

    # ---- 5. Build response plan ----
    response_plan = build_response_plan(
        parsed_query, search_query, df, original_query=effective_query
    )
    logger.info(
        "Response plan: mode=%s, diversify=%s, problem=%s, context=%s",
        response_plan.mode,
        response_plan.diversify_results,
        response_plan.user_problem,
        response_plan.context_area,
    )

    # ---- 5b. Handle Ollama clarification ----
    # The Ollama normalizer can over-eagerly ask for clarification even when
    # the user already gave concrete product signals (e.g. "özel gün için
    # kadın elbise öner" → category + target + context all present).  Only
    # honor its clarification request when the parser ALSO failed to find a
    # searchable category — i.e. the plan is not a search mode.  When the plan
    # is broad/focused search, the user told us enough; proceed to products.
    if (
        normalization.needs_clarification
        and normalization.clarification_question
        and response_plan.mode not in (MODE_BROAD_SEARCH, MODE_FOCUSED_SEARCH)
    ):
        update_session(
            session,
            user_query=original_query,
            normalized_query=normalization.normalized_query,
            pending_clarification=True,
        )

        # Try to rewrite the clarification text
        answer, rewriter_used = rewrite_response(
            original_query=original_query,
            normalized_query=normalization.normalized_query,
            parsed_query=parsed_query,
            products=[],
            result_status="clarification_needed",
            clarification_question=normalization.clarification_question,
            response_plan=response_plan,
        )

        return {
            "answer": answer,
            "products": [],
            "parsed_query": parsed_query,
            "needs_clarification": True,
            "follow_up_question": normalization.clarification_question,
            **debug_info,
            "response_mode": response_plan.mode,
            "response_source": "ollama_clarification" if rewriter_used else "ollama_clarification_template",
        }

    # ---- 6. Clarification check ----
    # For broad_search mode, we override the normal clarification behavior:
    # instead of returning clarification-only, we run the search with
    # diversification and include a follow-up question in the response.
    clarification = get_clarification_response(search_query, parsed_query, df)

    if clarification.get("no_catalog_match"):
        # Distinguish "vague" requests ("ürün öner", "bir şey lazım",
        # "ne almalıyım") from genuinely unknown specific items
        # ("uzay mekiği", "zihin okuma cihazı").  The first family
        # should get a clarification prompt; the second should keep the
        # no-result wording.
        if _is_vague_query(original_query):
            update_session(
                session,
                user_query=original_query,
                normalized_query=search_query,
                parsed_query=parsed_query,
                pending_clarification=True,
            )

            answer, rewriter_used = rewrite_response(
                original_query=original_query,
                normalized_query=search_query,
                parsed_query=parsed_query,
                products=[],
                result_status="clarification_needed",
                clarification_question=_VAGUE_CLARIFICATION_QUESTION,
                response_plan=response_plan,
            )

            return {
                "answer": answer,
                "products": [],
                "parsed_query": parsed_query,
                "needs_clarification": True,
                "follow_up_question": _VAGUE_CLARIFICATION_QUESTION,
                **debug_info,
                "response_mode": response_plan.mode,
                "response_source": "ollama_vague_clarification" if rewriter_used else "template_vague_clarification",
            }

        update_session(
            session,
            user_query=original_query,
            normalized_query=search_query,
            parsed_query=parsed_query,
            pending_clarification=False,
        )

        answer, rewriter_used = rewrite_response(
            original_query=original_query,
            normalized_query=search_query,
            parsed_query=parsed_query,
            products=[],
            result_status="no_result",
            response_plan=response_plan,
        )

        return {
            "answer": answer,
            "products": [],
            "parsed_query": parsed_query,
            "needs_clarification": False,
            "follow_up_question": None,
            **debug_info,
            "response_mode": response_plan.mode,
            "response_source": "ollama_no_result" if rewriter_used else "template_no_result",
        }

    if clarification["needs_clarification"]:
        # Override clarification for modes where the user specified enough
        # information to show products:
        # - broad_search: main_category set → show diverse products + follow-up
        # - focused_search: sub_category or product_type set → show products
        should_override = response_plan.mode in (MODE_BROAD_SEARCH, MODE_FOCUSED_SEARCH)

        if should_override:
            logger.info(
                "Clarification override (%s): skipping clarification, "
                "user specified enough context to show products.",
                response_plan.mode,
            )
            # Fall through to search below
        else:
            update_session(
                session,
                user_query=original_query,
                normalized_query=search_query,
                parsed_query=parsed_query,
                pending_clarification=True,
            )

            answer, rewriter_used = rewrite_response(
                original_query=original_query,
                normalized_query=search_query,
                parsed_query=parsed_query,
                products=[],
                result_status="clarification_needed",
                clarification_question=clarification["follow_up_question"],
                response_plan=response_plan,
            )

            return {
                "answer": answer,
                "products": [],
                "parsed_query": parsed_query,
                "needs_clarification": True,
                "follow_up_question": clarification["follow_up_question"],
                **debug_info,
                "response_mode": response_plan.mode,
                "response_source": "ollama_clarification" if rewriter_used else "template_clarification",
            }

    # ---- 7. Filtering + search ----
    # Seasonal modifiers ("kışlık", "yazlık", ...) embed close to outerwear
    # (Mont/Kaban/Bot), so on a small explicit-category pool the broad fallback
    # can drift to a sibling category (e.g. "kışlık elbise" → Mont). When such a
    # modifier appears AND the user named an explicit sub_category/product_type,
    # enforce that category so the explicit term outranks the seasonal one.
    # Restricted to a closed seasonal-word set so ordinary context queries
    # (e.g. "koşu için ayakkabı") keep their whole-catalog rescue.
    _query_tokens = set(re.findall(r"\w+", f"{search_query} {effective_query}".lower()))
    has_explicit_category = (
        parsed_query.get("sub_category") is not None
        or parsed_query.get("product_type") is not None
    )
    enforce_category = has_explicit_category and bool(_query_tokens & _SEASONAL_WORDS)
    filtered_df = apply_filters(df, parsed_query, enforce_explicit_category=enforce_category)

    has_filter = any([
        parsed_query["min_price"] is not None,
        parsed_query["max_price"] is not None,
        parsed_query["main_category"] is not None,
        parsed_query["sub_category"] is not None,
        parsed_query["target_group"] is not None,
        parsed_query["product_type"] is not None,
        len(parsed_query["features"]) > 0,
        len(parsed_query["contexts"]) > 0,
    ])

    if filtered_df.empty and has_filter:
        update_session(
            session,
            user_query=original_query,
            normalized_query=search_query,
            parsed_query=parsed_query,
            pending_clarification=False,
        )

        answer, rewriter_used = rewrite_response(
            original_query=original_query,
            normalized_query=search_query,
            parsed_query=parsed_query,
            products=[],
            result_status="no_result",
            response_plan=response_plan,
        )

        return {
            "answer": answer,
            "products": [],
            "parsed_query": parsed_query,
            "needs_clarification": False,
            "follow_up_question": None,
            **debug_info,
            "response_mode": response_plan.mode,
            "response_source": "ollama_empty" if rewriter_used else "template_empty",
        }

    candidate_df = filtered_df if not filtered_df.empty else df.copy()

    # For broad_search, fetch more candidates so diversification has
    # enough material to pick from across product types.
    search_top_k = SEARCH_TOP_K
    if response_plan.diversify_results:
        search_top_k = max(SEARCH_TOP_K * 4, 20)

    result_df = semantic_search(
        search_query,
        candidate_df,
        model,
        product_embeddings,
        parsed_query,
        top_k=search_top_k,
    )

    # ---- 8. Apply diversification for broad_search ----
    if response_plan.diversify_results and not result_df.empty:
        result_df = diversify_results(result_df, top_k=SEARCH_TOP_K)
        # Capture actual top product_types for the rewriter
        response_plan.top_product_types = (
            result_df["product_type"].dropna().unique().tolist()
        )
        logger.info(
            "Diversified results: %d products across types: %s",
            len(result_df),
            response_plan.top_product_types,
        )

    # ---- 9. Build product list (same structure as before) ----
    products = []

    for idx, row in result_df.iterrows():
        percentage = int(row["match_percent"])

        products.append({
            "id": int(idx),
            "name": row["product_name"],
            "price": f"₺{int(row['price'])}",
            "rating": 4.5,
            "match": f"{percentage}%",
            "image": "🛍️",
            "description": row["description"],
            "tags": [
                row["main_category"],
                row["sub_category"],
                row["target_group"],
                row["product_type"],
            ],
        })

    # ---- 10. Ollama response rewrite (with response plan) ----
    # For broad_search, the result_status includes the follow-up behavior
    result_status = "products_found"
    followup_question = None

    if response_plan.should_ask_followup and products:
        result_status = "products_found_with_followup"
        followup_question = response_plan.followup_question

    answer, rewriter_used = rewrite_response(
        original_query=original_query,
        normalized_query=search_query,
        parsed_query=parsed_query,
        products=products,
        result_status=result_status,
        clarification_question=followup_question,
        response_plan=response_plan,
    )

    # ---- 11. Update session ----
    update_session(
        session,
        user_query=original_query,
        normalized_query=search_query,
        parsed_query=parsed_query,
        pending_clarification=response_plan.should_ask_followup,
        constraints={
            "min_price": parsed_query.get("min_price"),
            "max_price": parsed_query.get("max_price"),
            "target_group": parsed_query.get("target_group"),
        },
    )

    # ---- 12. Return response (backward-compatible + debug) ----
    return {
        "answer": answer,
        "products": products,
        "parsed_query": parsed_query,
        "needs_clarification": False,
        "follow_up_question": followup_question,
        **debug_info,
        "response_mode": response_plan.mode,
        "response_source": "ollama_rewrite" if rewriter_used else "template",
    }