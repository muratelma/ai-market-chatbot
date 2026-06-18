"""
Shared manual-regression scenario matrix for the AI-Market chatbot.

Single source of truth for both manual harnesses:

- ``api_queries.py``        — STRICT, deterministic pass/fail checks.
- ``ollama_regression.py``  — WARNING-only checks (Ollama may vary).

Both import :data:`ALL_SCENARIOS` from here so the query list and expected
behavior never drift between the two runners. This module is pure data — it
performs no HTTP calls and has no side effects, so it is safe to import from
anywhere (including pytest, although the harnesses themselves run outside it
because Ollama is non-deterministic).

Design notes
------------
Each :class:`Scenario` declares what we *expect* from ``POST /search`` for one
query. The ``strict`` tuple lists which of those expectations are enforced as
hard pass/fail. Any expectation that is set but *not* named in ``strict`` is a
warning-only signal (it depends on Ollama normalization / rewriting, which is
non-deterministic and must never break the build).

The check vocabulary (see the ``CHECK_*`` constants) maps onto the
deterministic rule tree in ``response_planner.py`` and the status branches in
``main.py``. See the planning matrix in the project docs for the rationale
behind each row.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# ---------------------------------------------------------------------------
# Scenario kinds (one per row-type in the planning matrix)
# ---------------------------------------------------------------------------

KIND_BROAD = "broad"          # broad category / problem query
KIND_FOCUSED = "focused"      # explicit sub_category / product_type query
KIND_CONTEXT = "context"      # context / feature query, intent must be kept
KIND_VAGUE = "vague"          # no product signal → clarification
KIND_NO_RESULT = "no_result"  # nonsense / out-of-catalog → no products

# ---------------------------------------------------------------------------
# Response modes (mirror response_planner.MODE_* / main.py response_mode)
# ---------------------------------------------------------------------------

MODE_CLARIFICATION_ONLY = "clarification_only"
MODE_FOCUSED_SEARCH = "focused_search"
MODE_BROAD_SEARCH = "broad_search"
MODE_NO_RESULT = "no_result"
MODE_CHAT_REPLY = "chat_reply"

# ---------------------------------------------------------------------------
# Check names — used in Scenario.strict to mark a check as hard pass/fail.
# Any expectation set on a Scenario but absent from .strict is warning-only.
# ---------------------------------------------------------------------------

CHECK_MODE = "mode"                       # response_mode == expect_mode
CHECK_PRODUCTS = "products"               # products non-empty matches expect_products
CHECK_FOLLOWUP = "followup"               # follow_up presence matches expect_followup
CHECK_NO_CLARIFICATION = "no_clarification"  # needs_clarification is False
CHECK_MAIN_CATEGORY = "main_category"     # parsed_query.main_category == expect_main_category
CHECK_SUB_OR_TYPE = "sub_or_type"         # parsed_query sub/product_type == expect_sub_or_type
CHECK_PRICE = "price_honored"             # every product respects the stated price bound
CHECK_NO_FABRICATION = "no_fabrication"   # products == [] (no invented catalog item)
CHECK_PRIMARY_FIRST = "primary_first"     # grouped result is primary-first + expected result_grouping
CHECK_NO_FORBIDDEN_TYPES = "no_forbidden_types"  # no product's sub/type matches forbid_types


# ---------------------------------------------------------------------------
# Scenario dataclass
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Scenario:
    """One manual-regression case for ``POST /search``.

    Expectation fields hold what we *expect*; :attr:`strict` lists which of
    those checks are pass/fail. Everything else is warning-only.
    """

    category: str                       # one of the 12 main_category labels, or "Cross-cutting"
    kind: str                           # KIND_*
    query: str                          # request body {"query": ...}

    # Expectations (None = "don't assert this dimension")
    expect_mode: str | None = None
    expect_products: bool | None = None
    expect_followup: bool | None = None
    expect_main_category: str | None = None
    expect_sub_or_type: str | None = None
    # Expected result_grouping ("primary_alternative" | "flat") when the server
    # runs with AI_MARKET_GROUPED_RANKING on. Checked by CHECK_PRIMARY_FIRST,
    # which is skipped when the server does not emit grouping fields.
    expect_result_grouping: str | None = None
    # Category/type substrings that must NOT appear in any returned product's
    # sub_category or product_type — used for negative constraints ("mont veya
    # kaban değil"). Checked by CHECK_NO_FORBIDDEN_TYPES.
    forbid_types: tuple[str, ...] = field(default_factory=tuple)

    # Hard pass/fail checks; remaining expectations are warning-only.
    strict: tuple[str, ...] = field(default_factory=tuple)

    notes: str = ""

    def strict_checks(self) -> tuple[str, ...]:
        """Return the checks enforced as hard pass/fail for this scenario."""
        return self.strict

    def warning_checks(self) -> tuple[str, ...]:
        """Return checks that have an expectation set but are advisory only."""
        candidates = {
            CHECK_MODE: self.expect_mode,
            CHECK_PRODUCTS: self.expect_products,
            CHECK_FOLLOWUP: self.expect_followup,
            CHECK_MAIN_CATEGORY: self.expect_main_category,
            CHECK_SUB_OR_TYPE: self.expect_sub_or_type,
        }
        return tuple(
            name
            for name, value in candidates.items()
            if value is not None and name not in self.strict
        )


# ---------------------------------------------------------------------------
# The 12 catalog categories (taxonomy.csv main_category rows)
# ---------------------------------------------------------------------------

CATEGORIES: tuple[str, ...] = (
    "Kamp",
    "Ayakkabı",
    "Giyim",
    "Elektronik",
    "Spor",
    "Kişisel Bakım",
    "Ev & Yaşam",
    "Mutfak",
    "Anne & Bebek",
    "Aksesuar",
    "Otomotiv",
    "Kırtasiye",
)


# ---------------------------------------------------------------------------
# Scenario matrix
# ---------------------------------------------------------------------------

ALL_SCENARIOS: tuple[Scenario, ...] = (
    # ---- 1. Kamp ----
    Scenario(
        category="Kamp", kind=KIND_BROAD,
        query="kamp için ürün öner",
        expect_mode=MODE_BROAD_SEARCH, expect_products=True, expect_followup=True,
        expect_main_category="Kamp",
        strict=(CHECK_PRODUCTS, CHECK_FOLLOWUP, CHECK_NO_CLARIFICATION, CHECK_MAIN_CATEGORY),
        notes="Borderline broad/focused: Ollama may resolve a sub_category, so "
              "mode is advisory. Strict on products + follow-up + category preserved.",
    ),
    Scenario(
        category="Kamp", kind=KIND_FOCUSED,
        query="kamp için uyku tulumu öner",
        expect_mode=MODE_FOCUSED_SEARCH, expect_products=True, expect_followup=False,
        expect_main_category="Kamp", expect_sub_or_type="Uyku Tulumu",
        strict=(CHECK_MODE, CHECK_PRODUCTS, CHECK_NO_CLARIFICATION),
    ),
    Scenario(
        category="Kamp", kind=KIND_CONTEXT,
        query="kamp için yemek yapacak bir şey lazım",
        expect_products=True, expect_main_category="Kamp", expect_sub_or_type="Pişirme",
        expect_result_grouping="primary_alternative",
        strict=(CHECK_PRODUCTS, CHECK_MAIN_CATEGORY, CHECK_PRIMARY_FIRST),
        notes="Intent (Kamp/Pişirme) must be preserved; exact mode is Ollama-sensitive. "
              "Grouped: Kamp Ocağı (direct cooking equipment) is primary and leads over "
              "the semantic sibling Kamp Mutfak Seti, which becomes an alternative.",
    ),

    # ---- 2. Ayakkabı ----
    Scenario(
        category="Ayakkabı", kind=KIND_BROAD,
        query="ayakkabı öner",
        expect_products=True, expect_followup=True, expect_main_category="Ayakkabı",
        expect_result_grouping="flat",
        strict=(CHECK_PRODUCTS, CHECK_FOLLOWUP, CHECK_NO_CLARIFICATION, CHECK_PRIMARY_FIRST),
        notes="Resolves to focused_search + soft follow-up (not broad); mode is warning-only. "
              "No explicit problem/type/modifier axis → result_grouping must stay 'flat' "
              "(must NOT be incorrectly split into primary/alternative).",
    ),
    Scenario(
        category="Ayakkabı", kind=KIND_FOCUSED,
        query="yağmurlu havalar için kadın bot öner",
        expect_mode=MODE_FOCUSED_SEARCH, expect_products=True, expect_followup=False,
        expect_main_category="Ayakkabı", expect_sub_or_type="Bot",
        strict=(CHECK_MODE, CHECK_PRODUCTS, CHECK_NO_CLARIFICATION),
    ),
    Scenario(
        category="Ayakkabı", kind=KIND_CONTEXT,
        query="koşu için ayakkabı",
        expect_products=True, expect_main_category="Ayakkabı",
        strict=(CHECK_PRODUCTS, CHECK_MAIN_CATEGORY),
    ),
    Scenario(
        category="Ayakkabı", kind=KIND_FOCUSED,
        query="1500 TL üstünde ayakkabı",
        expect_products=True, expect_main_category="Ayakkabı",
        strict=(CHECK_PRODUCTS, CHECK_PRICE),
        notes="Price floor must be honored by every returned product.",
    ),

    # ---- 3. Giyim ----
    Scenario(
        category="Giyim", kind=KIND_BROAD,
        query="elbise öner",
        expect_products=True, expect_followup=True,
        expect_main_category="Giyim", expect_sub_or_type="Elbise",
        strict=(CHECK_PRODUCTS, CHECK_FOLLOWUP, CHECK_NO_CLARIFICATION),
        notes="Single-word product query → focused + soft follow-up; mode warning-only.",
    ),
    Scenario(
        category="Giyim", kind=KIND_FOCUSED,
        query="özel gün için kadın abiye öner",
        expect_mode=MODE_FOCUSED_SEARCH, expect_products=True, expect_followup=False,
        expect_main_category="Giyim", expect_sub_or_type="Abiye",
        strict=(CHECK_MODE, CHECK_PRODUCTS, CHECK_NO_CLARIFICATION),
    ),
    Scenario(
        category="Giyim", kind=KIND_CONTEXT,
        query="kamp için kışlık elbise öner",
        expect_products=True, expect_main_category="Giyim",
        strict=(CHECK_PRODUCTS, CHECK_MAIN_CATEGORY),
        notes="Explicit product (elbise) must win over context word (kamp) → main stays Giyim.",
    ),
    Scenario(
        category="Giyim", kind=KIND_FOCUSED,
        query="kışlık elbise öner",
        expect_products=True, expect_main_category="Giyim", expect_sub_or_type="Elbise",
        expect_result_grouping="primary_alternative",
        strict=(CHECK_PRODUCTS, CHECK_NO_CLARIFICATION, CHECK_PRIMARY_FIRST),
        notes="Seasonal modifier: kışlık/triko dresses are primary and lead; yazlık "
              "dresses become alternatives. CHECK_PRIMARY_FIRST skipped if grouping off.",
    ),
    Scenario(
        category="Giyim", kind=KIND_FOCUSED,
        query="Kışlık kadın elbisesi önerir misin? Mont veya kaban değil, elbise arıyorum.",
        expect_products=True, expect_main_category="Giyim", expect_sub_or_type="Elbise",
        forbid_types=("Mont", "Kaban"),
        strict=(CHECK_PRODUCTS, CHECK_MAIN_CATEGORY, CHECK_NO_FORBIDDEN_TYPES),
        notes="Negative constraint: 'mont/kaban değil' rejects outerwear — the "
              "explicit positive product (elbise) must win and no Mont/Kaban may "
              "appear in results. Deterministic via query_parser.extract_excluded_terms.",
    ),
    Scenario(
        category="Giyim", kind=KIND_FOCUSED,
        query="Kışlık, sıcak tutan ve günlük kullanıma uygun bir kadın elbisesi önerir misin?",
        expect_products=True, expect_main_category="Giyim", expect_sub_or_type="Elbise",
        forbid_types=("Mont", "Kaban", "Şişme Mont", "Yağmurluk Mont"),
        strict=(CHECK_PRODUCTS, CHECK_MAIN_CATEGORY, CHECK_NO_FORBIDDEN_TYPES),
        notes="Explicit positive intent lock (NO negation): warmth/seasonal "
              "modifiers ('kışlık', 'sıcak tutan', 'günlük') must NOT switch the "
              "explicit 'elbise' to Mont/Kaban. Results stay in Giyim › Elbise; "
              "the inflected 'elbisesi' is detected via contains_term.",
    ),

    # ---- 4. Elektronik ----
    Scenario(
        category="Elektronik", kind=KIND_BROAD,
        query="elektronik ürün öner",
        expect_mode=MODE_BROAD_SEARCH, expect_products=True, expect_followup=True,
        expect_main_category="Elektronik",
        strict=(CHECK_MODE, CHECK_PRODUCTS, CHECK_FOLLOWUP, CHECK_NO_CLARIFICATION),
    ),
    Scenario(
        category="Elektronik", kind=KIND_FOCUSED,
        query="bilgisayar için kablosuz mouse öner",
        expect_mode=MODE_FOCUSED_SEARCH, expect_products=True, expect_followup=False,
        expect_main_category="Elektronik", expect_sub_or_type="Mouse",
        strict=(CHECK_MODE, CHECK_PRODUCTS, CHECK_NO_CLARIFICATION),
    ),
    Scenario(
        category="Elektronik", kind=KIND_CONTEXT,
        query="telefonum hemen bitiyor",
        expect_products=True, expect_main_category="Elektronik", expect_sub_or_type="Powerbank",
        strict=(CHECK_PRODUCTS,),
        notes="Problem→product inference (Powerbank) is Ollama-sensitive → warning-only.",
    ),
    Scenario(
        category="Elektronik", kind=KIND_BROAD,
        query="1000 ile 2000 arası elektronik",
        expect_mode=MODE_BROAD_SEARCH, expect_products=True,
        expect_main_category="Elektronik",
        strict=(CHECK_PRODUCTS, CHECK_PRICE),
    ),

    # ---- 5. Spor ----
    Scenario(
        category="Spor", kind=KIND_BROAD,
        query="spor için ürün öner",
        expect_mode=MODE_BROAD_SEARCH, expect_products=True, expect_followup=True,
        expect_main_category="Spor",
        strict=(CHECK_MODE, CHECK_PRODUCTS, CHECK_FOLLOWUP, CHECK_NO_CLARIFICATION),
    ),
    Scenario(
        category="Spor", kind=KIND_FOCUSED,
        query="yoga için mat öner",
        expect_mode=MODE_FOCUSED_SEARCH, expect_products=True, expect_followup=False,
        expect_main_category="Spor", expect_sub_or_type="Yoga Matı",
        strict=(CHECK_MODE, CHECK_PRODUCTS, CHECK_NO_CLARIFICATION),
    ),
    Scenario(
        category="Spor", kind=KIND_CONTEXT,
        query="koşu için ürün arıyorum",
        expect_products=True, expect_main_category="Spor",
        strict=(CHECK_PRODUCTS, CHECK_MAIN_CATEGORY),
    ),

    # ---- 6. Kişisel Bakım ----
    Scenario(
        category="Kişisel Bakım", kind=KIND_BROAD,
        query="saç için ürün öner",
        expect_mode=MODE_BROAD_SEARCH, expect_products=True, expect_followup=True,
        expect_main_category="Kişisel Bakım", expect_sub_or_type="Saç Bakımı",
        strict=(CHECK_PRODUCTS, CHECK_FOLLOWUP, CHECK_NO_CLARIFICATION, CHECK_MAIN_CATEGORY),
        notes="Borderline broad/focused: Ollama may resolve a sub_category, so "
              "mode is advisory. Strict on products + follow-up + category preserved.",
    ),
    Scenario(
        category="Kişisel Bakım", kind=KIND_FOCUSED,
        query="saç dökülmesi için şampuan öner",
        expect_mode=MODE_FOCUSED_SEARCH, expect_products=True, expect_followup=False,
        expect_main_category="Kişisel Bakım", expect_sub_or_type="Şampuan",
        strict=(CHECK_MODE, CHECK_PRODUCTS, CHECK_NO_CLARIFICATION),
    ),
    Scenario(
        category="Kişisel Bakım", kind=KIND_BROAD,
        query="saç dökülmesi için ürün öner",
        expect_mode=MODE_BROAD_SEARCH, expect_products=True,
        expect_main_category="Kişisel Bakım", expect_sub_or_type="Saç Bakımı",
        expect_result_grouping="primary_alternative",
        strict=(CHECK_MODE, CHECK_PRODUCTS, CHECK_NO_CLARIFICATION, CHECK_PRIMARY_FIRST),
        notes="Problem + sub_category, no product_type → diversified broad_search. "
              "Grouped: dökülme products are primary; CHECK_PRIMARY_FIRST skipped if "
              "grouping disabled on the server.",
    ),
    Scenario(
        category="Kişisel Bakım", kind=KIND_BROAD,
        query="yağlı saç için ürün öner",
        expect_mode=MODE_BROAD_SEARCH, expect_products=True,
        expect_main_category="Kişisel Bakım", expect_sub_or_type="Saç Bakımı",
        expect_result_grouping="primary_alternative",
        strict=(CHECK_PRODUCTS, CHECK_NO_CLARIFICATION, CHECK_PRIMARY_FIRST),
        notes="Problem-broad: yağlı saç products are primary, lead; non-yağlı "
              "siblings become alternatives. Mode is Ollama-advisory.",
    ),
    Scenario(
        category="Kişisel Bakım", kind=KIND_FOCUSED,
        query="yağlı saç için şampuan öner",
        expect_mode=MODE_FOCUSED_SEARCH, expect_products=True,
        expect_main_category="Kişisel Bakım", expect_sub_or_type="Şampuan",
        expect_result_grouping="primary_alternative",
        strict=(CHECK_MODE, CHECK_PRODUCTS, CHECK_NO_CLARIFICATION, CHECK_PRIMARY_FIRST),
        notes="Problem + product_type: yağlı şampuanlar are primary; generic "
              "şampuanlar are alternatives. product_type alone is not primary.",
    ),
    Scenario(
        category="Kişisel Bakım", kind=KIND_CONTEXT,
        query="yağlı cilt için temizleyici öner",
        expect_products=True, expect_main_category="Kişisel Bakım",
        expect_sub_or_type="Cilt Bakımı",
        strict=(CHECK_PRODUCTS, CHECK_MAIN_CATEGORY),
    ),

    # ---- 7. Ev & Yaşam ----
    Scenario(
        category="Ev & Yaşam", kind=KIND_BROAD,
        query="ev için ürün öner",
        expect_mode=MODE_BROAD_SEARCH, expect_products=True, expect_followup=True,
        expect_main_category="Ev & Yaşam",
        strict=(CHECK_PRODUCTS, CHECK_FOLLOWUP, CHECK_NO_CLARIFICATION, CHECK_MAIN_CATEGORY),
        notes="Borderline broad/focused: Ollama may resolve a sub_category, so "
              "mode is advisory. Strict on products + follow-up + category preserved.",
    ),
    Scenario(
        category="Ev & Yaşam", kind=KIND_FOCUSED,
        query="ev için dekoratif lamba öner",
        expect_mode=MODE_FOCUSED_SEARCH, expect_products=True, expect_followup=False,
        expect_main_category="Ev & Yaşam", expect_sub_or_type="Dekoratif Lamba",
        strict=(CHECK_MODE, CHECK_PRODUCTS, CHECK_NO_CLARIFICATION),
    ),

    # ---- 8. Mutfak ----
    Scenario(
        category="Mutfak", kind=KIND_BROAD,
        query="mutfak için ürün öner",
        expect_mode=MODE_BROAD_SEARCH, expect_products=True, expect_followup=True,
        expect_main_category="Mutfak",
        strict=(CHECK_PRODUCTS, CHECK_FOLLOWUP, CHECK_NO_CLARIFICATION, CHECK_MAIN_CATEGORY),
        notes="Borderline broad/focused: Ollama may resolve a sub_category, so "
              "mode is advisory. Strict on products + follow-up + category preserved.",
    ),
    Scenario(
        category="Mutfak", kind=KIND_FOCUSED,
        query="mutfak için kahve makinesi öner",
        expect_mode=MODE_FOCUSED_SEARCH, expect_products=True, expect_followup=False,
        expect_main_category="Mutfak", expect_sub_or_type="Kahve Makinesi",
        strict=(CHECK_MODE, CHECK_PRODUCTS, CHECK_NO_CLARIFICATION),
    ),

    # ---- 9. Anne & Bebek ----
    Scenario(
        category="Anne & Bebek", kind=KIND_BROAD,
        query="bebek için ürün öner",
        expect_mode=MODE_BROAD_SEARCH, expect_products=True, expect_followup=True,
        expect_main_category="Anne & Bebek",
        strict=(CHECK_MODE, CHECK_PRODUCTS, CHECK_FOLLOWUP, CHECK_NO_CLARIFICATION),
    ),
    Scenario(
        category="Anne & Bebek", kind=KIND_FOCUSED,
        query="bebek için pişik kremi öner",
        expect_mode=MODE_FOCUSED_SEARCH, expect_products=True, expect_followup=False,
        expect_main_category="Anne & Bebek", expect_sub_or_type="Pişik Kremi",
        strict=(CHECK_MODE, CHECK_PRODUCTS, CHECK_NO_CLARIFICATION),
    ),

    # ---- 10. Aksesuar ----
    Scenario(
        category="Aksesuar", kind=KIND_BROAD,
        query="aksesuar öner",
        expect_mode=MODE_BROAD_SEARCH, expect_products=True, expect_followup=True,
        expect_main_category="Aksesuar",
        strict=(CHECK_PRODUCTS, CHECK_FOLLOWUP, CHECK_NO_CLARIFICATION),
    ),
    Scenario(
        category="Aksesuar", kind=KIND_FOCUSED,
        query="okul için sırt çantası öner",
        expect_mode=MODE_FOCUSED_SEARCH, expect_products=True, expect_followup=False,
        expect_main_category="Aksesuar", expect_sub_or_type="Sırt Çantası",
        strict=(CHECK_PRODUCTS, CHECK_NO_CLARIFICATION),
    ),

    # ---- 11. Otomotiv ----
    Scenario(
        category="Otomotiv", kind=KIND_BROAD,
        query="otomotiv ürünü öner",
        expect_mode=MODE_BROAD_SEARCH, expect_products=True, expect_followup=True,
        expect_main_category="Otomotiv",
        strict=(CHECK_PRODUCTS, CHECK_FOLLOWUP, CHECK_NO_CLARIFICATION),
    ),
    Scenario(
        category="Otomotiv", kind=KIND_CONTEXT,
        query="araç için telefon şarj cihazı öner",
        expect_mode=MODE_FOCUSED_SEARCH, expect_products=True, expect_followup=False,
        expect_main_category="Otomotiv", expect_sub_or_type="Araç Şarj Cihazı",
        strict=(CHECK_PRODUCTS, CHECK_NO_CLARIFICATION),
    ),

    # ---- 12. Kırtasiye ----
    Scenario(
        category="Kırtasiye", kind=KIND_BROAD,
        query="kırtasiye ürünü öner",
        expect_mode=MODE_BROAD_SEARCH, expect_products=True, expect_followup=True,
        expect_main_category="Kırtasiye",
        strict=(CHECK_PRODUCTS, CHECK_FOLLOWUP, CHECK_NO_CLARIFICATION),
    ),
    Scenario(
        category="Kırtasiye", kind=KIND_FOCUSED,
        query="tablet için dokunmatik kalem öner",
        expect_products=True, expect_sub_or_type="Tablet Kalemi",
        strict=(CHECK_PRODUCTS, CHECK_NO_CLARIFICATION),
        notes="May parse as Kırtasiye or Elektronik; assert products, not main_category.",
    ),

    # ---- Cross-cutting (run once, not per-category) ----
    Scenario(
        category="Cross-cutting", kind=KIND_VAGUE,
        query="ürün öner",
        expect_mode=MODE_CLARIFICATION_ONLY, expect_products=False, expect_followup=True,
        strict=(CHECK_MODE, CHECK_PRODUCTS, CHECK_FOLLOWUP),
    ),
    Scenario(
        category="Cross-cutting", kind=KIND_VAGUE,
        query="bir şey lazım",
        expect_mode=MODE_CLARIFICATION_ONLY, expect_products=False, expect_followup=True,
        strict=(CHECK_MODE, CHECK_PRODUCTS, CHECK_FOLLOWUP),
    ),
    Scenario(
        category="Cross-cutting", kind=KIND_VAGUE,
        query="1500 TL altında erkek",
        expect_mode=MODE_CLARIFICATION_ONLY, expect_products=False, expect_followup=True,
        strict=(CHECK_PRODUCTS, CHECK_FOLLOWUP),
        notes="Attributes only, no category → clarification; exact mode warning-only.",
    ),
    Scenario(
        category="Cross-cutting", kind=KIND_NO_RESULT,
        query="uzay mekiği",
        expect_products=False,
        strict=(CHECK_PRODUCTS, CHECK_NO_FABRICATION),
    ),
    Scenario(
        category="Cross-cutting", kind=KIND_NO_RESULT,
        query="zihin okuma cihazı",
        expect_products=False,
        strict=(CHECK_PRODUCTS, CHECK_NO_FABRICATION),
    ),
    # Unreal / fantasy items phrased as full purchase sentences. Normalization
    # must not map these onto real catalog terms (e.g. "saat"/"seyahat"); they
    # must return no products with the safe no-result message.
    Scenario(
        category="Cross-cutting", kind=KIND_NO_RESULT,
        query="zaman makinesi almak istiyorum",
        expect_products=False,
        strict=(CHECK_PRODUCTS, CHECK_NO_FABRICATION),
    ),
    Scenario(
        category="Cross-cutting", kind=KIND_NO_RESULT,
        query="Mars'a giden roket almak istiyorum",
        expect_products=False,
        strict=(CHECK_PRODUCTS, CHECK_NO_FABRICATION),
    ),
    Scenario(
        category="Cross-cutting", kind=KIND_NO_RESULT,
        query="Görünmezlik pelerini almak istiyorum",
        expect_products=False,
        strict=(CHECK_PRODUCTS, CHECK_NO_FABRICATION),
    ),
)


# ---------------------------------------------------------------------------
# Convenience accessors
# ---------------------------------------------------------------------------

def by_category(category: str) -> tuple[Scenario, ...]:
    """Return all scenarios for a given category label."""
    return tuple(s for s in ALL_SCENARIOS if s.category == category)


def by_kind(kind: str) -> tuple[Scenario, ...]:
    """Return all scenarios of a given KIND_* type."""
    return tuple(s for s in ALL_SCENARIOS if s.kind == kind)
