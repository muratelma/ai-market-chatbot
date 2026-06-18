"""Deterministic tests for search_engine.apply_filters.

Covers the price strict-filter and the enforce_explicit_category branch — the
deterministic core of the "seasonal modifier + explicit category" behavior
(e.g. "kışlık elbise" must stay within Elbise instead of drifting to a sibling
category). No embeddings/model/DB involved.
"""
import pandas as pd

from search_engine import apply_filters, filter_excluded


def _catalog():
    # 12 Giyim rows: 3 Elbise + 9 Mont. Small enough that category narrowing
    # yields < 10 rows, which is what triggers the enforce_explicit_category path.
    rows = []
    for i in range(3):
        rows.append(("Elbise %d" % i, "Giyim", "Elbise", "Kadın", "Abiye", 500 + i))
    for i in range(9):
        rows.append(("Mont %d" % i, "Giyim", "Dış Giyim", "Kadın", "Mont", 800 + i))
    return pd.DataFrame(
        rows,
        columns=["product_name", "main_category", "sub_category", "target_group",
                 "product_type", "price"],
    )


def _parsed(**overrides):
    base = {
        "min_price": None,
        "max_price": None,
        "target_group": None,
        "main_category": None,
        "sub_category": None,
        "product_type": None,
    }
    base.update(overrides)
    return base


def test_price_is_strict_filter():
    df = _catalog()
    out = apply_filters(df, _parsed(max_price=501))
    assert len(out) == 2  # Elbise 0 (500) and Elbise 1 (501); 502 excluded
    assert set(out["product_name"]) == {"Elbise 0", "Elbise 1"}


def test_enforce_explicit_category_keeps_named_subcategory():
    df = _catalog()
    parsed = _parsed(main_category="Giyim", sub_category="Elbise")

    enforced = apply_filters(df, parsed, enforce_explicit_category=True)
    assert len(enforced) == 3
    assert set(enforced["sub_category"]) == {"Elbise"}


def test_without_enforce_falls_back_to_broader_pool():
    df = _catalog()
    parsed = _parsed(main_category="Giyim", sub_category="Elbise")

    # Narrowed pool is < 10, and without enforcement apply_filters widens back
    # to the broader (price-filtered) base pool rather than the 3 Elbise rows.
    default = apply_filters(df, parsed, enforce_explicit_category=False)
    assert len(default) == len(df)


def test_enforce_explicit_category_keeps_pool_in_sub():
    df = _catalog()
    # Explicit dress intent with a small pool: enforcement must keep the pool in
    # sub_category "Elbise" instead of widening to the whole catalog (which would
    # let warmth-driven Mont/Kaban back in).
    parsed = _parsed(main_category="Giyim", sub_category="Elbise")
    out = apply_filters(df, parsed, enforce_explicit_category=True)
    assert set(out["sub_category"]) == {"Elbise"}
    assert "Mont" not in set(out["sub_category"])


def test_filter_excluded_removes_rejected_subcategory():
    df = _catalog()
    out = filter_excluded(df, {"mont"})
    # All 9 Mont sub_category rows dropped; the 3 Elbise rows remain.
    assert set(out["sub_category"]) == {"Elbise"}
    assert len(out) == 3


def test_filter_excluded_safety_net_keeps_pool_when_exclusion_empties_it():
    df = _catalog()
    # Excluding every category present would empty the pool — the safety net
    # returns the original frame instead of zero results.
    out = filter_excluded(df, {"elbise", "mont"})
    assert len(out) == len(df)


def test_apply_filters_drops_excluded_before_broad_fallback():
    df = _catalog()
    # The negative constraint must hold even when the broad fallback would
    # otherwise widen back to the whole catalog: no Mont may survive.
    parsed = _parsed(main_category="Giyim", sub_category="Elbise",
                     excluded_terms=["mont"])
    out = apply_filters(df, parsed, enforce_explicit_category=False)
    assert "Mont" not in set(out["product_type"])
    assert set(out["sub_category"]) == {"Elbise"}


# ---------------------------------------------------------------------------
# detect_unavailable_category — deterministic substitution signal
# ---------------------------------------------------------------------------
from search_engine import detect_unavailable_category


def _results(*rows):
    # rows: (product_name, main_category, sub_category, product_type)
    return pd.DataFrame(
        [(n, mc, sc, pt) for (n, mc, sc, pt) in rows],
        columns=["product_name", "main_category", "sub_category", "product_type"],
    )


def _parsed_intent(**explicit):
    return {"explicit_intent": dict(explicit)}


def test_unavailable_category_flags_relaxed_subcategory():
    # User explicitly asked for "Çanta"; the price filter forced a fallback to
    # clothing/footwear, so no result is a bag -> the request is unavailable.
    df = _results(
        ("Kadın Uzun Kaban", "Giyim", "Üst Giyim", "Kaban"),
        ("Kadın Kışlık Bot", "Ayakkabı", "Bot", "Bot"),
    )
    assert detect_unavailable_category(_parsed_intent(sub_category="Çanta"), df) == "Çanta"


def test_unavailable_category_none_when_request_is_covered():
    # Bags are present -> no substitution, nothing to disclose.
    df = _results(
        ("El Çantası Deri Kadın", "Aksesuar", "Çanta", "El Çantası"),
        ("Kadın Omuz Çantası", "Aksesuar", "Çanta", "Omuz Çantası"),
    )
    assert detect_unavailable_category(_parsed_intent(sub_category="Çanta"), df) is None


def test_unavailable_category_matches_product_type_by_contains():
    df = _results(("Deri Omuz Çantası", "Aksesuar", "Çanta", "Omuz Çantası"))
    # Requested product_type "Çanta" is contained in "Omuz Çantası" -> covered.
    assert detect_unavailable_category(_parsed_intent(product_type="Çanta"), df) is None


def test_unavailable_category_ignores_inferred_only_categories():
    # Nothing user-typed (empty explicit_intent) -> never flag, even if the
    # inferred parsed category differs from results.
    df = _results(("Kadın Uzun Kaban", "Giyim", "Üst Giyim", "Kaban"))
    assert detect_unavailable_category({"explicit_intent": {}}, df) is None
    assert detect_unavailable_category({}, df) is None


def test_unavailable_category_none_for_empty_results():
    assert detect_unavailable_category(_parsed_intent(sub_category="Çanta"), _results()) is None
