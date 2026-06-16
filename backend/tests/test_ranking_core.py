"""Deterministic unit tests for ranking_core (Stage 2 directness tiering).

No DB, no Ollama, no embeddings — pure functions over dict/DataFrame fixtures.
Each test maps to one of the four live-diagnostics findings the stage targets.
"""

import pandas as pd

from response_planner import (
    ResponsePlan,
    MODE_FOCUSED_SEARCH,
    MODE_BROAD_SEARCH,
)
from search_engine import diversify_results
from ranking_core import (
    extract_query_modifiers,
    assign_directness_tier,
    finalize_ranking_v2,
    TIER_DIRECT,
    TIER_RELATED,
    TIER_OTHER,
)


def _row(name, product_type, tags="", features="", sub="", main="",
         semantic=0.5, score=0.5, attributes=""):
    return {
        "product_name": name,
        "product_type": product_type,
        "tags": tags,
        "features": features,
        "attributes": attributes,
        "sub_category": sub,
        "main_category": main,
        "semantic_score": semantic,
        "score": score,
    }


def _df(rows):
    return pd.DataFrame(rows)


def _names(df):
    return df["product_name"].tolist()


# ---------------------------------------------------------------------------
# extract_query_modifiers
# ---------------------------------------------------------------------------

def test_modifiers_seasonal():
    assert "kislik" in extract_query_modifiers("kışlık elbise öner")


def test_modifiers_material():
    mods = extract_query_modifiers("triko kazak arıyorum")
    assert "triko" in mods


def test_modifiers_none_for_plain_query():
    assert extract_query_modifiers("yağlı saç için şampuan öner") == set()


# ---------------------------------------------------------------------------
# assign_directness_tier — Finding 1 (problem present)
# ---------------------------------------------------------------------------

def test_tier_problem_match_is_direct():
    parsed = {"product_type": "Şampuan", "sub_category": "Saç Bakımı",
              "main_category": "Kişisel Bakım", "features": []}
    yagli = _row("Yağlı Saç Şampuanı", "Şampuan", tags="yağlı saç,şampuan",
                 sub="Saç Bakımı", main="Kişisel Bakım")
    tier, _ = assign_directness_tier(parsed, yagli, "yağlı saç", set())
    assert tier == TIER_DIRECT


def test_tier_exact_type_without_problem_is_related():
    # Same product_type but NOT the stated problem → must be RELATED, not DIRECT.
    parsed = {"product_type": "Şampuan", "sub_category": "Saç Bakımı",
              "main_category": "Kişisel Bakım", "features": []}
    generic = _row("Keratin Onarıcı Şampuan", "Şampuan", tags="onarıcı,keratin",
                   sub="Saç Bakımı", main="Kişisel Bakım")
    tier, _ = assign_directness_tier(parsed, generic, "yağlı saç", set())
    assert tier == TIER_RELATED


# ---------------------------------------------------------------------------
# assign_directness_tier — Findings 2 & 3 (product_type / modifiers)
# ---------------------------------------------------------------------------

def test_tier_exact_product_type_is_direct():
    parsed = {"product_type": "Kamp Ocağı", "sub_category": "Pişirme",
              "main_category": "Kamp", "features": []}
    ocak = _row("Gazlı Kamp Ocağı", "Kamp Ocağı", sub="Pişirme", main="Kamp")
    seti = _row("Kamp Mutfak Seti", "Kamp Mutfak Seti", sub="Pişirme", main="Kamp")
    assert assign_directness_tier(parsed, ocak, None, set())[0] == TIER_DIRECT
    assert assign_directness_tier(parsed, seti, None, set())[0] == TIER_OTHER


def test_tier_modifier_match_is_direct_without_product_type():
    parsed = {"product_type": None, "sub_category": "Elbise",
              "main_category": "Giyim", "features": []}
    mods = extract_query_modifiers("kışlık elbise öner")
    kislik = _row("Kadın Kışlık Triko Elbise", "Triko Elbise",
                  tags="kışlık,triko", sub="Elbise", main="Giyim")
    yazlik = _row("Kadın Yazlık Elbise", "Yazlık Elbise",
                  tags="yazlık,çiçekli", sub="Elbise", main="Giyim")
    assert assign_directness_tier(parsed, kislik, None, mods)[0] == TIER_DIRECT
    assert assign_directness_tier(parsed, yazlik, None, mods)[0] == TIER_RELATED


# ---------------------------------------------------------------------------
# finalize_ranking_v2 — ordering invariants
# ---------------------------------------------------------------------------

def test_finalize_problem_beats_higher_scored_generic():
    # Finding 1: yağlı (problem) must lead even though the generic scores higher.
    parsed = {"product_type": "Şampuan", "sub_category": "Saç Bakımı",
              "main_category": "Kişisel Bakım", "features": []}
    plan = ResponsePlan(mode=MODE_FOCUSED_SEARCH, user_problem="yağlı saç")
    df = _df([
        _row("Keratin Onarıcı Şampuan", "Şampuan", tags="onarıcı",
             sub="Saç Bakımı", main="Kişisel Bakım", score=0.95),
        _row("Yağlı Saç Şampuanı", "Şampuan", tags="yağlı saç,dengeleyici",
             sub="Saç Bakımı", main="Kişisel Bakım", score=0.70),
    ])
    out = finalize_ranking_v2(df, parsed, plan, "yağlı saç için şampuan öner", top_k=5)
    assert _names(out)[0] == "Yağlı Saç Şampuanı"


def test_finalize_exact_type_beats_semantic_sibling():
    # Finding 3: Kamp Ocağı (exact type) outranks higher-scored Kamp Mutfak Seti.
    parsed = {"product_type": "Kamp Ocağı", "sub_category": "Pişirme",
              "main_category": "Kamp", "features": []}
    plan = ResponsePlan(mode=MODE_FOCUSED_SEARCH, user_problem=None)
    df = _df([
        _row("Kamp Mutfak Seti", "Kamp Mutfak Seti", sub="Pişirme", main="Kamp",
             score=1.14),
        _row("Gazlı Kamp Ocağı", "Kamp Ocağı", sub="Pişirme", main="Kamp",
             score=1.08),
    ])
    out = finalize_ranking_v2(df, parsed, plan, "kamp için yemek yapacak bir şey", top_k=5)
    assert _names(out)[0] == "Gazlı Kamp Ocağı"


def test_finalize_modifier_beats_higher_scored_offseason():
    # Finding 2: kışlık/triko dress leads over a higher-scored yazlık dress.
    parsed = {"product_type": None, "sub_category": "Elbise",
              "main_category": "Giyim", "features": []}
    plan = ResponsePlan(mode=MODE_FOCUSED_SEARCH, user_problem=None)
    df = _df([
        _row("Kadın Yazlık Elbise", "Yazlık Elbise", tags="yazlık",
             sub="Elbise", main="Giyim", score=0.90),
        _row("Kadın Kışlık Triko Elbise", "Triko Elbise", tags="kışlık,triko",
             sub="Elbise", main="Giyim", score=0.80),
    ])
    out = finalize_ranking_v2(df, parsed, plan, "kışlık elbise öner", top_k=5)
    assert _names(out)[0] == "Kadın Kışlık Triko Elbise"


def test_finalize_problem_broad_direct_block_leads_then_tail():
    # Finding 4: direct problem matches form a contiguous lead block; a
    # higher-scored non-direct item is pushed into the diversified tail.
    parsed = {"product_type": None, "sub_category": "Saç Bakımı",
              "main_category": "Kişisel Bakım", "features": []}
    plan = ResponsePlan(mode=MODE_BROAD_SEARCH, user_problem="saç dökülmesi")
    df = _df([
        _row("Dökülme Karşıtı Şampuan", "Şampuan", tags="saç dökülmesi",
             sub="Saç Bakımı", main="Kişisel Bakım", score=0.70),
        _row("Hassas Saç Toniği", "Saç Toniği", tags="hassas,yatıştırıcı",
             sub="Saç Bakımı", main="Kişisel Bakım", score=0.95),  # highest score
        _row("Dökülmeye Karşı Serum", "Saç Serumu", tags="saç dökülmesi",
             sub="Saç Bakımı", main="Kişisel Bakım", score=0.60),
    ])
    out = finalize_ranking_v2(df, parsed, plan, "saç dökülmesi için ürün öner", top_k=5)
    names = _names(out)
    # Both dökülme products lead; the high-scored tonik is demoted to the tail.
    assert names[0] == "Dökülme Karşıtı Şampuan"
    assert names[1] == "Dökülmeye Karşı Serum"
    assert names[2] == "Hassas Saç Toniği"


def test_finalize_browse_broad_is_identical_to_diversify():
    # Constraint: browse diversity must be preserved exactly (no tiering).
    parsed = {"product_type": None, "sub_category": None,
              "main_category": "Kamp", "features": []}
    plan = ResponsePlan(mode=MODE_BROAD_SEARCH, user_problem=None)
    rows = [
        _row("Çadır", "Çadır", sub="Barınma", main="Kamp", score=0.90),
        _row("Uyku Tulumu", "Uyku Tulumu", sub="Uyku", main="Kamp", score=0.88),
        _row("Kamp Sandalyesi", "Kamp Sandalyesi", sub="Mobilya", main="Kamp", score=0.86),
        _row("İkinci Çadır", "Çadır", sub="Barınma", main="Kamp", score=0.84),
        _row("Kamp Feneri", "Kamp Feneri", sub="Aydınlatma", main="Kamp", score=0.82),
    ]
    expected = diversify_results(_df(rows), top_k=3)
    actual = finalize_ranking_v2(_df(rows), parsed, plan, "kamp için ürün öner", top_k=3)
    assert _names(actual) == _names(expected)


def test_finalize_empty_passthrough():
    parsed = {"product_type": None, "sub_category": None, "main_category": None,
              "features": []}
    plan = ResponsePlan(mode=MODE_FOCUSED_SEARCH, user_problem=None)
    out = finalize_ranking_v2(pd.DataFrame(), parsed, plan, "q", top_k=5)
    assert out.empty
