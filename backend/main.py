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
)
from data_loader import load_products, load_taxonomy
from query_parser import parse_query, build_taxonomy_embeddings, get_clarification_response
from search_engine import (
    create_search_text,
    apply_filters,
    semantic_search,
    build_answer,
)


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

print("AI-Market API hazır.")


@app.get("/")
def root():
    return {"message": "AI-Market API çalışıyor"}


@app.post("/search")
def search_products(req: QueryRequest):
    parsed_query = parse_query(
        req.query,
        df,
        model,
        taxonomy_embeddings,
        taxonomy_records,
        taxonomy_match_threshold=TAXONOMY_MATCH_THRESHOLD,
    )

    clarification = get_clarification_response(req.query, parsed_query, df)

    if clarification.get("no_catalog_match"):
        return {
            "answer": "Katalogda bu isteğe uygun net bir ürün bulunamadı. Ürün adını, kullanım amacını veya kategoriyi biraz daha farklı yazabilir misin?",
            "products": [],
            "parsed_query": parsed_query,
            "needs_clarification": False,
            "follow_up_question": None,
        }

    if clarification["needs_clarification"]:
        return {
            "answer": clarification["follow_up_question"],
            "products": [],
            "parsed_query": parsed_query,
            "needs_clarification": True,
            "follow_up_question": clarification["follow_up_question"],
        }

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
       return {
            "answer": build_answer(parsed_query, 0),
            "products": [],
            "parsed_query": parsed_query,
            "needs_clarification": False,
            "follow_up_question": None,
        }

    candidate_df = filtered_df if not filtered_df.empty else df.copy()

    result_df = semantic_search(
        req.query,
        candidate_df,
        model,
        product_embeddings,
        parsed_query,
        top_k=SEARCH_TOP_K,
    )

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

    return {
    "answer": build_answer(parsed_query, len(products)),
    "products": products,
    "parsed_query": parsed_query,
    "needs_clarification": False,
    "follow_up_question": None,
}