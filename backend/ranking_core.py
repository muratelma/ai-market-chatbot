"""
Core ranking (Stage 2).

Re-orders the FINAL, already-scored search result so direct-intent matches lead,
using a discrete *directness tier* as the primary sort key and the existing
blended ``score`` as the within-tier tiebreak.  Tiering only re-orders results
that the search already produced — it never drops candidates, never re-scores,
and never touches the source DataFrame or its embeddings (the embedding/order
contract is about the catalog df, not the post-search result df).

All behaviour here is gated upstream by ``config.RANKING_V2_ENABLED``; when the
flag is off, ``main.py`` keeps the legacy diversify/head ordering and never calls
``finalize_ranking_v2``.

This module is the foundation layer: pure functions, no Ollama, no DB.
``ranking_diagnostics`` (the observe-only layer) imports from here, not the other
way around.
"""

from __future__ import annotations

import pandas as pd

from query_parser import normalize_text_for_match, contains_phrase, product_type_overlap
from response_planner import MODE_FOCUSED_SEARCH, MODE_BROAD_SEARCH
from search_engine import diversify_results


# ---------------------------------------------------------------------------
# Diversification regimes
# ---------------------------------------------------------------------------

REGIME_FOCUSED = "focused"              # explicit product_type / sub_category → narrow
REGIME_PROBLEM_BROAD = "problem_broad"  # broad_search + a stated user_problem
REGIME_BROWSE_BROAD = "browse_broad"    # broad_search, pure category browse
REGIME_NONE = "none"                    # not a product-search ordering context


# ---------------------------------------------------------------------------
# Directness tiers (primary sort key)
# ---------------------------------------------------------------------------

TIER_DIRECT = 2     # directly answers the user's explicit intent
TIER_RELATED = 1    # same type/category/area but not the explicit need
TIER_OTHER = 0      # neither


# ---------------------------------------------------------------------------
# Primary / alternative grouping (Stage 4 — labels derived from the tier)
# ---------------------------------------------------------------------------

GROUP_PRIMARY = "primary"            # "En uygun ürünler"
GROUP_ALTERNATIVE = "alternative"    # "İlgili alternatifler"

GROUPING_PRIMARY_ALTERNATIVE = "primary_alternative"  # a meaningful split exists
GROUPING_FLAT = "flat"                                # no explicit axis → one list


# Seasonal / material modifiers that should count as matchable signals.
# Catalog-grounded and intentionally small; matched against a row's signal text
# (name + tags + features + attributes + product_type).
MODIFIER_TERMS: tuple[str, ...] = (
    # seasonal
    "kışlık", "yazlık", "kış", "yaz", "soğuk hava", "soğuk", "sıcak", "mevsimlik",
    # material / knit / fabric
    "triko", "deri", "kot", "denim", "pamuk", "keten", "yün", "kaşmir", "polar",
)


def classify_diversification_regime(parsed_query, response_plan):
    """Label which ordering regime this query falls into."""
    mode = getattr(response_plan, "mode", None)
    user_problem = getattr(response_plan, "user_problem", None)

    if mode == MODE_FOCUSED_SEARCH:
        return REGIME_FOCUSED
    if mode == MODE_BROAD_SEARCH:
        if user_problem:
            return REGIME_PROBLEM_BROAD
        return REGIME_BROWSE_BROAD
    return REGIME_NONE


# ---------------------------------------------------------------------------
# Low-level signal helpers (shared with ranking_diagnostics)
# ---------------------------------------------------------------------------

def field(row, key):
    """Read a column from a pandas Series OR a plain dict as a clean str.

    Both pandas ``Series`` and ``dict`` expose ``.get``; supporting both keeps
    these helpers unit-testable with plain dict fixtures (no DataFrame needed).
    """
    value = row.get(key, "")
    if value is None:
        return ""
    text = str(value)
    if text.lower() == "nan":
        return ""
    return text


def row_signal_text(row):
    """Normalized concatenation of the fields that carry intent signal."""
    parts = [
        field(row, "tags"),
        field(row, "features"),
        field(row, "product_name"),
        field(row, "attributes"),
        field(row, "product_type"),
    ]
    return normalize_text_for_match(" ".join(parts))


def problem_match(user_problem, signal_text):
    """True when the canonical user problem appears in the row's signal text."""
    if not user_problem:
        return False
    needle = normalize_text_for_match(str(user_problem))
    if not needle:
        return False
    return needle in signal_text


# Problems that are direct opposites of one another: a product built to solve
# one is actively wrong for the other (oily vs dry hair/skin). Keys and values
# are pre-normalized (normalize_text_for_match form). When the user states one
# problem, a row whose signal matches the opposite — and which does NOT match
# the user's own problem — is demoted to TIER_OTHER so it sinks below neutral
# same-type siblings instead of surfacing as an "alternative" (e.g. a "Kuru
# Saçlar İçin ... Şampuan" must not appear for a "yağlı saç" request).
#
# The needles include "sac"/"cilt" so they never fire on unrelated tokens such
# as "kuru şampuan" (a dry-shampoo product *type*, which is valid for oily hair).
_OPPOSITE_PROBLEM_SIGNALS: dict[str, tuple[str, ...]] = {
    "yagli sac": ("kuru sac",),
    "kuru sac": ("yagli sac", "yaglanma"),
    "yagli cilt": ("kuru cilt",),
    "kuru cilt": ("yagli cilt",),
}


def opposite_problem_match(user_problem, signal_text):
    """True when the row addresses the *opposite* of the user's stated problem."""
    if not user_problem:
        return False
    key = normalize_text_for_match(str(user_problem))
    for opposite in _OPPOSITE_PROBLEM_SIGNALS.get(key, ()):
        if opposite in signal_text:
            return True
    return False


def product_type_match(parsed_query, row):
    """Return 'exact' | 'substring' | 'none' for product_type alignment.

    Exact is what the tier rewards; substring is the loose recall behaviour we
    deliberately demote (e.g. 'serum' matching both 'Saç Serumu' and
    'Cilt Serumu').
    """
    parsed_pt = parsed_query.get("product_type")
    if not parsed_pt:
        return "none"

    parsed_pt_lower = str(parsed_pt).lower().strip()
    row_pt_lower = field(row, "product_type").lower().strip()

    if not row_pt_lower:
        return "none"
    if parsed_pt_lower == row_pt_lower:
        return "exact"
    # Word-boundary overlap only: keeps "serum" ↔ "Saç Serumu" but rejects the
    # spurious "Bot" ⊂ "Robot Süpürge" mid-word substring.
    if product_type_overlap(parsed_pt_lower, row_pt_lower):
        return "substring"
    return "none"


def feature_tag_hits(parsed_query, signal_text):
    """Count distinct parsed features present in the row's signal text."""
    features = parsed_query.get("features", []) or []
    hits = 0
    seen = set()
    for feature in features:
        norm = normalize_text_for_match(str(feature))
        if not norm or norm in seen:
            continue
        seen.add(norm)
        if norm in signal_text:
            hits += 1
    return hits


def extract_query_modifiers(query):
    """Detect seasonal/material modifier terms in the raw (deterministic) query."""
    found = set()
    for term in MODIFIER_TERMS:
        if contains_phrase(query, term):
            found.add(normalize_text_for_match(term))
    return found


def modifier_match(query_modifiers, signal_text):
    """True when any detected modifier appears in the row's signal text."""
    if not query_modifiers:
        return False
    return any(mod and mod in signal_text for mod in query_modifiers)


# ---------------------------------------------------------------------------
# Directness tier assignment (regime-aware)
# ---------------------------------------------------------------------------

def assign_directness_tier(parsed_query, row, user_problem, query_modifiers):
    """Assign a directness tier to one row. Returns (tier, reason).

    Rules (see the Stage 2 plan):
      * user_problem present → DIRECT requires problem_match (product_type alone
        is NOT enough); exact-type/same-sub but no problem → RELATED.
      * explicit product_type, no problem → DIRECT on exact type, but if the
        user also gave a modifier the row must match it; substring → RELATED.
      * modifiers present, no product_type → DIRECT on modifier match;
        same category → RELATED.
      * pure browse → no discriminating signal → all RELATED (sort by score).
    """
    signal = row_signal_text(row)
    sub_match = (
        parsed_query.get("sub_category") is not None
        and field(row, "sub_category").lower()
        == str(parsed_query["sub_category"]).lower()
    )
    main_match = (
        parsed_query.get("main_category") is not None
        and field(row, "main_category").lower()
        == str(parsed_query["main_category"]).lower()
    )

    # Context 1 — user problem present (Finding 1)
    if user_problem:
        if problem_match(user_problem, signal):
            return TIER_DIRECT, "problem_match"
        # A product for the OPPOSITE problem (e.g. "kuru saç" when the user
        # asked about "yağlı saç") is actively wrong: demote below neutral
        # same-type siblings so it never surfaces as a visible alternative.
        if opposite_problem_match(user_problem, signal):
            return TIER_OTHER, "problem_opposite"
        if product_type_match(parsed_query, row) == "exact" or sub_match:
            return TIER_RELATED, "same_type_or_sub"
        return TIER_OTHER, "other"

    # Context 2 — explicit product_type, no problem (Findings 2, 3)
    if parsed_query.get("product_type") is not None:
        ptype = product_type_match(parsed_query, row)
        if ptype == "exact":
            if not query_modifiers or modifier_match(query_modifiers, signal):
                return TIER_DIRECT, "product_type_exact"
            return TIER_RELATED, "exact_type_modifier_mismatch"
        if ptype == "substring":
            return TIER_RELATED, "product_type_substring"
        return TIER_OTHER, "other"

    # Context 3 — modifiers present, no product_type (Finding 2: kışlık elbise)
    if query_modifiers:
        if modifier_match(query_modifiers, signal):
            return TIER_DIRECT, "modifier_match"
        if sub_match or main_match:
            return TIER_RELATED, "same_category"
        return TIER_OTHER, "other"

    # Context 4 — pure browse: no discriminating signal, defer to score order.
    return TIER_RELATED, "browse"


# ---------------------------------------------------------------------------
# Final ordering
# ---------------------------------------------------------------------------

def finalize_ranking_v2(result_df, parsed_query, response_plan, query, top_k):
    """Re-order the scored result_df by directness tier, then blended score.

    Regime-aware:
      * browse_broad → bypass tiering, keep the legacy diversify (preserve the
        product-type variety browse queries expect).
      * problem_broad → DIRECT block (score-ordered, contiguous) leads; diversity
        applies ONLY to the non-direct tail (Finding 4).
      * focused / other → stable sort by (tier desc, score desc), then truncate.

    Read-only over scoring; reorders/truncates the result df only.
    """
    if result_df is None or result_df.empty:
        return result_df

    regime = classify_diversification_regime(parsed_query, response_plan)

    # Preserve browse diversity exactly as before.
    if regime == REGIME_BROWSE_BROAD:
        return diversify_results(result_df, top_k=top_k)

    user_problem = getattr(response_plan, "user_problem", None)
    modifiers = extract_query_modifiers(query)

    work = result_df.copy()
    work["_tier"] = [
        assign_directness_tier(parsed_query, row, user_problem, modifiers)[0]
        for _, row in work.iterrows()
    ]

    # When a DIRECT match anchors the result, drop CROSS-main-category TIER_OTHER
    # rows.  These reach the top-k only because the base_pool fallback backfills a
    # thin candidate set and semantic similarity grabs a loosely-worded outsider
    # (e.g. a "Mutfak Robotu" for a "Robot Süpürge" query).  They are neither the
    # answer nor a same-area sibling, so showing them as "İlgili alternatifler" is
    # misleading.  Same-category TIER_OTHER items are kept — they are legitimate
    # demoted siblings (Kamp Mutfak Seti next to Kamp Ocağı; an opposite "kuru
    # şampuan" next to "yağlı şampuan").  If nothing is DIRECT we keep everything
    # so a weak query still returns results instead of going empty.
    if (work["_tier"] == TIER_DIRECT).any():
        direct_mains = set(
            work.loc[work["_tier"] == TIER_DIRECT, "main_category"]
            .astype(str).str.lower()
        )
        is_other = work["_tier"] == TIER_OTHER
        cross_category = ~work["main_category"].astype(str).str.lower().isin(direct_mains)
        work = work[~(is_other & cross_category)]

    if regime == REGIME_PROBLEM_BROAD:
        direct = (
            work[work["_tier"] == TIER_DIRECT]
            .sort_values("score", ascending=False, kind="stable")
            .drop(columns="_tier")
            .reset_index(drop=True)
        )
        rest = work[work["_tier"] != TIER_DIRECT].drop(columns="_tier")
        if not rest.empty:
            rest = diversify_results(rest.reset_index(drop=True), top_k=top_k)
        combined = pd.concat([direct, rest], ignore_index=True)
        return combined.head(top_k).reset_index(drop=True)

    # focused (and REGIME_NONE fallback): tier first, score second.
    work = work.sort_values(
        ["_tier", "score"], ascending=[False, False], kind="stable"
    )
    return work.drop(columns="_tier").head(top_k).reset_index(drop=True)


# ---------------------------------------------------------------------------
# Primary / alternative grouping helpers (Stage 4)
# ---------------------------------------------------------------------------

def has_explicit_axis(parsed_query, user_problem, query_modifiers):
    """True when the query carries an explicit intent axis to split around.

    A primary/alternative split is only meaningful when the user named a
    concrete need: a problem (e.g. "yağlı saç"), a product_type, or a
    seasonal/material modifier. A pure category browse ("ayakkabı öner") has
    no such axis — everything is equally a result — so it stays flat.
    """
    return bool(
        user_problem
        or parsed_query.get("product_type") is not None
        or query_modifiers
    )


def determine_result_grouping(parsed_query, user_problem, query_modifiers, direct_count):
    """Decide whether results split into primary/alternative or stay flat.

    Split only when there's an explicit axis AND at least one direct (tier 2)
    match exists to anchor the "primary" group; otherwise flat.
    """
    if has_explicit_axis(parsed_query, user_problem, query_modifiers) and direct_count >= 1:
        return GROUPING_PRIMARY_ALTERNATIVE
    return GROUPING_FLAT


def match_group_for(tier, result_grouping):
    """Map a directness tier + grouping mode to a match_group label.

    In flat mode there is no alternative concept — every result is a direct
    answer to a broad browse, so all are "primary". In split mode, only the
    DIRECT tier is primary; everything else is an alternative.
    """
    if result_grouping == GROUPING_FLAT:
        return GROUP_PRIMARY
    return GROUP_PRIMARY if tier == TIER_DIRECT else GROUP_ALTERNATIVE


def compute_grouping(parsed_query, result_df, response_plan, query):
    """Compute (result_grouping, [match_group per row]) for the FINAL result_df.

    Single source of truth shared by the response builder (main.py) and the
    debug diagnostics, so the contract labels and the debug labels never drift.
    The returned match_group list is aligned to ``result_df.iterrows()`` order;
    because ``finalize_ranking_v2`` already sorts DIRECT-first, primaries are
    contiguous at the top — i.e. the products list stays "primary-first".
    """
    if result_df is None or result_df.empty:
        return GROUPING_FLAT, []

    user_problem = getattr(response_plan, "user_problem", None)
    modifiers = extract_query_modifiers(query)

    tiers = [
        assign_directness_tier(parsed_query, row, user_problem, modifiers)[0]
        for _, row in result_df.iterrows()
    ]
    direct_count = sum(1 for tier in tiers if tier == TIER_DIRECT)
    grouping = determine_result_grouping(
        parsed_query, user_problem, modifiers, direct_count
    )
    groups = [match_group_for(tier, grouping) for tier in tiers]
    return grouping, groups
