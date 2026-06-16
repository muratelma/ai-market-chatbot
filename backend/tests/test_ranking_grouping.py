"""Deterministic unit tests for Stage 4 primary/alternative classification.

Observe-only labels derived from the V2 directness tier. Pure functions over
dict/DataFrame fixtures — no DB, no Ollama, no embeddings.
"""

import pandas as pd

from response_planner import ResponsePlan, MODE_FOCUSED_SEARCH, MODE_BROAD_SEARCH
from ranking_core import (
    has_explicit_axis,
    determine_result_grouping,
    match_group_for,
    compute_grouping,
    finalize_ranking_v2,
    TIER_DIRECT,
    TIER_RELATED,
    TIER_OTHER,
    GROUP_PRIMARY,
    GROUP_ALTERNATIVE,
    GROUPING_PRIMARY_ALTERNATIVE,
    GROUPING_FLAT,
)
from ranking_diagnostics import build_ranking_diagnostics


def _row(name, product_type, tags="", sub="", main="", score=0.5):
    return {
        "product_name": name, "product_type": product_type, "tags": tags,
        "features": "", "attributes": "", "sub_category": sub,
        "main_category": main, "semantic_score": score, "score": score,
    }


# ---------------------------------------------------------------------------
# has_explicit_axis / determine_result_grouping
# ---------------------------------------------------------------------------

def test_axis_true_for_problem():
    assert has_explicit_axis({"product_type": None}, "yağlı saç", set()) is True


def test_axis_true_for_product_type():
    assert has_explicit_axis({"product_type": "Şampuan"}, None, set()) is True


def test_axis_true_for_modifier():
    assert has_explicit_axis({"product_type": None}, None, {"kislik"}) is True


def test_axis_false_for_pure_browse():
    assert has_explicit_axis({"product_type": None}, None, set()) is False


def test_grouping_split_when_axis_and_direct_exist():
    g = determine_result_grouping({"product_type": "Şampuan"}, "yağlı saç", set(), direct_count=2)
    assert g == GROUPING_PRIMARY_ALTERNATIVE


def test_grouping_flat_when_no_axis():
    g = determine_result_grouping({"product_type": None}, None, set(), direct_count=0)
    assert g == GROUPING_FLAT


def test_grouping_flat_when_axis_but_no_direct():
    # Explicit axis but nothing actually matched it directly → no anchor → flat.
    g = determine_result_grouping({"product_type": "Şampuan"}, "yağlı saç", set(), direct_count=0)
    assert g == GROUPING_FLAT


# ---------------------------------------------------------------------------
# match_group_for
# ---------------------------------------------------------------------------

def test_match_group_split_mode():
    assert match_group_for(TIER_DIRECT, GROUPING_PRIMARY_ALTERNATIVE) == GROUP_PRIMARY
    assert match_group_for(TIER_RELATED, GROUPING_PRIMARY_ALTERNATIVE) == GROUP_ALTERNATIVE
    assert match_group_for(TIER_OTHER, GROUPING_PRIMARY_ALTERNATIVE) == GROUP_ALTERNATIVE


def test_match_group_flat_mode_all_primary():
    assert match_group_for(TIER_RELATED, GROUPING_FLAT) == GROUP_PRIMARY
    assert match_group_for(TIER_DIRECT, GROUPING_FLAT) == GROUP_PRIMARY


# ---------------------------------------------------------------------------
# build_ranking_diagnostics include_grouping wiring
# ---------------------------------------------------------------------------

def test_diagnostics_grouping_off_by_default():
    plan = ResponsePlan(mode=MODE_FOCUSED_SEARCH, user_problem="yağlı saç")
    df = pd.DataFrame([_row("Yağlı Saç Şampuanı", "Şampuan", tags="yağlı saç",
                            sub="Saç Bakımı", main="Kişisel Bakım")])
    parsed = {"product_type": "Şampuan", "sub_category": "Saç Bakımı",
              "main_category": "Kişisel Bakım", "features": []}
    diag = build_ranking_diagnostics(parsed, df, "yağlı saç için şampuan öner", plan)
    assert "result_grouping" not in diag
    assert "match_group" not in diag["products"][0]


def test_diagnostics_grouping_split_problem_query():
    plan = ResponsePlan(mode=MODE_FOCUSED_SEARCH, user_problem="yağlı saç")
    parsed = {"product_type": "Şampuan", "sub_category": "Saç Bakımı",
              "main_category": "Kişisel Bakım", "features": []}
    df = pd.DataFrame([
        _row("Yağlı Saç Şampuanı", "Şampuan", tags="yağlı saç",
             sub="Saç Bakımı", main="Kişisel Bakım", score=0.7),
        _row("Keratin Onarıcı Şampuan", "Şampuan", tags="onarıcı",
             sub="Saç Bakımı", main="Kişisel Bakım", score=0.9),
    ])
    diag = build_ranking_diagnostics(
        parsed, df, "yağlı saç için şampuan öner", plan, include_grouping=True
    )
    assert diag["result_grouping"] == GROUPING_PRIMARY_ALTERNATIVE
    groups = {p["name"]: p["match_group"] for p in diag["products"]}
    assert groups["Yağlı Saç Şampuanı"] == GROUP_PRIMARY
    assert groups["Keratin Onarıcı Şampuan"] == GROUP_ALTERNATIVE
    assert diag["primary_count"] == 1
    assert diag["alternative_count"] == 1


def test_compute_grouping_aligned_and_primary_first():
    # Pipeline view: finalize then group. Primaries must be contiguous at the
    # top, and the match_group list must align to the ordered rows.
    parsed = {"product_type": "Şampuan", "sub_category": "Saç Bakımı",
              "main_category": "Kişisel Bakım", "features": []}
    plan = ResponsePlan(mode=MODE_FOCUSED_SEARCH, user_problem="yağlı saç")
    df = pd.DataFrame([
        _row("Keratin Onarıcı Şampuan", "Şampuan", tags="onarıcı",
             sub="Saç Bakımı", main="Kişisel Bakım", score=0.95),
        _row("Yağlı Saç Şampuanı", "Şampuan", tags="yağlı saç",
             sub="Saç Bakımı", main="Kişisel Bakım", score=0.70),
        _row("Dökülme Karşıtı Şampuan", "Şampuan", tags="saç dökülmesi",
             sub="Saç Bakımı", main="Kişisel Bakım", score=0.60),
    ])
    ordered = finalize_ranking_v2(df, parsed, plan, "yağlı saç için şampuan öner", top_k=5)
    grouping, groups = compute_grouping(parsed, ordered, plan, "yağlı saç için şampuan öner")

    assert grouping == GROUPING_PRIMARY_ALTERNATIVE
    assert len(groups) == len(ordered)
    # The yağlı product is primary and leads.
    assert ordered["product_name"].tolist()[0] == "Yağlı Saç Şampuanı"
    assert groups[0] == GROUP_PRIMARY
    # All primaries precede all alternatives (no interleaving).
    first_alt = next((i for i, g in enumerate(groups) if g == GROUP_ALTERNATIVE), len(groups))
    assert all(g == GROUP_PRIMARY for g in groups[:first_alt])
    assert all(g == GROUP_ALTERNATIVE for g in groups[first_alt:])


def test_compute_grouping_empty():
    plan = ResponsePlan(mode=MODE_FOCUSED_SEARCH, user_problem=None)
    grouping, groups = compute_grouping({"product_type": None}, pd.DataFrame(), plan, "q")
    assert grouping == GROUPING_FLAT
    assert groups == []


def test_diagnostics_grouping_flat_for_browse():
    plan = ResponsePlan(mode=MODE_BROAD_SEARCH, user_problem=None)
    parsed = {"product_type": None, "sub_category": None,
              "main_category": "Kamp", "features": []}
    df = pd.DataFrame([
        _row("Çadır", "Çadır", sub="Barınma", main="Kamp", score=0.9),
        _row("Uyku Tulumu", "Uyku Tulumu", sub="Uyku", main="Kamp", score=0.8),
    ])
    diag = build_ranking_diagnostics(
        parsed, df, "kamp için ürün öner", plan, include_grouping=True
    )
    assert diag["result_grouping"] == GROUPING_FLAT
    # Flat mode → every product labelled primary (no alternative concept).
    assert all(p["match_group"] == GROUP_PRIMARY for p in diag["products"])
    assert diag["alternative_count"] == 0
