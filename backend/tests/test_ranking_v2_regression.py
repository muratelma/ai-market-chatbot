"""Regression locks for the V2 ranking path (finalize_ranking_v2).

These reproduce the real-catalog orderings observed in live Stage-3 validation,
using realistic multi-row scored pools (names/types/tags mirror the catalog).
They route through the ACTUAL V2 entry point — closing the gap that the eval /
manual harnesses bypass ``finalize_ranking_v2`` — and are deterministic
(no model, no DB, no Ollama), so they guard the ordering in CI.

If a future change to the tier rules or weights regresses one of the four
findings, one of these locks fails.
"""

import pandas as pd

from response_planner import ResponsePlan, MODE_FOCUSED_SEARCH, MODE_BROAD_SEARCH
from ranking_core import finalize_ranking_v2


def _row(name, product_type, tags="", features="", sub="", main="", score=0.5):
    return {
        "product_name": name,
        "product_type": product_type,
        "tags": tags,
        "features": features,
        "attributes": "",
        "sub_category": sub,
        "main_category": main,
        "semantic_score": score,
        "score": score,
    }


def _order(out):
    return out["product_name"].tolist()


# ---------------------------------------------------------------------------
# Finding 3 — "kamp için yemek yapacak bir şey lazım"
# Direct Kamp Ocağı must lead over the higher-scored semantic sibling.
# ---------------------------------------------------------------------------

def test_lock_kamp_ocagi_leads_over_mutfak_seti():
    parsed = {"product_type": "Kamp Ocağı", "sub_category": "Pişirme",
              "main_category": "Kamp", "features": []}
    plan = ResponsePlan(mode=MODE_FOCUSED_SEARCH, user_problem=None)
    df = pd.DataFrame([
        _row("Kamp Mutfak Seti 4 Parça", "Kamp Mutfak Seti", sub="Pişirme",
             main="Kamp", score=0.76),  # highest semantic, but NOT the type
        _row("Gazlı Kamp Ocağı", "Kamp Ocağı", sub="Pişirme", main="Kamp", score=0.70),
        _row("Kamp Ocağı Yüksek Güç 3500W", "Kamp Ocağı", sub="Pişirme",
             main="Kamp", score=0.68),
        _row("Kamp Ocağı Gazlı Kompakt", "Kamp Ocağı", sub="Pişirme",
             main="Kamp", score=0.61),
        _row("Katlanır Kamp Bardağı", "Kamp Bardağı", sub="Mutfak", main="Kamp",
             score=0.73),
    ])
    order = _order(finalize_ranking_v2(
        df, parsed, plan, "kamp için yemek yapacak bir şey lazım", top_k=5
    ))
    # Three Kamp Ocağı lead; the higher-scored Mutfak Seti is demoted below them.
    assert order[:3] == [
        "Gazlı Kamp Ocağı",
        "Kamp Ocağı Yüksek Güç 3500W",
        "Kamp Ocağı Gazlı Kompakt",
    ]
    assert order.index("Gazlı Kamp Ocağı") < order.index("Kamp Mutfak Seti 4 Parça")


# ---------------------------------------------------------------------------
# Finding 2 — "kışlık elbise öner"
# Seasonal modifier match must lead over higher-scored off-season dresses.
# ---------------------------------------------------------------------------

def test_lock_kislik_dress_leads_over_yazlik():
    parsed = {"product_type": None, "sub_category": "Elbise",
              "main_category": "Giyim", "features": []}
    plan = ResponsePlan(mode=MODE_FOCUSED_SEARCH, user_problem=None)
    df = pd.DataFrame([
        _row("Kadın Günlük Midi Elbise", "Midi Elbise", sub="Elbise",
             main="Giyim", score=0.46),
        _row("Kadın Çiçekli Elbise", "Yazlık Elbise", tags="yazlık,çiçekli",
             sub="Elbise", main="Giyim", score=0.45),
        _row("Kadın Kışlık Triko Elbise", "Triko Elbise", tags="kışlık,triko",
             sub="Elbise", main="Giyim", score=0.45),  # lower score, but direct
        _row("Kadın Yazlık Mini Elbise", "Mini Elbise", tags="yazlık",
             sub="Elbise", main="Giyim", score=0.44),
    ])
    order = _order(finalize_ranking_v2(
        df, parsed, plan, "kışlık elbise öner", top_k=5
    ))
    assert order[0] == "Kadın Kışlık Triko Elbise"


# ---------------------------------------------------------------------------
# Finding 1 — "yağlı saç için şampuan öner"
# Problem-matched şampuanlar must lead over a higher-scored generic şampuan.
# ---------------------------------------------------------------------------

def test_lock_yagli_sampuan_leads_over_generic():
    parsed = {"product_type": "Şampuan", "sub_category": "Saç Bakımı",
              "main_category": "Kişisel Bakım", "features": []}
    plan = ResponsePlan(mode=MODE_FOCUSED_SEARCH, user_problem="yağlı saç")
    df = pd.DataFrame([
        _row("Keratin Onarıcı Şampuan", "Şampuan", tags="onarıcı,keratin",
             sub="Saç Bakımı", main="Kişisel Bakım", score=0.95),  # highest
        _row("Dökülme Karşıtı Şampuan", "Şampuan", tags="saç dökülmesi",
             sub="Saç Bakımı", main="Kişisel Bakım", score=0.90),
        _row("Yağlı Saç Dengeleyici Şampuan", "Şampuan", tags="yağlı saç,dengeleyici",
             sub="Saç Bakımı", main="Kişisel Bakım", score=0.69),
        _row("Yağlı Saç Şampuanı", "Şampuan", tags="yağlı saç,yağlanma",
             sub="Saç Bakımı", main="Kişisel Bakım", score=0.65),
    ])
    order = _order(finalize_ranking_v2(
        df, parsed, plan, "yağlı saç için şampuan öner", top_k=5
    ))
    assert order[:2] == ["Yağlı Saç Dengeleyici Şampuan", "Yağlı Saç Şampuanı"]
    # The two yağlı products precede every generic same-type şampuan.
    assert order.index("Yağlı Saç Şampuanı") < order.index("Keratin Onarıcı Şampuan")
    assert order.index("Yağlı Saç Şampuanı") < order.index("Dökülme Karşıtı Şampuan")


# ---------------------------------------------------------------------------
# Finding 4 — "saç dökülmesi için ürün öner" (problem_broad)
# Direct problem matches form a contiguous lead block; a higher-scored
# non-direct item is demoted to the diversified tail.
# ---------------------------------------------------------------------------

def test_lock_dokulme_problem_broad_direct_block_leads():
    parsed = {"product_type": None, "sub_category": "Saç Bakımı",
              "main_category": "Kişisel Bakım", "features": []}
    plan = ResponsePlan(mode=MODE_BROAD_SEARCH, user_problem="saç dökülmesi")
    df = pd.DataFrame([
        _row("Hassas Saç Derisi Yatıştırıcı Tonik", "Saç Toniği",
             tags="hassas,yatıştırıcı", sub="Saç Bakımı", main="Kişisel Bakım",
             score=0.95),  # highest score, but NOT a dökülme product
        _row("Dökülme Karşıtı Şampuan", "Şampuan", tags="saç dökülmesi",
             sub="Saç Bakımı", main="Kişisel Bakım", score=0.70),
        _row("Saç Dökülmesine Karşı Serum", "Saç Serumu", tags="saç dökülmesi",
             sub="Saç Bakımı", main="Kişisel Bakım", score=0.73),
        _row("Saç Dökülmesi Losyonu", "Saç Losyonu", tags="saç dökülmesi",
             sub="Saç Bakımı", main="Kişisel Bakım", score=0.60),
    ])
    order = _order(finalize_ranking_v2(
        df, parsed, plan, "saç dökülmesi için ürün öner", top_k=5
    ))
    dokulme = {"Dökülme Karşıtı Şampuan", "Saç Dökülmesine Karşı Serum",
               "Saç Dökülmesi Losyonu"}
    # All three dökülme products lead; the high-scored tonik is in the tail.
    assert set(order[:3]) == dokulme
    assert order[-1] == "Hassas Saç Derisi Yatıştırıcı Tonik"


# ---------------------------------------------------------------------------
# Opposite-problem regression — "yağlı saç için şampuan öner"
# A product for the OPPOSITE problem ("Kuru Saçlar İçin ... Şampuan") must be
# demoted below neutral same-type siblings so it never surfaces as a visible
# alternative ahead of them, even when its semantic score is higher.
# ---------------------------------------------------------------------------

def test_lock_yagli_demotes_opposite_kuru_below_neutral():
    parsed = {"product_type": "Şampuan", "sub_category": "Saç Bakımı",
              "main_category": "Kişisel Bakım", "features": []}
    plan = ResponsePlan(mode=MODE_FOCUSED_SEARCH, user_problem="yağlı saç")
    df = pd.DataFrame([
        _row("Yağlı Saç Dengeleyici Şampuan", "Şampuan", tags="yağlı saç,dengeleyici",
             sub="Saç Bakımı", main="Kişisel Bakım", score=0.70),
        _row("Yağlı Saç Şampuanı", "Şampuan", tags="yağlı saç,yağlanma",
             sub="Saç Bakımı", main="Kişisel Bakım", score=0.66),
        _row("Kuru Saçlar İçin Avokadolu Şampuan", "Şampuan", tags="kuru saç,avokado",
             sub="Saç Bakımı", main="Kişisel Bakım", score=0.82),  # high score, WRONG problem
        _row("Dökülme Karşıtı Şampuan", "Şampuan", tags="saç dökülmesi",
             sub="Saç Bakımı", main="Kişisel Bakım", score=0.60),  # neutral sibling
    ])
    order = _order(finalize_ranking_v2(
        df, parsed, plan, "yağlı saç için şampuan öner", top_k=5
    ))
    # Both yağlı products lead (DIRECT), and the opposite-problem kuru product is
    # demoted below the neutral şampuan despite its higher semantic score.
    assert order[:2] == ["Yağlı Saç Dengeleyici Şampuan", "Yağlı Saç Şampuanı"]
    assert order.index("Dökülme Karşıtı Şampuan") < order.index("Kuru Saçlar İçin Avokadolu Şampuan")
    assert order[-1] == "Kuru Saçlar İçin Avokadolu Şampuan"


def test_lock_yagli_kuru_sampuan_type_not_demoted():
    """A yağlı-saç product whose *type* is "Kuru Şampuan" (dry shampoo) must stay
    DIRECT — the opposite-problem rule keys on "kuru saç", not the word "kuru"."""
    parsed = {"product_type": None, "sub_category": "Saç Bakımı",
              "main_category": "Kişisel Bakım", "features": []}
    plan = ResponsePlan(mode=MODE_BROAD_SEARCH, user_problem="yağlı saç")
    df = pd.DataFrame([
        _row("Yağlı Saçlar İçin Kuru Şampuan", "Kuru Şampuan",
             tags="yağlı saç,kuru şampuan,yağlanma", sub="Saç Bakımı",
             main="Kişisel Bakım", score=0.60),
        _row("Kuru Saçlar İçin Avokadolu Şampuan", "Şampuan", tags="kuru saç,avokado",
             sub="Saç Bakımı", main="Kişisel Bakım", score=0.85),
    ])
    out = finalize_ranking_v2(
        df, parsed, plan, "yağlı saç için ürün öner", top_k=5
    )
    order = _order(out)
    # The yağlı dry-shampoo leads; the opposite kuru-hair product trails it.
    assert order[0] == "Yağlı Saçlar İçin Kuru Şampuan"


# ---------------------------------------------------------------------------
# Negative-constraint regression — "kışlık kadın elbisesi ... mont/kaban değil"
# After exclusion the pool is Elbise-only; the seasonal "kışlık" modifier must
# float the kışlık/triko elbise to the top (DIRECT), with the other dresses as
# alternatives. Mont/Kaban are removed upstream (filter_excluded), so the
# ordering here only needs to prove the modifier preference among dresses.
# ---------------------------------------------------------------------------

def test_lock_kislik_elbise_modifier_leads_among_dresses():
    parsed = {"product_type": None, "sub_category": "Elbise",
              "main_category": "Giyim", "features": []}
    plan = ResponsePlan(mode=MODE_FOCUSED_SEARCH, user_problem=None)
    df = pd.DataFrame([
        _row("Kadın Yazlık Elbise", "Yazlık Elbise", tags="kadın,elbise,yaz",
             sub="Elbise", main="Giyim", score=0.80),  # highest semantic
        _row("Kadın Kışlık Triko Elbise", "Triko Elbise",
             tags="kadın,triko,elbise,kış,sıcak", features="triko,sıcak,kışlık",
             sub="Elbise", main="Giyim", score=0.66),
        _row("Kadın Mini Elbise", "Mini Elbise", tags="kadın,mini,elbise",
             sub="Elbise", main="Giyim", score=0.72),
    ])
    out = finalize_ranking_v2(
        df, parsed, plan,
        "kışlık kadın elbisesi önerir misin mont veya kaban değil elbise arıyorum",
        top_k=5,
    )
    order = _order(out)
    # The kışlık/triko dress leads despite its lower semantic score.
    assert order[0] == "Kadın Kışlık Triko Elbise"
    # No outerwear is present (and none should be).
    assert all("Mont" not in pt and "Kaban" not in pt for pt in out["product_type"])
