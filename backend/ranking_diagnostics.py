"""
Ranking diagnostics (observe-only).

Exposes, in a debug field, the per-product directness signals and the
query-level diversification *regime* for the FINAL, already-ordered search
result.  It is read-only with respect to ranking: it never reorders, filters,
rescores, or changes which products are returned.

The foundational helpers (regime classifier, signal helpers, tier assignment)
live in ``ranking_core``; this module imports from there and only *reports*.
The ``directness_score`` and ``PRIMARY_DIRECTNESS_THRESHOLD`` here remain
diagnostic-only — a readable composite for eyeballing — while the discrete
``directness_tier`` mirrors what ``ranking_core.finalize_ranking_v2`` actually
sorts on when ``RANKING_V2`` is enabled.
"""

from __future__ import annotations

from ranking_core import (
    field as _field,
    row_signal_text,
    problem_match,
    product_type_match,
    feature_tag_hits,
    extract_query_modifiers,
    assign_directness_tier,
    classify_diversification_regime,
    determine_result_grouping,
    match_group_for,
    REGIME_FOCUSED,
    REGIME_PROBLEM_BROAD,
    REGIME_BROWSE_BROAD,
    REGIME_NONE,
    TIER_DIRECT,
)


# Diagnostic-only weights for the readable directness composite.  These do NOT
# drive ordering (the discrete tier does); they make the signal easy to scan in
# logs and the debug field.
_W_PROBLEM_MATCH = 0.50
_W_PRODUCT_TYPE_EXACT = 0.30
_W_PRODUCT_TYPE_SUBSTRING = 0.10
_W_FEATURE_TAG_HIT = 0.10
_FEATURE_TAG_HIT_CAP = 0.30
_W_SUB_CATEGORY = 0.05
_W_MAIN_CATEGORY = 0.02

PRIMARY_DIRECTNESS_THRESHOLD = 0.30


def compute_product_directness(parsed_query, row, user_problem, query_modifiers=None):
    """Per-product directness diagnostics (observe-only).

    ``directness_score`` is a readable composite; ``directness_tier`` is the
    discrete value ``finalize_ranking_v2`` sorts on.
    """
    if query_modifiers is None:
        query_modifiers = set()

    signal_text = row_signal_text(row)

    p_match = problem_match(user_problem, signal_text)
    pt_match = product_type_match(parsed_query, row)
    feature_hits = feature_tag_hits(parsed_query, signal_text)

    sub_match = (
        parsed_query.get("sub_category") is not None
        and _field(row, "sub_category").lower()
        == str(parsed_query["sub_category"]).lower()
    )
    main_match = (
        parsed_query.get("main_category") is not None
        and _field(row, "main_category").lower()
        == str(parsed_query["main_category"]).lower()
    )

    score = 0.0
    reasons = []

    if p_match:
        score += _W_PROBLEM_MATCH
        reasons.append(f"problem:{user_problem}")
    if pt_match == "exact":
        score += _W_PRODUCT_TYPE_EXACT
        reasons.append("product_type:exact")
    elif pt_match == "substring":
        score += _W_PRODUCT_TYPE_SUBSTRING
        reasons.append("product_type:substring")
    if feature_hits:
        score += min(_FEATURE_TAG_HIT_CAP, feature_hits * _W_FEATURE_TAG_HIT)
        reasons.append(f"features:{feature_hits}")
    if sub_match:
        score += _W_SUB_CATEGORY
        reasons.append("sub_category")
    if main_match:
        score += _W_MAIN_CATEGORY
        reasons.append("main_category")

    tier, tier_reason = assign_directness_tier(
        parsed_query, row, user_problem, query_modifiers
    )

    return {
        "problem_match": p_match,
        "product_type_match": pt_match,
        "feature_tag_hits": feature_hits,
        "sub_category_match": bool(sub_match),
        "main_category_match": bool(main_match),
        "directness_score": round(score, 3),
        "directness_tier": tier,
        "tier_reason": tier_reason,
        "is_primary_candidate": score >= PRIMARY_DIRECTNESS_THRESHOLD,
        "match_reason": ", ".join(reasons) if reasons else "semantic_only",
    }


def build_ranking_diagnostics(parsed_query, result_df, query, response_plan,
                              include_grouping=False):
    """Assemble the query-level ranking diagnostics for the FINAL result_df.

    Read-only: iterates the already-ordered ``result_df`` and reports. Never
    mutates or reorders it. Returns a JSON-serialisable dict for a single
    top-level debug key on the ``/search`` response.

    When ``include_grouping`` is set (Stage 4, gated by GROUPED_RANKING_ENABLED),
    the result also carries a ``result_grouping`` label and a per-product
    ``match_group`` derived from the directness tier. This is OBSERVE-ONLY: it
    does not change the products list, ordering, or the response contract.
    """
    user_problem = getattr(response_plan, "user_problem", None)
    regime = classify_diversification_regime(parsed_query, response_plan)
    query_modifiers = extract_query_modifiers(query)

    products = []
    primary_count = 0
    direct_tier_count = 0

    if result_df is not None and not result_df.empty:
        for idx, row in result_df.iterrows():
            diag = compute_product_directness(
                parsed_query, row, user_problem, query_modifiers
            )
            if diag["is_primary_candidate"]:
                primary_count += 1
            if diag["directness_tier"] == TIER_DIRECT:
                direct_tier_count += 1
            products.append({
                "id": int(idx),
                "name": _field(row, "product_name"),
                "product_type": _field(row, "product_type"),
                "semantic_score": round(float(row.get("semantic_score", 0.0)), 3),
                "final_score": round(float(row.get("score", 0.0)), 3),
                **diag,
            })

    # Is the direct-match cluster contiguous at the top, or does a weaker result
    # precede a direct one? (the W2/Finding-4 symptom). Measured on directness_tier.
    first_non_direct_index = -1
    direct_after_non_direct = False
    seen_non_direct = False
    for position, product in enumerate(products):
        if product["directness_tier"] == TIER_DIRECT:
            if seen_non_direct:
                direct_after_non_direct = True
        else:
            seen_non_direct = True
            if first_non_direct_index == -1:
                first_non_direct_index = position

    diagnostics = {
        "regime": regime,
        "user_problem": user_problem,
        "query_modifiers": sorted(query_modifiers),
        "product_count": len(products),
        "primary_candidate_count": primary_count,
        "direct_tier_count": direct_tier_count,
        "first_non_direct_index": first_non_direct_index,
        # True ⇒ ordering still places a direct match after a weaker one.
        "direct_after_non_direct": direct_after_non_direct,
        "products": products,
    }

    # Stage 4 (debug-only): label each product primary/alternative off its tier.
    # Observe-only — does not touch ordering or the response contract.
    if include_grouping:
        result_grouping = determine_result_grouping(
            parsed_query, user_problem, query_modifiers, direct_tier_count
        )
        for product in products:
            product["match_group"] = match_group_for(
                product["directness_tier"], result_grouping
            )
        diagnostics["result_grouping"] = result_grouping
        diagnostics["primary_count"] = sum(
            1 for p in products if p["match_group"] == "primary"
        )
        diagnostics["alternative_count"] = sum(
            1 for p in products if p["match_group"] == "alternative"
        )

    return diagnostics
