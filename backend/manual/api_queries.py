"""
Strict manual-regression harness for the AI-Market ``POST /search`` endpoint.

Runs the shared scenario matrix (:mod:`manual.scenarios`) against a live API
and enforces only the **deterministic** expectations — the ones that come from
the rule tree in ``response_planner.py`` and the status branches in
``main.py``, not from Ollama wording. A strict failure is a real regression, so
this script exits non-zero when any strict check fails.

Runs OUTSIDE pytest (Ollama is non-deterministic):

    python -m manual.api_queries
    # or, from backend/:  .venv/bin/python -m manual.api_queries

Warning-only / Ollama-sensitive checks live in ``ollama_regression.py``.
"""

from __future__ import annotations

import json
import re
import sys
import urllib.request
from collections import defaultdict

from manual.scenarios import (
    ALL_SCENARIOS,
    CHECK_FOLLOWUP,
    CHECK_MAIN_CATEGORY,
    CHECK_MODE,
    CHECK_NO_CLARIFICATION,
    CHECK_NO_FABRICATION,
    CHECK_NO_FORBIDDEN_TYPES,
    CHECK_PRICE,
    CHECK_PRIMARY_FIRST,
    CHECK_PRODUCTS,
    Scenario,
)

API_URL = "http://127.0.0.1:8000/search"
TIMEOUT = 60


# ---------------------------------------------------------------------------
# HTTP
# ---------------------------------------------------------------------------

def search(query: str) -> dict:
    data = json.dumps({"query": query}).encode("utf-8")
    request = urllib.request.Request(
        API_URL,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
        return json.loads(response.read().decode("utf-8"))


# ---------------------------------------------------------------------------
# Check evaluators — each returns (ok: bool, detail: str)
# ---------------------------------------------------------------------------

def _price_to_int(price: str) -> int | None:
    digits = re.sub(r"[^\d]", "", str(price))
    return int(digits) if digits else None


def check_mode(sc: Scenario, resp: dict) -> tuple[bool, str]:
    actual = resp.get("response_mode")
    return actual == sc.expect_mode, f"response_mode={actual!r} (want {sc.expect_mode!r})"


def check_products(sc: Scenario, resp: dict) -> tuple[bool, str]:
    has = bool(resp.get("products"))
    return has == sc.expect_products, f"products={len(resp.get('products') or [])} (want {'>0' if sc.expect_products else '0'})"


def check_followup(sc: Scenario, resp: dict) -> tuple[bool, str]:
    has = bool(resp.get("follow_up_question"))
    return has == sc.expect_followup, f"follow_up_present={has} (want {sc.expect_followup})"


def check_no_clarification(sc: Scenario, resp: dict) -> tuple[bool, str]:
    flag = bool(resp.get("needs_clarification"))
    return flag is False, f"needs_clarification={flag} (want False)"


def check_main_category(sc: Scenario, resp: dict) -> tuple[bool, str]:
    actual = (resp.get("parsed_query") or {}).get("main_category")
    return actual == sc.expect_main_category, f"main_category={actual!r} (want {sc.expect_main_category!r})"


def check_no_fabrication(sc: Scenario, resp: dict) -> tuple[bool, str]:
    n = len(resp.get("products") or [])
    return n == 0, f"products={n} (want 0 — no invented catalog item)"


def check_price(sc: Scenario, resp: dict) -> tuple[bool, str]:
    pq = resp.get("parsed_query") or {}
    lo, hi = pq.get("min_price"), pq.get("max_price")
    if lo is None and hi is None:
        return False, "no price bound parsed from query"
    bad = []
    for p in resp.get("products") or []:
        val = _price_to_int(p.get("price"))
        if val is None:
            continue
        if lo is not None and val < lo:
            bad.append(f"{val}<{lo}")
        if hi is not None and val > hi:
            bad.append(f"{val}>{hi}")
    return not bad, f"bounds=[{lo},{hi}] violations={bad}" if bad else f"bounds=[{lo},{hi}] ok"


def check_primary_first(sc: Scenario, resp: dict) -> tuple[bool, str]:
    """Verify the grouped result is primary-first and has the expected grouping.

    Feature-gated: when the server does not emit grouping fields (i.e.
    AI_MARKET_GROUPED_RANKING is off), this is skipped (passes) so the strict
    suite stays green against a default server. When grouping IS enabled, it
    enforces two things deterministically:
      * ordering — every "primary" precedes every "alternative" (no interleave),
      * expect_result_grouping — result_grouping matches the scenario, if set.
    """
    products = resp.get("products") or []
    grouping = resp.get("result_grouping")
    has_labels = any("match_group" in p for p in products)

    if grouping is None and not has_labels:
        return True, "grouping disabled on server — primary_first skipped"

    groups = [p.get("match_group") for p in products]
    first_alt = next(
        (i for i, g in enumerate(groups) if g == "alternative"), len(groups)
    )
    ordering_ok = all(g == "primary" for g in groups[:first_alt]) and all(
        g == "alternative" for g in groups[first_alt:]
    )

    grouping_ok = True
    detail = f"result_grouping={grouping!r} order={groups}"
    if sc.expect_result_grouping is not None:
        grouping_ok = grouping == sc.expect_result_grouping
        detail += f" want={sc.expect_result_grouping!r}"

    return ordering_ok and grouping_ok, detail


def check_no_forbidden_types(sc: Scenario, resp: dict) -> tuple[bool, str]:
    """No returned product's sub_category/product_type may match a forbid_types term.

    Enforces explicit negative constraints ("mont veya kaban değil"): the
    rejected outerwear must never appear in the visible results. Each product's
    tags carry [main, sub, target, product_type]; we scan sub_category and
    product_type for any forbidden substring (case-insensitive).
    """
    forbidden = [f.lower() for f in sc.forbid_types]
    if not forbidden:
        return True, "no forbid_types set"
    offenders = []
    for p in resp.get("products") or []:
        tags = [str(t).lower() for t in (p.get("tags") or [])]
        haystack = " ".join(tags)
        for term in forbidden:
            if term in haystack:
                offenders.append(p.get("name"))
                break
    return not offenders, (
        f"forbidden={sc.forbid_types} offenders={offenders}" if offenders
        else f"forbidden={sc.forbid_types} none present"
    )


CHECK_DISPATCH = {
    CHECK_MODE: check_mode,
    CHECK_PRODUCTS: check_products,
    CHECK_FOLLOWUP: check_followup,
    CHECK_NO_CLARIFICATION: check_no_clarification,
    CHECK_MAIN_CATEGORY: check_main_category,
    CHECK_NO_FABRICATION: check_no_fabrication,
    CHECK_PRICE: check_price,
    CHECK_PRIMARY_FIRST: check_primary_first,
    CHECK_NO_FORBIDDEN_TYPES: check_no_forbidden_types,
}


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

def evaluate(sc: Scenario, resp: dict) -> list[tuple[str, bool, str]]:
    """Evaluate every strict check for one scenario. Returns (check, ok, detail)."""
    results = []
    for name in sc.strict_checks():
        evaluator = CHECK_DISPATCH.get(name)
        if evaluator is None:
            results.append((name, False, "no evaluator registered"))
            continue
        ok, detail = evaluator(sc, resp)
        results.append((name, ok, detail))
    return results


def main() -> int:
    print("=" * 80)
    print("AI-Market — STRICT manual regression (POST /search)")
    print("=" * 80)

    per_category_pass: dict[str, int] = defaultdict(int)
    per_category_fail: dict[str, int] = defaultdict(int)
    failures: list[tuple[Scenario, list[tuple[str, bool, str]]]] = []
    errors: list[tuple[Scenario, str]] = []

    for sc in ALL_SCENARIOS:
        try:
            resp = search(sc.query)
        except Exception as e:  # noqa: BLE001 — surface any transport/HTTP failure
            errors.append((sc, str(e)))
            per_category_fail[sc.category] += 1
            print(f"\n[{sc.category}] {sc.kind:<9} {sc.query!r}")
            print(f"   ❌ ERROR: {e}")
            continue

        checks = evaluate(sc, resp)
        scenario_ok = all(ok for _, ok, _ in checks)

        if scenario_ok:
            per_category_pass[sc.category] += 1
            print(f"\n[{sc.category}] {sc.kind:<9} {sc.query!r}")
            print(f"   ✅ PASS  ({len(checks)} strict checks)")
        else:
            per_category_fail[sc.category] += 1
            failures.append((sc, checks))
            print(f"\n[{sc.category}] {sc.kind:<9} {sc.query!r}")
            print("   ❌ FAIL")
            for name, ok, detail in checks:
                mark = "✅" if ok else "❌"
                print(f"      {mark} {name}: {detail}")

    # ---- Per-category summary table ----
    print("\n" + "=" * 80)
    print("Per-category summary")
    print("-" * 80)
    print(f"{'Category':<18} {'Pass':>5} {'Fail':>5}")
    total_pass = total_fail = 0
    for cat in sorted(set(per_category_pass) | set(per_category_fail)):
        p, f = per_category_pass[cat], per_category_fail[cat]
        total_pass += p
        total_fail += f
        flag = "" if f == 0 else "  ← FAIL"
        print(f"{cat:<18} {p:>5} {f:>5}{flag}")
    print("-" * 80)
    print(f"{'TOTAL':<18} {total_pass:>5} {total_fail:>5}")

    if errors:
        print(f"\n⚠️  {len(errors)} scenario(s) errored (transport/HTTP). Is the API running at {API_URL}?")

    if total_fail:
        print(f"\n❌ STRICT REGRESSION: {total_fail} scenario(s) failed.")
        return 1

    print(f"\n✅ All {total_pass} strict scenarios passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
