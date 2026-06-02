import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import faiss
import numpy as np
from sentence_transformers import SentenceTransformer

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from config import (  # noqa: E402
    MODEL_NAME_OR_PATH,
    PRODUCTS_CSV_PATH,
    SEARCH_TOP_K,
    TAXONOMY_CSV_PATH,
    TAXONOMY_MATCH_THRESHOLD,
)
from data_loader import load_products, load_taxonomy  # noqa: E402
from query_parser import (  # noqa: E402
    build_taxonomy_embeddings,
    get_clarification_response,
    parse_query,
)
from search_engine import apply_filters, create_search_text, semantic_search  # noqa: E402


@dataclass
class EvalContext:
    model: SentenceTransformer
    products_df: Any
    product_embeddings: np.ndarray
    taxonomy_records: list[dict[str, Any]]
    taxonomy_embeddings: np.ndarray
    top_k: int


def load_gold_queries(gold_path: Path) -> list[dict[str, Any]]:
    with gold_path.open("r", encoding="utf-8") as file:
        data = json.load(file)

    if not isinstance(data, list):
        raise ValueError("Gold query set JSON formatı liste olmalı.")

    return data


def build_eval_context(top_k: int) -> EvalContext:
    model = SentenceTransformer(MODEL_NAME_OR_PATH)
    products_df = load_products(PRODUCTS_CSV_PATH)

    search_texts = create_search_text(products_df)
    product_embeddings = model.encode(search_texts)
    product_embeddings = np.array(product_embeddings).astype("float32")
    faiss.normalize_L2(product_embeddings)

    taxonomy_records = load_taxonomy(TAXONOMY_CSV_PATH)
    taxonomy_embeddings = build_taxonomy_embeddings(model, taxonomy_records)

    return EvalContext(
        model=model,
        products_df=products_df,
        product_embeddings=product_embeddings,
        taxonomy_records=taxonomy_records,
        taxonomy_embeddings=taxonomy_embeddings,
        top_k=top_k,
    )


def run_single_query(context: EvalContext, query: str) -> dict[str, Any]:
    parsed_query = parse_query(
        query,
        context.products_df,
        context.model,
        context.taxonomy_embeddings,
        context.taxonomy_records,
        taxonomy_match_threshold=TAXONOMY_MATCH_THRESHOLD,
    )

    clarification = get_clarification_response(query, parsed_query, context.products_df)

    if clarification.get("no_catalog_match"):
        return {
            "needs_clarification": False,
            "no_catalog_match": True,
            "products": [],
            "parsed_query": parsed_query,
        }

    if clarification.get("needs_clarification"):
        return {
            "needs_clarification": True,
            "no_catalog_match": False,
            "products": [],
            "parsed_query": parsed_query,
            "follow_up_question": clarification.get("follow_up_question"),
        }

    filtered_df = apply_filters(context.products_df, parsed_query)

    # Block fallback when a strong hard filter (product_type) produced zero matches.
    # A specific product_type that yields no rows means the item is genuinely absent
    # from the catalog; falling back to the full database would surface unrelated products.
    # Softer filters (main_category / sub_category alone) still allow the fallback so
    # that broad or ambiguous queries keep returning results.
    if filtered_df.empty and parsed_query.get("product_type") is not None:
        return {
            "needs_clarification": False,
            "no_catalog_match": False,
            "products": [],
            "parsed_query": parsed_query,
        }

    candidate_df = filtered_df if not filtered_df.empty else context.products_df.copy()

    result_df = semantic_search(
        query,
        candidate_df,
        context.model,
        context.product_embeddings,
        parsed_query,
        top_k=context.top_k,
    )

    products = []
    for _, row in result_df.iterrows():
        products.append(
            {
                "name": row["product_name"],
                "main_category": row["main_category"],
                "sub_category": row["sub_category"],
                "target_group": row["target_group"],
                "product_type": row["product_type"],
                "match_percent": int(row["match_percent"]),
            }
        )

    return {
        "needs_clarification": False,
        "no_catalog_match": False,
        "products": products,
        "parsed_query": parsed_query,
    }


def product_matches_expectation(product: dict[str, Any], expected: dict[str, Any]) -> bool:
    if not expected:
        return False

    for field in ("main_category", "sub_category", "target_group"):
        expected_value = expected.get(field)
        if expected_value is not None and product.get(field) != expected_value:
            return False

    expected_product_types = expected.get("product_types_any", [])
    if expected_product_types and product.get("product_type") not in expected_product_types:
        return False

    return True


def evaluate_queries(gold_queries: list[dict[str, Any]], context: EvalContext) -> dict[str, Any]:
    top1_hits = 0
    top3_hits = 0
    topk_denominator = 0

    clarification_count = 0
    empty_count = 0

    expected_clarification_matches = 0
    expected_empty_matches = 0
    expected_flag_count = 0

    per_query = []

    for item in gold_queries:
        query_id = item.get("id", "")
        query = item["query"]
        expected = item.get("expected", {})
        expects_clarification = bool(item.get("expects_clarification", False))
        expects_empty_result = bool(item.get("expects_empty_result", False))

        result = run_single_query(context, query)

        needs_clarification = bool(result.get("needs_clarification", False))
        products = result.get("products", [])
        is_empty_result = (not needs_clarification) and (len(products) == 0)

        clarification_count += int(needs_clarification)
        empty_count += int(is_empty_result)

        if expects_clarification or expects_empty_result:
            expected_flag_count += 1
            expected_clarification_matches += int(needs_clarification == expects_clarification)
            expected_empty_matches += int(is_empty_result == expects_empty_result)

        top1_hit = False
        top3_hit = False

        # Top-k relevance is measured only on intent-labeled queries.
        if expected and not expects_clarification and not expects_empty_result:
            topk_denominator += 1

            if products:
                top1_hit = product_matches_expectation(products[0], expected)
                top3_hit = any(product_matches_expectation(product, expected) for product in products[:3])

            top1_hits += int(top1_hit)
            top3_hits += int(top3_hit)

        per_query.append(
            {
                "id": query_id,
                "query": query,
                "expected": expected,
                "expects_clarification": expects_clarification,
                "expects_empty_result": expects_empty_result,
                "needs_clarification": needs_clarification,
                "is_empty_result": is_empty_result,
                "top1_hit": top1_hit,
                "top3_hit": top3_hit,
                "products": products,
                "parsed_query": result.get("parsed_query"),
            }
        )

    total_query_count = len(gold_queries)

    metrics = {
        "top1_relevance": (top1_hits / topk_denominator) if topk_denominator else 0.0,
        "top3_hit_rate": (top3_hits / topk_denominator) if topk_denominator else 0.0,
        "clarification_rate": (clarification_count / total_query_count) if total_query_count else 0.0,
        "empty_result_rate": (empty_count / total_query_count) if total_query_count else 0.0,
    }

    expectations = {
        "tracked_expectation_queries": expected_flag_count,
        "clarification_expectation_match_rate": (
            expected_clarification_matches / expected_flag_count
            if expected_flag_count
            else 0.0
        ),
        "empty_expectation_match_rate": (
            expected_empty_matches / expected_flag_count
            if expected_flag_count
            else 0.0
        ),
    }

    counters = {
        "total_queries": total_query_count,
        "topk_denominator": topk_denominator,
        "top1_hits": top1_hits,
        "top3_hits": top3_hits,
        "clarification_count": clarification_count,
        "empty_result_count": empty_count,
    }

    return {"metrics": metrics, "counters": counters, "expectations": expectations, "queries": per_query}


def print_summary(report: dict[str, Any]) -> None:
    metrics = report["metrics"]
    counters = report["counters"]
    expectations = report["expectations"]

    print("=" * 72)
    print("AI-Market Eval Harness")
    print("=" * 72)
    print(f"Top-1 relevance:      {metrics['top1_relevance']:.3f} ({counters['top1_hits']}/{counters['topk_denominator']})")
    print(f"Top-3 hit rate:       {metrics['top3_hit_rate']:.3f} ({counters['top3_hits']}/{counters['topk_denominator']})")
    print(f"Clarification rate:   {metrics['clarification_rate']:.3f} ({counters['clarification_count']}/{counters['total_queries']})")
    print(f"Empty-result rate:    {metrics['empty_result_rate']:.3f} ({counters['empty_result_count']}/{counters['total_queries']})")
    print("-" * 72)
    print(
        "Expectation alignment:"
        f" clarification={expectations['clarification_expectation_match_rate']:.3f},"
        f" empty={expectations['empty_expectation_match_rate']:.3f},"
        f" tracked={expectations['tracked_expectation_queries']}"
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Gold query set ile parser/ranking kalitesini yerelde ölçer."
    )
    parser.add_argument(
        "--gold-set",
        default=str(BACKEND_DIR / "eval" / "gold_queries.json"),
        help="Gold query set JSON dosya yolu",
    )
    parser.add_argument(
        "--top-k",
        type=int,
        default=SEARCH_TOP_K,
        help="Arama sonucu top-k değeri",
    )
    parser.add_argument(
        "--output-json",
        default="",
        help="Detaylı raporu JSON olarak kaydetmek için dosya yolu",
    )
    parser.add_argument(
        "--show-failures",
        action="store_true",
        help="Top-1/top-3 kaçan sorguları yazdır",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    gold_path = Path(args.gold_set).resolve()
    gold_queries = load_gold_queries(gold_path)
    context = build_eval_context(top_k=max(1, int(args.top_k)))

    report = evaluate_queries(gold_queries, context)
    print_summary(report)

    if args.show_failures:
        print("-" * 72)
        print("Başarısız top-k sorguları:")
        for query_result in report["queries"]:
            if query_result["expected"] and not query_result["top3_hit"]:
                print(f"- {query_result['id']}: {query_result['query']}")

    if args.output_json:
        output_path = Path(args.output_json).resolve()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with output_path.open("w", encoding="utf-8") as file:
            json.dump(report, file, ensure_ascii=False, indent=2)
        print(f"Detaylı rapor kaydedildi: {output_path}")


if __name__ == "__main__":
    main()
