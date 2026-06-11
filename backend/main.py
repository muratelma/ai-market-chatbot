import logging
from typing import Optional

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import numpy as np
import faiss
from sentence_transformers import SentenceTransformer

from config import (
    MODEL_NAME_OR_PATH,
    PRODUCTS_CSV_PATH,
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
    build_answer,
)
from chat_intent import classify_intent, INTENT_PRODUCT_SEARCH, INTENT_CLARIFICATION_FOLLOWUP, INTENT_NONSENSE
from chat_memory import get_or_create_session, resolve_follow_up, update_session
from chat_normalizer import normalize_query
from response_rewriter import rewrite_response

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


print("Model yükleniyor...")
model = SentenceTransformer(MODEL_NAME_OR_PATH)

print("CSV okunuyor...")
df = load_products(PRODUCTS_CSV_PATH)

print("Ürün metinleri hazırlanıyor...")
search_texts = create_search_text(df)

print("Ürün embeddingleri oluşturuluyor...")
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

    # ---- 3. Handle Ollama clarification ----
    if normalization.needs_clarification and normalization.clarification_question:
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
            parsed_query={},
            products=[],
            result_status="clarification_needed",
            clarification_question=normalization.clarification_question,
        )

        return {
            "answer": answer,
            "products": [],
            "parsed_query": {},
            "needs_clarification": True,
            "follow_up_question": normalization.clarification_question,
            **debug_info,
            "response_source": "ollama_clarification" if rewriter_used else "ollama_clarification_template",
        }

    # ---- 4. Existing parse_query (UNCHANGED) ----
    parsed_query = parse_query(
        search_query,
        df,
        model,
        taxonomy_embeddings,
        taxonomy_records,
        taxonomy_match_threshold=TAXONOMY_MATCH_THRESHOLD,
    )

    # ---- 5. Existing clarification check (UNCHANGED) ----
    clarification = get_clarification_response(search_query, parsed_query, df)

    if clarification.get("no_catalog_match"):
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
        )

        return {
            "answer": answer,
            "products": [],
            "parsed_query": parsed_query,
            "needs_clarification": False,
            "follow_up_question": None,
            **debug_info,
            "response_source": "ollama_no_result" if rewriter_used else "template_no_result",
        }

    if clarification["needs_clarification"]:
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
        )

        return {
            "answer": answer,
            "products": [],
            "parsed_query": parsed_query,
            "needs_clarification": True,
            "follow_up_question": clarification["follow_up_question"],
            **debug_info,
            "response_source": "ollama_clarification" if rewriter_used else "template_clarification",
        }

    # ---- 6. Existing filtering + search (UNCHANGED) ----
    filtered_df = apply_filters(df, parsed_query)

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
        )

        return {
            "answer": answer,
            "products": [],
            "parsed_query": parsed_query,
            "needs_clarification": False,
            "follow_up_question": None,
            **debug_info,
            "response_source": "ollama_empty" if rewriter_used else "template_empty",
        }

    candidate_df = filtered_df if not filtered_df.empty else df.copy()

    result_df = semantic_search(
        search_query,
        candidate_df,
        model,
        product_embeddings,
        parsed_query,
        top_k=SEARCH_TOP_K,
    )

    # ---- 7. Build product list (same structure as before) ----
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

    # ---- 8. Ollama response rewrite (with fallback) ----
    answer, rewriter_used = rewrite_response(
        original_query=original_query,
        normalized_query=search_query,
        parsed_query=parsed_query,
        products=products,
        result_status="products_found",
    )

    # ---- 9. Update session ----
    update_session(
        session,
        user_query=original_query,
        normalized_query=search_query,
        parsed_query=parsed_query,
        pending_clarification=False,
        constraints={
            "min_price": parsed_query.get("min_price"),
            "max_price": parsed_query.get("max_price"),
            "target_group": parsed_query.get("target_group"),
        },
    )

    # ---- 10. Return response (backward-compatible + debug) ----
    return {
        "answer": answer,
        "products": products,
        "parsed_query": parsed_query,
        "needs_clarification": False,
        "follow_up_question": None,
        **debug_info,
        "response_source": "ollama_rewrite" if rewriter_used else "template",
    }