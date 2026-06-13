"""
Response planner for AI-Market chatbot.

Determines the response *mode* from ``parsed_query`` output, **after** the
query parser has run and **before** the search engine executes.  The mode
controls two things:

1. Whether and how the search runs (focused vs. diversified).
2. What metadata the Ollama response-rewriter receives so it can write
   the correct style of assistant message.

Design
------
* Pure deterministic rules — no Ollama call, no added latency.
* Consumes only ``parsed_query`` + original query text.
* Returns a ``ResponsePlan`` dataclass that downstream components read.
* Never modifies parsed_query or search results.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Mode constants
# ---------------------------------------------------------------------------

MODE_CHAT_REPLY = "chat_reply"
MODE_NO_RESULT = "no_result"
MODE_CLARIFICATION_ONLY = "clarification_only"
MODE_FOCUSED_SEARCH = "focused_search"
MODE_BROAD_SEARCH = "broad_search"


# ---------------------------------------------------------------------------
# ResponsePlan dataclass
# ---------------------------------------------------------------------------

@dataclass
class ResponsePlan:
    """Describes how the chatbot should behave for this query."""

    mode: str

    # Context flags (derived from parsed_query)
    has_explicit_product_type: bool = False
    has_main_category: bool = False
    has_sub_category: bool = False

    # Semantic context
    user_problem: str | None = None       # e.g. "saç dökülmesi", "kuru cilt"
    context_area: str | None = None       # e.g. "kamp", "spor", "bebek"

    # Behavior flags
    diversify_results: bool = False       # Spread results across product_types
    should_ask_followup: bool = False     # Include a narrowing question
    followup_question: str | None = None

    # Info for rewriter
    top_product_types: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# User-problem extraction
# ---------------------------------------------------------------------------

# Problem phrases that indicate a user need/concern (not a product type).
# Ordered longest-first so multi-word phrases match before single words.
_PROBLEM_PHRASES: list[tuple[str, str]] = [
    # Hair
    ("saç dökülmesi", "saç dökülmesi"),
    ("saç dökülme", "saç dökülmesi"),
    ("dökülme", "saç dökülmesi"),
    ("kuru saç", "kuru saç"),
    ("yağlı saç", "yağlı saç"),
    ("kepek", "kepek"),
    # Skin
    ("yağlı cilt", "yağlı cilt"),
    ("kuru cilt", "kuru cilt"),
    ("hassas cilt", "hassas cilt"),
    ("sivilce", "sivilce"),
    ("akne", "sivilce"),
    ("morluk", "morluk"),
    ("göz altı morluk", "morluk"),
    # Baby
    ("pişik", "pişik"),
    ("pisik", "pişik"),
]


def extract_user_problem(query: str) -> str | None:
    """
    Detect whether the query mentions a user problem/concern.

    Returns the canonical problem name, or None.
    """
    q_lower = query.lower().strip()

    for phrase, canonical in _PROBLEM_PHRASES:
        if re.search(rf"\b{re.escape(phrase)}\b", q_lower):
            return canonical

    return None


# ---------------------------------------------------------------------------
# Context-area extraction
# ---------------------------------------------------------------------------

# Maps query keywords → a canonical context area label.
_CONTEXT_AREA_MAP: dict[str, str] = {
    "kamp": "kamp",
    "outdoor": "kamp",
    "çadır": "kamp",
    "cadir": "kamp",
    "spor": "spor",
    "fitness": "spor",
    "egzersiz": "spor",
    "koşu": "spor",
    "kosu": "spor",
    "ev": "ev",
    "dekoratif": "ev",
    "dekorasyon": "ev",
    "mutfak": "mutfak",
    "ofis": "ofis",
    "okul": "okul",
    "bebek": "bebek",
    "araç": "araç",
    "arac": "araç",
    "araba": "araç",
}


def extract_context_area(query: str) -> str | None:
    """
    Detect a broad use-area / context from the query.

    Returns the canonical area name, or None.
    """
    q_lower = query.lower().strip()

    for keyword, area in _CONTEXT_AREA_MAP.items():
        if re.search(rf"\b{re.escape(keyword)}\b", q_lower):
            return area

    return None


# ---------------------------------------------------------------------------
# Follow-up question templates
# ---------------------------------------------------------------------------

_BROAD_FOLLOWUP_QUESTIONS: dict[str, str] = {
    "kamp": (
        "Kamp kategorisinden farklı ürün tiplerini listeledim. "
        "Uyku, barınma, aydınlatma veya yemek hazırlama gibi "
        "hangi ihtiyacına odaklanmamı istersin?"
    ),
    "spor": (
        "Spor kategorisinden çeşitli ürünleri listeledim. "
        "Fitness, koşu, yoga veya outdoor gibi hangi alana "
        "odaklanmamı istersin?"
    ),
    "ev": (
        "Ev & Yaşam kategorisinden farklı ürünleri listeledim. "
        "Dekorasyon, aydınlatma, temizlik veya düzenleme gibi "
        "hangi ihtiyacına odaklanmamı istersin?"
    ),
    "bebek": (
        "Bebek bakım ürünlerinden çeşitli seçenekleri listeledim. "
        "Bakım, beslenme, güvenlik veya giyim gibi hangi alana "
        "odaklanmamı istersin?"
    ),
}

_DEFAULT_BROAD_FOLLOWUP = (
    "Farklı ürün tiplerinden seçenekleri listeledim. "
    "Belirli bir ürün tipini tercih eder misin?"
)

_PROBLEM_BROAD_FOLLOWUP_TEMPLATE = (
    "{problem} sorununa yönelik farklı ürün tiplerinden seçenekleri listeledim. "
    "Belirli bir ürün tipini tercih eder misin?"
)

_CATEGORY_BROWSE_FOLLOWUP: dict[str, str] = {
    "Ayakkabı": (
        "Ayakkabı kategorisinden farklı modelleri listeledim. "
        "Günlük, spor, koşu veya özel gün gibi kullanım amacını "
        "belirtirsen daha uygun öneriler sunabilirim."
    ),
    "Giyim": (
        "Giyim kategorisinden çeşitli ürünleri listeledim. "
        "Günlük, ofis, yazlık/kışlık veya özel gün gibi bir kullanım "
        "amacı belirtirsen daha iyi yardımcı olurum."
    ),
    "Elektronik": (
        "Elektronik kategorisinden farklı ürünleri listeledim. "
        "Bilgisayar, telefon, ses veya giyilebilir teknoloji gibi "
        "hangi alana odaklanmamı istersin?"
    ),
    "Kişisel Bakım": (
        "Kişisel bakım ürünlerinden çeşitli seçenekleri listeledim. "
        "Saç bakımı, cilt bakımı veya ağız bakımı gibi hangi alana "
        "odaklanmamı istersin?"
    ),
}


def _build_followup_question(
    context_area: str | None,
    user_problem: str | None,
    main_category: str | None,
) -> str:
    """Build an appropriate follow-up question for broad_search mode."""
    if user_problem:
        return _PROBLEM_BROAD_FOLLOWUP_TEMPLATE.format(
            problem=user_problem.capitalize()
        )

    if context_area and context_area in _BROAD_FOLLOWUP_QUESTIONS:
        return _BROAD_FOLLOWUP_QUESTIONS[context_area]

    if main_category and main_category in _CATEGORY_BROWSE_FOLLOWUP:
        return _CATEGORY_BROWSE_FOLLOWUP[main_category]

    return _DEFAULT_BROAD_FOLLOWUP


# ---------------------------------------------------------------------------
# Public API & Heuristics
# ---------------------------------------------------------------------------

def query_has_details(parsed_query: dict, query: str) -> bool:
    """
    Determine if the search query contains additional details beyond
    the core product category/type name itself.
    """
    # Compile category/product names and synonyms
    category_words = set()
    for key in ["main_category", "sub_category", "product_type"]:
        val = parsed_query.get(key)
        if val:
            val_norm = re.sub(r"[^\w\s]", " ", str(val).lower())
            category_words.update(val_norm.split())

    # 1. Price constraints (always a detail)
    if parsed_query.get("min_price") is not None or parsed_query.get("max_price") is not None:
        return True

    # 2. Target group (kadın, erkek, çocuk, bebek, unisex when explicit and not part of PT name)
    #    Only count it when the target-group word actually appears in the
    #    query text.  Ollama normalization can inject a target group (e.g.
    #    expanding "elbise öner" → "kadın elbise") the user never typed; that
    #    must not be treated as a user-given detail.
    target_group = parsed_query.get("target_group")
    if target_group:
        tg_words = set(re.findall(r"\w+", str(target_group).lower()))
        if not tg_words.issubset(category_words) and any(
            tw in query.lower() for tw in tg_words
        ):
            return True

    # 3. Features (that are not part of category/product name)
    # Only count a feature as user-given detail when at least one of its
    # tokens actually appears in the original query.  This skips synthetic
    # FEATURE_SYNONYMS expansions (e.g. "spor" → ["spor","rahat"]) that
    # would otherwise suppress the broad-query follow-up.
    q_text_lower = query.lower()
    features = parsed_query.get("features", [])
    for f in features:
        f_words = set(re.findall(r"\w+", str(f).lower()))
        if f_words.issubset(category_words):
            continue
        if any(fw in q_text_lower for fw in f_words):
            return True

    # 4. Contexts (that are not part of category/product name)
    contexts = parsed_query.get("contexts", [])
    for c in contexts:
        c_words = set(re.findall(r"\w+", str(c).lower()))
        if c_words.issubset(category_words):
            continue
        if any(cw in q_text_lower for cw in c_words):
            return True

    # 5. User problem terms
    if extract_user_problem(query) is not None:
        return True

    # 6. Explicit usage phrases or specific details (that are not category words)
    usage_phrases = [
        "özel gün", "ozel gun", "günlük kullanım", "gunluk kullanim", "günlük", "gunluk",
        "kamp yemeği", "kamp yemegi", "koşu", "kosu", "oyun", "ofis", "okul"
    ]
    q_lower = query.lower()
    for phrase in usage_phrases:
        if re.search(rf"\b{re.escape(phrase)}\b", q_lower):
            phrase_words = set(phrase.split())
            if not phrase_words.issubset(category_words):
                return True

    # 7. Word difference heuristic (additional descriptive terms)
    q_words = set(re.sub(r"[^\w\s]", " ", query.lower()).split())
    
    filler_words = {
        "öner", "oner", "öneri", "oneri", "tavsiye", "tavsiyesi",
        "arıyorum", "ariyorum", "istiyorum", "lazım", "lazim",
        "ürün", "urun", "şey", "sey", "bir", "için", "icin",
        "ve", "veya", "en", "daha", "lütfen", "lutfen", "bakıyorum",
        "bakiyorum", "almak", "istiyorum", "bul", "getir", "göster",
        "goster", "yardımcı", "ol", "olsun", "tarzı", "tarzi",
        "model", "modelleri", "seçenekleri", "secenekleri",
        "ararım", "ararim", "lazımdı", "lazimdi", "istemiştim",
        "istemistim", "varsa", "önerir", "önerirsin", "onerir",
        "yönlendir", "yonlendir", "arıyoruz", "ariyoruz", "yardım",
        "yardim", "destek", "malzeme", "malzemeleri", "malzemesi",
        "adeti", "adet", "tane", "istemiş", "istemis",
        # Inflected forms — Turkish suffixes on the broad/intent stems
        "ürünü", "urunu", "ürüne", "urune", "ürünler", "urunler",
        "ürünleri", "urunleri", "ürünlerini", "urunlerini",
        "ürünlerden", "urunlerden", "ürünün", "urunun",
        "ürününü", "urununu", "üründen", "urunden", "üründe", "urunde",
        "şeyi", "seyi", "şeyler", "seyler", "şeyleri", "seyleri",
        "şeylere", "seylere", "şeye", "seye", "şeyden", "seyden",
        "almalıyım", "almaliyim", "alabilirim", "alır", "alir",
        "yapabilirim", "yapabilir", "yapmalıyım", "yapmaliyim",
        "arıyor", "ariyor", "arıyorlar", "ariyorlar",
        "biraz", "lazımmış", "lazimmis",
    }
    
    extra_words = q_words - category_words - filler_words
    extra_words = {w for w in extra_words if not w.isdigit()}
    
    if len(extra_words) > 0:
        return True

    return False


def _build_soft_followup_question(parsed_query: dict, query: str) -> str:
    """Build a soft, category-specific follow-up question for generic queries."""
    q_lower = query.lower()
    
    pt = parsed_query.get("product_type")
    sc = parsed_query.get("sub_category")
    mc = parsed_query.get("main_category")
    
    pt_lower = str(pt).lower() if pt else ""
    sc_lower = str(sc).lower() if sc else ""
    mc_lower = str(mc).lower() if mc else ""
    
    # 1. Elbise
    if "elbise" in q_lower or sc_lower == "elbise" or pt_lower in ["abiye", "yazlık"]:
        return "Daha iyi bir öneri için elbiseyi günlük kullanım mı yoksa özel bir gün için mi arıyorsunuz? Renk veya fiyat aralığı tercihinizi belirtebilirsiniz."
        
    # 2. Ayakkabı
    if "ayakkabı" in q_lower or "ayakkabi" in q_lower or mc_lower == "ayakkabı" or sc_lower in ["sneaker", "spor ayakkabı", "outdoor ayakkabı", "bot"]:
        return "Daha iyi bir öneri için ayakkabıyı günlük kullanım, koşu, spor veya bot/sandalet gibi hangi amaçla arıyorsunuz? Fiyat aralığı da belirtebilirsiniz."
        
    # 3. Şampuan
    if "şampuan" in q_lower or "sampuan" in q_lower or pt_lower in ["şampuan", "kuru şampuan"]:
        return "Daha iyi bir şampuan önerisi için saç tipinizi ve saç problemi (kuru, yağlı, kepek veya dökülme gibi) gibi ihtiyaçlarınızı belirtebilirsiniz."
        
    # 4. Parfüm
    if "parfüm" in q_lower or "parfum" in q_lower or sc_lower == "parfüm":
        return "Daha iyi bir öneri için parfümü günlük kullanım mı yoksa özel günler için mi arıyorsunuz? Koku tarzı veya fiyat aralığı tercihinizi yazabilirsiniz."
        
    # 5. Kulaklık
    if "kulaklık" in q_lower or "kulaklik" in q_lower or pt_lower in ["kulaklık", "kulak içi kulaklık"]:
        return "Daha iyi bir kulaklık önerisi için kablosuz, oyuncu veya gürültü önleme (ANC) gibi hangi özellikleri tercih edersiniz? Bütçe de belirtebilirsiniz."
        
    # Fallback
    return "Daha net öneri için kullanım amacı, fiyat aralığı veya tercih ettiğiniz özellikleri yazabilirsiniz."


def build_response_plan(
    parsed_query: dict,
    query: str,
    df=None,
    original_query: str | None = None,
) -> ResponsePlan:
    """
    Determine the response mode and metadata from parsed_query output.

    Parameters
    ----------
    parsed_query : dict
        Output of ``parse_query()``.
    query : str
        The search query (normalized or original).
    df : DataFrame, optional
        Product DataFrame — used to determine top product_types for
        broad_search mode.

    Returns
    -------
    ResponsePlan
        The response plan with mode, flags, and metadata.
    """
    has_product_type = parsed_query.get("product_type") is not None
    has_main_category = parsed_query.get("main_category") is not None
    has_sub_category = parsed_query.get("sub_category") is not None
    has_features = len(parsed_query.get("features", [])) > 0
    has_contexts = len(parsed_query.get("contexts", [])) > 0
    has_price = (
        parsed_query.get("min_price") is not None
        or parsed_query.get("max_price") is not None
    )
    has_target_group = parsed_query.get("target_group") is not None

    has_any_signal = any([
        has_main_category, has_sub_category, has_product_type,
        has_target_group, has_features, has_contexts, has_price,
    ])

    # Extract semantic context — check both the normalized and (when
    # available) original query so an Ollama expansion doesn't hide a
    # problem the user actually stated.
    user_problem = extract_user_problem(query)
    if user_problem is None and original_query:
        user_problem = extract_user_problem(original_query)
    context_area = extract_context_area(query)

    # Specificity check — base the "did the user provide details?" decision on
    # the user's ORIGINAL words, not the Ollama-normalized query.  Normalization
    # can add a target group/category the user never typed (e.g. "elbise öner"
    # → "kadın elbise"), which would otherwise suppress the soft follow-up that
    # simple generic queries should still receive.
    has_det = query_has_details(parsed_query, original_query or query)

    # ---- Decision tree ----

    # 1. No product signal at all → clarification_only
    if not has_any_signal:
        return ResponsePlan(mode=MODE_CLARIFICATION_ONLY)

    # 2a. user_problem + sub_category + no product_type → broad_search within sub.
    #     The user named a problem broadly (e.g. "saç dökülmesi için ürün öner")
    #     — show diverse product types within the relevant care area instead
    #     of locking onto whichever single product_type the taxonomy matched
    #     most strongly.  has_main_category alone is enough to qualify the
    #     plan; the candidate pool is still filtered by sub_category via
    #     apply_filters() upstream.
    if (
        not has_product_type
        and has_sub_category
        and user_problem is not None
    ):
        sub_cat = parsed_query.get("sub_category")
        top_product_types = []
        if df is not None and sub_cat is not None:
            sub_products = df[
                df["sub_category"].astype(str).str.lower()
                == str(sub_cat).lower()
            ]
            type_counts = (
                sub_products["product_type"]
                .dropna()
                .value_counts()
                .head(8)
            )
            top_product_types = type_counts.index.tolist()

        return ResponsePlan(
            mode=MODE_BROAD_SEARCH,
            has_explicit_product_type=False,
            has_main_category=has_main_category,
            has_sub_category=True,
            user_problem=user_problem,
            context_area=context_area,
            diversify_results=True,
            should_ask_followup=False,
            followup_question=None,
            top_product_types=top_product_types,
        )

    # 2. Has product_type or sub_category → focused_search
    #    The user knows what kind of product they want.
    if has_product_type or has_sub_category:
        return ResponsePlan(
            mode=MODE_FOCUSED_SEARCH,
            has_explicit_product_type=has_product_type,
            has_main_category=has_main_category,
            has_sub_category=has_sub_category,
            user_problem=user_problem,
            context_area=context_area,
            diversify_results=False,
            should_ask_followup=not has_det,
            followup_question=_build_soft_followup_question(parsed_query, query) if not has_det else None,
        )

    # 3. Has main_category or context but no product_type → broad_search
    #    Show diverse products + ask follow-up.
    if has_main_category or has_contexts or context_area:
        main_cat = parsed_query.get("main_category")

        # Determine top product_types for this category (for rewriter)
        top_product_types = []
        if df is not None and main_cat is not None:
            category_products = df[
                df["main_category"].astype(str).str.lower()
                == str(main_cat).lower()
            ]
            type_counts = (
                category_products["product_type"]
                .dropna()
                .value_counts()
                .head(8)
            )
            top_product_types = type_counts.index.tolist()

        return ResponsePlan(
            mode=MODE_BROAD_SEARCH,
            has_explicit_product_type=False,
            has_main_category=has_main_category,
            has_sub_category=False,
            user_problem=user_problem,
            context_area=context_area,
            diversify_results=True,
            should_ask_followup=not has_det,
            followup_question=_build_followup_question(context_area, user_problem, main_cat) if not has_det else None,
            top_product_types=top_product_types,
        )

    # 4. Has features or price or target_group but no category
    #    This is an edge case: e.g. "1500 TL altında yazlık erkek"
    #    Currently handled as clarification by is_query_too_general().
    #    Keep as clarification_only since we don't know what category.
    if has_features or has_price or has_target_group:
        return ResponsePlan(mode=MODE_CLARIFICATION_ONLY)

    # 5. Fallback: clarification_only
    return ResponsePlan(mode=MODE_CLARIFICATION_ONLY)
