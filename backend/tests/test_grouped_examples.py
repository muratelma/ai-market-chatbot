"""Stage 7 — grouped-ranking locks for the named focused examples.

Runs the real pipeline tail (finalize_ranking_v2 → compute_grouping) on
realistic catalog-shaped pools and asserts the result_grouping decision plus
which products land in the primary group. Deterministic: no model, DB, Ollama.

Covers exactly the queries called out for Stage 7:
  * kışlık elbise öner
  * yağlı saç için ürün öner
  * yağlı saç için şampuan öner
  * saç dökülmesi için ürün öner
  * kamp için yemek yapacak bir şey lazım
plus the guard that a broad browse ("ayakkabı öner") stays flat.
"""

import pandas as pd

from response_planner import ResponsePlan, MODE_FOCUSED_SEARCH, MODE_BROAD_SEARCH
from ranking_core import (
    finalize_ranking_v2,
    compute_grouping,
    GROUPING_PRIMARY_ALTERNATIVE,
    GROUPING_FLAT,
)


def _row(name, product_type, tags="", sub="", main="", score=0.5):
    return {
        "product_name": name, "product_type": product_type, "tags": tags,
        "features": "", "attributes": "", "sub_category": sub,
        "main_category": main, "semantic_score": score, "score": score,
    }


def _run(df, parsed, plan, query):
    """Pipeline tail: order then group. Returns (grouping, primary, alternative)."""
    ordered = finalize_ranking_v2(df, parsed, plan, query, top_k=5)
    grouping, groups = compute_grouping(parsed, ordered, plan, query)
    names = ordered["product_name"].tolist()
    primary = [n for n, g in zip(names, groups) if g == "primary"]
    alternative = [n for n, g in zip(names, groups) if g == "alternative"]
    return grouping, primary, alternative


def test_kislik_elbise_oner_splits_kislik_primary():
    parsed = {"product_type": None, "sub_category": "Elbise",
              "main_category": "Giyim", "features": []}
    plan = ResponsePlan(mode=MODE_FOCUSED_SEARCH, user_problem=None)
    df = pd.DataFrame([
        _row("Kadın Çiçekli Elbise", "Yazlık Elbise", tags="yazlık", sub="Elbise", main="Giyim", score=0.46),
        _row("Kadın Kışlık Triko Elbise", "Triko Elbise", tags="kışlık,triko", sub="Elbise", main="Giyim", score=0.45),
        _row("Kadın Yazlık Mini Elbise", "Mini Elbise", tags="yazlık", sub="Elbise", main="Giyim", score=0.44),
    ])
    grouping, primary, alternative = _run(df, parsed, plan, "kışlık elbise öner")
    assert grouping == GROUPING_PRIMARY_ALTERNATIVE
    assert primary == ["Kadın Kışlık Triko Elbise"]
    assert "Kadın Çiçekli Elbise" in alternative


def test_yagli_sac_icin_urun_oner_splits_yagli_primary():
    parsed = {"product_type": None, "sub_category": "Saç Bakımı",
              "main_category": "Kişisel Bakım", "features": []}
    plan = ResponsePlan(mode=MODE_BROAD_SEARCH, user_problem="yağlı saç")
    df = pd.DataFrame([
        _row("Yağlı Saç Şampuanı", "Şampuan", tags="yağlı saç", sub="Saç Bakımı", main="Kişisel Bakım", score=0.70),
        _row("Saç Dökülmesine Karşı Serum", "Saç Serumu", tags="saç dökülmesi", sub="Saç Bakımı", main="Kişisel Bakım", score=0.73),
        _row("Yağ Dengeleyici Saç Maskesi", "Saç Maskesi", tags="yağlı saç", sub="Saç Bakımı", main="Kişisel Bakım", score=0.65),
    ])
    grouping, primary, alternative = _run(df, parsed, plan, "yağlı saç için ürün öner")
    assert grouping == GROUPING_PRIMARY_ALTERNATIVE
    assert set(primary) == {"Yağlı Saç Şampuanı", "Yağ Dengeleyici Saç Maskesi"}
    assert alternative == ["Saç Dökülmesine Karşı Serum"]


def test_yagli_sac_icin_sampuan_oner_generic_is_alternative():
    parsed = {"product_type": "Şampuan", "sub_category": "Saç Bakımı",
              "main_category": "Kişisel Bakım", "features": []}
    plan = ResponsePlan(mode=MODE_FOCUSED_SEARCH, user_problem="yağlı saç")
    df = pd.DataFrame([
        _row("Keratin Onarıcı Şampuan", "Şampuan", tags="onarıcı", sub="Saç Bakımı", main="Kişisel Bakım", score=0.95),
        _row("Yağlı Saç Dengeleyici Şampuan", "Şampuan", tags="yağlı saç", sub="Saç Bakımı", main="Kişisel Bakım", score=0.69),
    ])
    grouping, primary, alternative = _run(df, parsed, plan, "yağlı saç için şampuan öner")
    assert grouping == GROUPING_PRIMARY_ALTERNATIVE
    # product_type match alone must NOT make the generic şampuan primary.
    assert primary == ["Yağlı Saç Dengeleyici Şampuan"]
    assert alternative == ["Keratin Onarıcı Şampuan"]


def test_sac_dokulmesi_icin_urun_oner_dokulme_primary():
    parsed = {"product_type": None, "sub_category": "Saç Bakımı",
              "main_category": "Kişisel Bakım", "features": []}
    plan = ResponsePlan(mode=MODE_BROAD_SEARCH, user_problem="saç dökülmesi")
    df = pd.DataFrame([
        _row("Hassas Saç Toniği", "Saç Toniği", tags="hassas", sub="Saç Bakımı", main="Kişisel Bakım", score=0.95),
        _row("Dökülme Karşıtı Şampuan", "Şampuan", tags="saç dökülmesi", sub="Saç Bakımı", main="Kişisel Bakım", score=0.70),
        _row("Saç Dökülmesi Losyonu", "Saç Losyonu", tags="saç dökülmesi", sub="Saç Bakımı", main="Kişisel Bakım", score=0.60),
    ])
    grouping, primary, alternative = _run(df, parsed, plan, "saç dökülmesi için ürün öner")
    assert grouping == GROUPING_PRIMARY_ALTERNATIVE
    assert set(primary) == {"Dökülme Karşıtı Şampuan", "Saç Dökülmesi Losyonu"}
    # The higher-scored non-dökülme tonik is demoted to an alternative.
    assert alternative == ["Hassas Saç Toniği"]


def test_kamp_yemek_kamp_ocagi_primary():
    parsed = {"product_type": "Kamp Ocağı", "sub_category": "Pişirme",
              "main_category": "Kamp", "features": []}
    plan = ResponsePlan(mode=MODE_FOCUSED_SEARCH, user_problem=None)
    df = pd.DataFrame([
        _row("Kamp Mutfak Seti 4 Parça", "Kamp Mutfak Seti", sub="Pişirme", main="Kamp", score=0.76),
        _row("Gazlı Kamp Ocağı", "Kamp Ocağı", sub="Pişirme", main="Kamp", score=0.70),
        _row("Kamp Ocağı Yüksek Güç", "Kamp Ocağı", sub="Pişirme", main="Kamp", score=0.68),
    ])
    grouping, primary, alternative = _run(df, parsed, plan, "kamp için yemek yapacak bir şey lazım")
    assert grouping == GROUPING_PRIMARY_ALTERNATIVE
    assert primary == ["Gazlı Kamp Ocağı", "Kamp Ocağı Yüksek Güç"]
    assert alternative == ["Kamp Mutfak Seti 4 Parça"]


def test_ayakkabi_oner_stays_flat():
    # Broad browse, no explicit problem/type/modifier axis → must NOT split.
    parsed = {"product_type": None, "sub_category": None,
              "main_category": "Ayakkabı", "features": []}
    plan = ResponsePlan(mode=MODE_BROAD_SEARCH, user_problem=None)
    df = pd.DataFrame([
        _row("Erkek Spor Sneaker", "Sneaker", sub="Sneaker", main="Ayakkabı", score=0.55),
        _row("Kadın Spor Sneaker", "Sneaker", sub="Sneaker", main="Ayakkabı", score=0.54),
        _row("Çocuk Spor Sneaker", "Çocuk Sneaker", sub="Sneaker", main="Ayakkabı", score=0.53),
    ])
    grouping, primary, alternative = _run(df, parsed, plan, "ayakkabı öner")
    assert grouping == GROUPING_FLAT
    assert alternative == []
    assert len(primary) == 3
