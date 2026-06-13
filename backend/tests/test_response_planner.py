"""
Unit tests for the response_planner module.

Tests the deterministic decision tree that maps parsed_query output
into response modes (focused_search, broad_search, clarification_only).
"""

import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from response_planner import (
    build_response_plan,
    extract_user_problem,
    extract_context_area,
    MODE_FOCUSED_SEARCH,
    MODE_BROAD_SEARCH,
    MODE_CLARIFICATION_ONLY,
)


# ---------------------------------------------------------------------------
# extract_user_problem
# ---------------------------------------------------------------------------

def test_extract_problem_hair_loss():
    assert extract_user_problem("saç dökülmesi için şampuan öner") == "saç dökülmesi"


def test_extract_problem_dry_skin():
    assert extract_user_problem("kuru cilt için nemlendirici") == "kuru cilt"


def test_extract_problem_oily_hair():
    assert extract_user_problem("yağlı saç için şampuan") == "yağlı saç"


def test_extract_problem_dandruff():
    assert extract_user_problem("kepek problemi var") == "kepek"


def test_extract_problem_pimple():
    assert extract_user_problem("sivilce için temizleyici") == "sivilce"


def test_extract_problem_diaper_rash():
    assert extract_user_problem("pişik için krem") == "pişik"


def test_extract_problem_none():
    assert extract_user_problem("ayakkabı arıyorum") is None


def test_extract_problem_none_camp():
    assert extract_user_problem("kamp için ürün arıyorum") is None


# ---------------------------------------------------------------------------
# extract_context_area
# ---------------------------------------------------------------------------

def test_extract_context_camp():
    assert extract_context_area("kamp için ürün arıyorum") == "kamp"


def test_extract_context_sport():
    assert extract_context_area("spor ürünü öner") == "spor"


def test_extract_context_baby():
    assert extract_context_area("bebek için bakım ürünü") == "bebek"


def test_extract_context_none():
    assert extract_context_area("şampuan öner") is None


# ---------------------------------------------------------------------------
# build_response_plan — focused_search
# ---------------------------------------------------------------------------

def test_focused_with_product_type():
    """When product_type is set, mode should be focused_search."""
    parsed = {
        "main_category": "Kişisel Bakım",
        "sub_category": "Saç Bakımı",
        "product_type": "Şampuan",
        "target_group": None,
        "features": ["saç dökülmesi"],
        "contexts": [],
        "min_price": None,
        "max_price": None,
    }
    plan = build_response_plan(parsed, "saç dökülmesi için şampuan öner")
    assert plan.mode == MODE_FOCUSED_SEARCH
    assert plan.has_explicit_product_type is True
    assert plan.diversify_results is False
    assert plan.user_problem == "saç dökülmesi"


def test_focused_with_sub_category():
    """When sub_category is set (no product_type), still focused_search."""
    parsed = {
        "main_category": "Giyim",
        "sub_category": "Elbise",
        "product_type": None,
        "target_group": "Kadın",
        "features": [],
        "contexts": [],
        "min_price": None,
        "max_price": None,
    }
    plan = build_response_plan(parsed, "kadın elbise öner")
    assert plan.mode == MODE_FOCUSED_SEARCH
    assert plan.has_explicit_product_type is False
    assert plan.has_sub_category is True
    assert plan.diversify_results is False


# ---------------------------------------------------------------------------
# build_response_plan — broad_search
# ---------------------------------------------------------------------------

def test_broad_with_main_category_only():
    """main_category without product_type → broad_search."""
    parsed = {
        "main_category": "Ayakkabı",
        "sub_category": None,
        "product_type": None,
        "target_group": None,
        "features": [],
        "contexts": [],
        "min_price": None,
        "max_price": None,
    }
    plan = build_response_plan(parsed, "ayakkabı öner")
    assert plan.mode == MODE_BROAD_SEARCH
    assert plan.diversify_results is True
    assert plan.should_ask_followup is True
    assert plan.followup_question is not None


def test_broad_with_context():
    """Context keyword (kamp) without product_type → broad_search."""
    parsed = {
        "main_category": "Kamp",
        "sub_category": None,
        "product_type": None,
        "target_group": None,
        "features": [],
        "contexts": ["kamp"],
        "min_price": None,
        "max_price": None,
    }
    plan = build_response_plan(parsed, "kamp için ürün arıyorum")
    assert plan.mode == MODE_BROAD_SEARCH
    assert plan.diversify_results is True
    assert plan.context_area == "kamp"


def test_broad_with_problem_no_product_type():
    """Problem + sub_category + no product_type → broad_search (diversified
    within the relevant care area).

    Previously this case fell into focused_search because sub_category
    was set, which let one product_type dominate the top-5.  When the
    user states only a problem and no explicit product_type, the right
    behaviour is to broaden across product_types within the sub_category.
    """
    parsed = {
        "main_category": "Kişisel Bakım",
        "sub_category": "Saç Bakımı",
        "product_type": None,
        "target_group": None,
        "features": ["saç dökülmesi"],
        "contexts": [],
        "min_price": None,
        "max_price": None,
    }
    plan = build_response_plan(parsed, "saç dökülmesi için ürün öner")
    assert plan.mode == MODE_BROAD_SEARCH
    assert plan.diversify_results is True
    assert plan.user_problem == "saç dökülmesi"
    assert plan.has_sub_category is True


# ---------------------------------------------------------------------------
# build_response_plan — clarification_only
# ---------------------------------------------------------------------------

def test_clarification_no_signals():
    """No product signals at all → clarification_only."""
    parsed = {
        "main_category": None,
        "sub_category": None,
        "product_type": None,
        "target_group": None,
        "features": [],
        "contexts": [],
        "min_price": None,
        "max_price": None,
    }
    plan = build_response_plan(parsed, "ürün öner")
    assert plan.mode == MODE_CLARIFICATION_ONLY


def test_clarification_price_only():
    """Only price, no category → clarification_only."""
    parsed = {
        "main_category": None,
        "sub_category": None,
        "product_type": None,
        "target_group": None,
        "features": [],
        "contexts": [],
        "min_price": None,
        "max_price": 1500,
    }
    plan = build_response_plan(parsed, "1500 TL altında ürün")
    assert plan.mode == MODE_CLARIFICATION_ONLY


# ---------------------------------------------------------------------------
# Specificity & Soft Follow-Up Tests
# ---------------------------------------------------------------------------

def test_generic_queries_have_followup():
    """Generic category/product type queries without details should trigger follow-up."""
    # elbise öner
    p1 = {"main_category": "Giyim", "sub_category": "Elbise", "product_type": None}
    plan1 = build_response_plan(p1, "elbise öner")
    assert plan1.should_ask_followup is True
    assert "elbise" in plan1.followup_question.lower()

    # ayakkabı öner
    p2 = {"main_category": "Ayakkabı", "sub_category": None, "product_type": None}
    plan2 = build_response_plan(p2, "ayakkabı öner")
    assert plan2.should_ask_followup is True
    assert "ayakkabı" in plan2.followup_question.lower()

    # şampuan öner
    p3 = {"main_category": "Kişisel Bakım", "sub_category": "Saç Bakımı", "product_type": "Şampuan"}
    plan3 = build_response_plan(p3, "şampuan öner")
    assert plan3.should_ask_followup is True
    assert "şampuan" in plan3.followup_question.lower()

    # tencere öner
    p4 = {"main_category": "Mutfak", "sub_category": None, "product_type": "Tencere Seti"}
    plan4 = build_response_plan(p4, "tencere öner")
    assert plan4.should_ask_followup is True
    assert plan4.followup_question == "Daha net öneri için kullanım amacı, fiyat aralığı veya tercih ettiğiniz özellikleri yazabilirsiniz."

    # defter öner
    p5 = {"main_category": "Kırtasiye", "sub_category": "Defter", "product_type": "Defter"}
    plan5 = build_response_plan(p5, "defter öner")
    assert plan5.should_ask_followup is True
    assert plan5.followup_question == "Daha net öneri için kullanım amacı, fiyat aralığı veya tercih ettiğiniz özellikleri yazabilirsiniz."

    # robot süpürge öner
    p6 = {"main_category": "Ev & Yaşam", "sub_category": "Temizlik", "product_type": "Robot Süpürge"}
    plan6 = build_response_plan(p6, "robot süpürge öner")
    assert plan6.should_ask_followup is True
    assert plan6.followup_question == "Daha net öneri için kullanım amacı, fiyat aralığı veya tercih ettiğiniz özellikleri yazabilirsiniz."

    # çanta öner
    p7 = {"main_category": "Aksesuar", "sub_category": "Çanta", "product_type": None}
    plan7 = build_response_plan(p7, "çanta öner")
    assert plan7.should_ask_followup is True
    assert plan7.followup_question == "Daha net öneri için kullanım amacı, fiyat aralığı veya tercih ettiğiniz özellikleri yazabilirsiniz."

    # nemlendirici öner
    p8 = {"main_category": "Kişisel Bakım", "sub_category": "Cilt Bakımı", "product_type": "Nemlendirici"}
    plan8 = build_response_plan(p8, "nemlendirici öner")
    assert plan8.should_ask_followup is True
    assert plan8.followup_question == "Daha net öneri için kullanım amacı, fiyat aralığı veya tercih ettiğiniz özellikleri yazabilirsiniz."

    # bebek şampuanı öner
    p9 = {"main_category": "Anne & Bebek", "sub_category": "Bakım", "product_type": "Bebek Şampuanı", "target_group": "Bebek"}
    plan9 = build_response_plan(p9, "bebek şampuanı öner")
    assert plan9.should_ask_followup is True
    # Should use şampuan specific question because "şampuan" matches keyword check in _build_soft_followup_question
    assert "şampuan" in plan9.followup_question.lower()


def test_detailed_queries_do_not_have_followup():
    """Queries that specify details should not trigger follow-up."""
    # özel gün için kadın elbise öner
    p1 = {"main_category": "Giyim", "sub_category": "Elbise", "product_type": None, "target_group": "Kadın"}
    plan1 = build_response_plan(p1, "özel gün için kadın elbise öner")
    assert plan1.should_ask_followup is False

    # saç dökülmesi için şampuan öner
    p2 = {"main_category": "Kişisel Bakım", "sub_category": "Saç Bakımı", "product_type": "Şampuan", "features": ["saç dökülmesi"]}
    plan2 = build_response_plan(p2, "saç dökülmesi için şampuan öner")
    assert plan2.should_ask_followup is False

    # yağlı saç için şampuan
    p3 = {"main_category": "Kişisel Bakım", "sub_category": "Saç Bakımı", "product_type": "Şampuan"}
    plan3 = build_response_plan(p3, "yağlı saç için şampuan")
    assert plan3.should_ask_followup is False

    # 1500 TL üstü yazlık spor papuç arıyorum
    p4 = {"main_category": "Ayakkabı", "sub_category": None, "product_type": None, "min_price": 1500}
    plan4 = build_response_plan(p4, "1500 TL üstü yazlık spor papuç arıyorum")
    assert plan4.should_ask_followup is False

    # telefon için taşınabilir şarj lazım
    p5 = {"main_category": "Elektronik", "sub_category": "Telefon Aksesuarı", "product_type": "Powerbank"}
    plan5 = build_response_plan(p5, "telefon için taşınabilir şarj lazım")
    assert plan5.should_ask_followup is False

    # kamp yemeği için ocak
    p6 = {"main_category": "Kamp", "sub_category": "Pişirme", "product_type": "Kamp Ocağı", "contexts": ["kamp"]}
    plan6 = build_response_plan(p6, "kamp yemeği için ocak")
    assert plan6.should_ask_followup is False
