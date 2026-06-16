"""Deterministic unit tests for ranking_diagnostics (Stage 1, observe-only).

No DB, no Ollama, no embeddings — pure functions over dict/DataFrame fixtures.
These lock the directness signals and the regime classifier so the future core
ranker (Phase 1) has a stable, tested substrate to build on.
"""

import pandas as pd

from response_planner import (
    ResponsePlan,
    MODE_FOCUSED_SEARCH,
    MODE_BROAD_SEARCH,
    MODE_CLARIFICATION_ONLY,
)
from ranking_diagnostics import (
    classify_diversification_regime,
    compute_product_directness,
    build_ranking_diagnostics,
    REGIME_FOCUSED,
    REGIME_PROBLEM_BROAD,
    REGIME_BROWSE_BROAD,
    REGIME_NONE,
)


# ---------------------------------------------------------------------------
# Row fixtures (mirror the catalog's Saç Bakımı / Şampuan structure)
# ---------------------------------------------------------------------------

def _row(name, product_type, features, tags, sub="Saç Bakımı",
         main="Kişisel Bakım", semantic=0.5, score=0.6):
    return {
        "product_name": name,
        "product_type": product_type,
        "features": features,
        "tags": tags,
        "attributes": "",
        "sub_category": sub,
        "main_category": main,
        "semantic_score": semantic,
        "score": score,
    }


YAGLI_SAMPUAN = _row(
    "Yağlı Saç Şampuanı", "Şampuan",
    "yağ dengeleyici,temizleyici,ferahlatıcı",
    "yağlı saç,yağlanma,şampuan,saç bakımı,dengeleyici",
)
DOKULME_SAMPUAN = _row(
    "Dökülme Karşıtı Şampuan", "Şampuan",
    "dökülme karşıtı,güçlendirici,onarıcı",
    "saç dökülmesi,şampuan,bakım,güçlendirici",
)
SAC_SERUMU = _row(
    "Argan Saç Serumu", "Saç Serumu",
    "onarıcı,parlaklık",
    "saç serumu,parlaklık,onarım",
)


# ---------------------------------------------------------------------------
# Regime classification
# ---------------------------------------------------------------------------

def test_regime_focused():
    plan = ResponsePlan(mode=MODE_FOCUSED_SEARCH)
    assert classify_diversification_regime({}, plan) == REGIME_FOCUSED


def test_regime_problem_broad():
    plan = ResponsePlan(mode=MODE_BROAD_SEARCH, user_problem="yağlı saç")
    assert classify_diversification_regime({}, plan) == REGIME_PROBLEM_BROAD


def test_regime_browse_broad():
    plan = ResponsePlan(mode=MODE_BROAD_SEARCH, user_problem=None)
    assert classify_diversification_regime({}, plan) == REGIME_BROWSE_BROAD


def test_regime_none_for_non_search_mode():
    plan = ResponsePlan(mode=MODE_CLARIFICATION_ONLY)
    assert classify_diversification_regime({}, plan) == REGIME_NONE


# ---------------------------------------------------------------------------
# Per-product directness
# ---------------------------------------------------------------------------

def test_problem_match_reads_tags():
    diag = compute_product_directness(
        {"features": [], "product_type": None}, YAGLI_SAMPUAN, "yağlı saç"
    )
    assert diag["problem_match"] is True


def test_problem_match_false_for_sibling_problem():
    # A dökülme product must NOT match a yağlı-saç problem.
    diag = compute_product_directness(
        {"features": [], "product_type": None}, DOKULME_SAMPUAN, "yağlı saç"
    )
    assert diag["problem_match"] is False


def test_product_type_exact_vs_substring_vs_none():
    exact = compute_product_directness(
        {"features": [], "product_type": "Şampuan"}, YAGLI_SAMPUAN, None
    )
    assert exact["product_type_match"] == "exact"

    substring = compute_product_directness(
        {"features": [], "product_type": "Serum"}, SAC_SERUMU, None
    )
    assert substring["product_type_match"] == "substring"

    none = compute_product_directness(
        {"features": [], "product_type": "Şampuan"}, SAC_SERUMU, None
    )
    assert none["product_type_match"] == "none"


def test_feature_tag_hits_counted():
    diag = compute_product_directness(
        {"features": ["yağ dengeleyici", "yağlı saç"], "product_type": None},
        YAGLI_SAMPUAN,
        None,
    )
    assert diag["feature_tag_hits"] == 2


def test_directness_score_orders_direct_above_sibling():
    parsed = {"features": ["yağ dengeleyici"], "product_type": "Şampuan",
              "sub_category": "Saç Bakımı", "main_category": "Kişisel Bakım"}
    direct = compute_product_directness(parsed, YAGLI_SAMPUAN, "yağlı saç")
    sibling = compute_product_directness(parsed, DOKULME_SAMPUAN, "yağlı saç")
    assert direct["directness_score"] > sibling["directness_score"]
    assert direct["is_primary_candidate"] is True


# ---------------------------------------------------------------------------
# Query-level diagnostics — never reorders, flags interleaving
# ---------------------------------------------------------------------------

def test_build_diagnostics_preserves_order_and_counts():
    # Order as the (buggy) diversifier might emit it: direct, sibling, direct.
    result_df = pd.DataFrame([YAGLI_SAMPUAN, SAC_SERUMU,
                              _row("Yağ Dengeleyici Şampuan", "Şampuan",
                                   "yağ dengeleyici",
                                   "yağlı saç,şampuan,dengeleyici")])
    parsed = {"features": ["yağ dengeleyici"], "product_type": None,
              "sub_category": "Saç Bakımı", "main_category": "Kişisel Bakım"}
    plan = ResponsePlan(mode=MODE_BROAD_SEARCH, user_problem="yağlı saç")

    diag = build_ranking_diagnostics(parsed, result_df, "yağlı saç için ürün", plan)

    assert diag["regime"] == REGIME_PROBLEM_BROAD
    assert diag["product_count"] == 3
    # Two yağlı products are primaries; the serum is not.
    assert diag["primary_candidate_count"] == 2
    # Two yağlı products are DIRECT tier; the serum is RELATED.
    assert diag["direct_tier_count"] == 2
    # A direct match (index 2) follows a non-direct one (index 1) → interleaving.
    assert diag["direct_after_non_direct"] is True
    assert diag["first_non_direct_index"] == 1
    # Order of ids is unchanged (read-only).
    assert [p["id"] for p in diag["products"]] == [0, 1, 2]


def test_build_diagnostics_empty_result():
    plan = ResponsePlan(mode=MODE_BROAD_SEARCH, user_problem=None)
    diag = build_ranking_diagnostics({}, pd.DataFrame(), "q", plan)
    assert diag["product_count"] == 0
    assert diag["primary_candidate_count"] == 0
    assert diag["direct_after_non_direct"] is False
