# Pre-DB Migration Plan

_Last updated: 2026-06-13_

This document captures the readiness state of the project before migrating the
product catalog from `backend/products.csv` to a database, the low-risk
cleanups applied in this round, and the work intentionally deferred until after
migration.

---

## 1. Summary of DB readiness

The data layer is **well-isolated** and the catalog is **clean**:

- 1000 products, 0 missing required fields, 0 duplicate rows, all prices numeric and > 0.
- Only four code paths read the CSV: `data_loader.py`, `main.py`, `eval/run_eval.py`, and `tests/test_query_parser.py`.
- `chat_normalizer.py` and `response_rewriter.py` have **no** data coupling.

Migration is **low-risk provided one architectural contract is honored**: the
product DataFrame row order must stay identical to the order
`product_embeddings` was built from. The whole system assumes the catalog is
loaded **once at startup into an in-memory pandas DataFrame**; as long as the DB
migration preserves that shape (DB → load all rows into the same df at boot,
`ORDER BY id`), the change is contained.

**Decision: READY TO START DB MIGRATION** after the cleanups below (now applied).

---

## 2. Problems found before DB migration

| # | Severity | Problem | Status |
|---|----------|---------|--------|
| 1 | 🔴 Contract | `product_embeddings` is a positional array indexed by `df.index` in `search_engine.semantic_search`. Works only because of stable row order (`reset_index(drop=True)`). A DB reorder corrupts results silently. | Documented |
| 2 | 🟠 Correctness | `mode().iloc[0]` category inference; 11 product_types + 11 sub_categories span multiple main_categories, so ties could flip with row order. | Fixed (deterministic) |
| 3 | 🟡 Fragility | `data_loader` read CSV without `encoding="utf-8-sig"`; a re-export with a BOM could break the required-column check. | Fixed |
| 4 | 🟡 Doc | Stale comments referencing a "750-product catalog" (actual size: 1000). | Fixed |
| 5 | 🟡 Data | Orphan taxonomy rows `Kışlık` and `Serum` (product_type) with 0 backing products — can bias broad queries. | Removed |
| 6 | ℹ️ Info | Taxonomy is a curated semantic-hint subset (sub_category 25/78, product_type 34/499 covered), not an authoritative map. | Documented (no change) |
| 7 | ⏭️ Deferred | Normalizer prompt lists catalog *columns* but does not constrain output to catalog *values* → hallucinations (e.g. "baharatlık"). Needs authoritative DB category list. | Post-DB |
| 8 | ⏭️ Deferred | High product_type fragmentation (281 single-product types). | Post-DB |

---

## 3. Pre-DB checklist

* [x] Add utf-8-sig CSV loading
* [x] Document embedding/DataFrame order contract
* [x] Make category tie-breaking deterministic
* [x] Update stale 750-product comments
* [x] Remove verified orphan taxonomy rows: Kışlık, Serum

---

## 4. Post-DB checklist

* [ ] Move catalog source from CSV to DB while preserving DataFrame shape
* [ ] Load products with stable ORDER BY id
* [ ] Rebuild embeddings from the exact DB-loaded product order
* [ ] Consider product_id-keyed embeddings later
* [ ] Re-test Ollama model alternatives after DB baseline
* [ ] Consider product_type consolidation after DB migration
* [ ] Constrain the normalizer's output to authoritative DB category/product_type values
* [ ] Re-tune `is_query_too_general` thresholds for the true catalog size

---

## 5. Changes applied in this round

All changes are minimal, logic-preserving, and **do not touch search scoring,
the frontend, or product data**.

1. **Defensive CSV loading** — `backend/data_loader.py`
   - `load_products` and `load_taxonomy` now read with `encoding="utf-8-sig"`.

2. **Embedding / DataFrame order contract documented** — three sites
   - `backend/data_loader.py`: comment on the `reset_index(drop=True)` that establishes the stable 0..N-1 positional index.
   - `backend/main.py`: comment at the `product_embeddings` build site.
   - `backend/search_engine.py`: comment at the `candidate_df.index` → embeddings lookup in `semantic_search`.

3. **Deterministic category inference** — `backend/query_parser.py`
   - Added `_most_common_category(series)`: most-frequent value with an explicit alphabetical tie-break, independent of row order.
   - Replaced all three `mode().iloc[0]` usages (`infer_main_category_from_parsed` ×2, `normalize_category_consistency` ×1) with this helper. Behavior is unchanged on the current data (pandas `mode()` already sorts ascending) but the guarantee is now explicit and migration-safe.

4. **Stale comments updated** — `backend/query_parser.py`
   - Two "750-product catalog" comments reworded to "the current catalog". Comment-only; no logic change.

5. **Taxonomy orphan rows removed** — `backend/taxonomy.csv`
   - Verified `Kışlık` (0 products) and `Serum` (0 products) have no backing product_type, then removed only those two rows (71 → 69 data rows). No other taxonomy content changed.

**Changed files:** `backend/data_loader.py`, `backend/main.py`,
`backend/search_engine.py`, `backend/query_parser.py`, `backend/taxonomy.csv`.

---

## 6. Test results

| Suite | Command | Result |
|-------|---------|--------|
| Unit tests | `python -m pytest` | **30 passed** |
| Gold eval | `python eval/run_eval.py --show-failures` | Top-1 **0.974** (38/39), Top-3 **1.000** (39/39), 0 top-k failures |
| Stress eval | `python eval/run_stress_eval.py --show-failures` | Top-1 **0.963** (77/80), Top-3 **1.000** (80/80), 0 top-k failures |

No regressions introduced by this round — Top-3 hit rate is 100% on both eval
sets and all unit tests pass.

---

## 7. Final DB migration readiness decision

**✅ READY TO START DB MIGRATION.**

The catalog is clean, the data dependency is isolated, the low-risk cleanups are
applied, and the one hard requirement is documented at every relevant code site:
**the DB must load products in a stable order (`ORDER BY id`) and embeddings must
be rebuilt from that exact order.** Capture the test/eval numbers above as the
pre-migration baseline; after migration, re-run all three suites and pay special
attention to the cross-category-ambiguous queries (`tencere seti`, `sırt çantası`,
`uyku tulumu`, `termos bardak`) to confirm ordering was preserved.
