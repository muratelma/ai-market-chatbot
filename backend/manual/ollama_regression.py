"""
Warning-only manual-regression harness for the Ollama intelligence layer.

Runs the SAME shared scenario matrix (:mod:`manual.scenarios`) as the strict
harness (``api_queries.py``), but evaluates only the **Ollama-sensitive**
expectations — the ones that depend on normalization / rewriting and may vary
between runs:

- exact ``response_mode`` on borderline single-word queries,
- inferred ``sub_category`` / ``product_type`` (e.g. problem→product),
- ``main_category`` where inference is non-deterministic,
- follow-up presence on focused (soft-followup) queries,
- multi-turn follow-up resolution via session memory.

Mismatches are reported as ⚠️ advisories. This script **always exits 0** —
Ollama variance must never break the build. Hard pass/fail invariants live in
``api_queries.py``.

Runs OUTSIDE pytest:

    python -m manual.ollama_regression
    # or, from backend/:  .venv/bin/python -m manual.ollama_regression
"""

from __future__ import annotations

import json
import urllib.request
from collections import defaultdict

from manual.api_queries import CHECK_DISPATCH
from manual.scenarios import (
    ALL_SCENARIOS,
    CHECK_SUB_OR_TYPE,
    Scenario,
)

API_URL = "http://127.0.0.1:8000/search"
TIMEOUT = 60


# ---------------------------------------------------------------------------
# HTTP (session-aware — needed for the multi-turn follow-up test)
# ---------------------------------------------------------------------------

def search(query: str, session_id: str | None = None) -> dict:
    payload: dict = {"query": query}
    if session_id:
        payload["session_id"] = session_id
    data = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        API_URL,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
        return json.loads(response.read().decode("utf-8"))


# ---------------------------------------------------------------------------
# Extra evaluator: sub_category / product_type inference (warning-only)
# ---------------------------------------------------------------------------

def check_sub_or_type(sc: Scenario, resp: dict) -> tuple[bool, str]:
    pq = resp.get("parsed_query") or {}
    sub = pq.get("sub_category")
    ptype = pq.get("product_type")
    want = sc.expect_sub_or_type
    ok = want in (sub, ptype)
    return ok, f"sub_category={sub!r} product_type={ptype!r} (want {want!r})"


WARNING_DISPATCH = {**CHECK_DISPATCH, CHECK_SUB_OR_TYPE: check_sub_or_type}


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

def evaluate_warnings(sc: Scenario, resp: dict) -> list[tuple[str, bool, str]]:
    """Evaluate the advisory (non-strict) checks for one scenario."""
    results = []
    for name in sc.warning_checks():
        evaluator = WARNING_DISPATCH.get(name)
        if evaluator is None:
            continue
        ok, detail = evaluator(sc, resp)
        results.append((name, ok, detail))
    return results


def _print_snapshot(resp: dict) -> None:
    pq = resp.get("parsed_query") or {}
    print(f"      mode={resp.get('response_mode')!r} "
          f"products={len(resp.get('products') or [])} "
          f"clarif={resp.get('needs_clarification')} "
          f"source={resp.get('response_source')!r}")
    print(f"      parsed: main={pq.get('main_category')!r} "
          f"sub={pq.get('sub_category')!r} type={pq.get('product_type')!r}")


def run_matrix() -> dict[str, int]:
    print("\n🔹 PART 1: Scenario matrix (advisory / Ollama-sensitive checks)")
    counts = defaultdict(int)  # match / mismatch / no-check / error

    for sc in ALL_SCENARIOS:
        warn_checks = sc.warning_checks()
        if not warn_checks:
            counts["no-check"] += 1
            continue

        print(f"\n[{sc.category}] {sc.kind:<9} {sc.query!r}")
        try:
            resp = search(sc.query)
        except Exception as e:  # noqa: BLE001
            counts["error"] += 1
            print(f"   ❌ ERROR: {e}")
            continue

        _print_snapshot(resp)
        for name, ok, detail in evaluate_warnings(sc, resp):
            if ok:
                counts["match"] += 1
                print(f"   ✓  {name}: {detail}")
            else:
                counts["mismatch"] += 1
                print(f"   ⚠️  {name}: {detail}")

    return counts


def run_followups() -> None:
    print("\n\n🔹 PART 2: Multi-turn follow-up (session memory — advisory)")

    conversations = [
        ("kamp için bir şey lazım", "yemek yapmalık"),
        ("2000 TL altında erkek ürün", "papuç olsun"),
    ]

    for opener, follow_up in conversations:
        print(f"\n📝 {opener!r} → {follow_up!r}")
        try:
            r1 = search(opener)
            print("   Turn 1:")
            _print_snapshot(r1)
            session_id = r1.get("session_id")
            if not session_id:
                print("   ⚠️  no session_id returned — cannot test follow-up")
                continue
            r2 = search(follow_up, session_id=session_id)
            print("   Turn 2 (follow-up):")
            _print_snapshot(r2)
            if not (r2.get("products") or r2.get("needs_clarification")):
                print("   ⚠️  follow-up produced neither products nor clarification")
        except Exception as e:  # noqa: BLE001
            print(f"   ❌ ERROR: {e}")


def main() -> int:
    print("=" * 80)
    print("AI-Market — Ollama intelligence layer (WARNING-ONLY regression)")
    print("=" * 80)

    counts = run_matrix()
    run_followups()

    print("\n" + "=" * 80)
    print("Advisory summary")
    print("-" * 80)
    print(f"  matched checks   : {counts['match']}")
    print(f"  ⚠️  mismatches    : {counts['mismatch']}")
    print(f"  scenarios w/o advisory checks: {counts['no-check']}")
    print(f"  errored scenarios: {counts['error']}")
    if counts["mismatch"]:
        print("\n⚠️  Advisory mismatches above are expected to vary with Ollama —"
              " review, but they do not fail the build.")
    print("\n✅ Done (always exit 0 — Ollama variance is not a hard failure).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
