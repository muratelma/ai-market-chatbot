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

* [x] Move catalog source from CSV to DB while preserving DataFrame shape
* [x] Load products with stable ORDER BY id
* [x] Rebuild embeddings from the exact DB-loaded product order
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

---

## 8. PostgreSQL DB migration baseline — COMPLETED ✅

_Completed: 2026-06-14_

The PostgreSQL catalog migration baseline is **done**. CSV remains the default
and is intentionally **not** removed from this branch.

**Infrastructure**

- PostgreSQL 16 and pgAdmin run via Docker (`docker-compose.yml`). PostgreSQL is
  reachable from the host at
  `postgresql://aimarket_user:aimarket_pass@localhost:5433/aimarket`; pgAdmin
  reaches it inside the Docker network at host `postgres`, port `5432`.
- Products were seeded into PostgreSQL successfully via
  `backend/scripts/seed_products_postgres.py` — 1000 rows, `id` assigned in CSV
  order (1..1000), re-runnable (TRUNCATE + reload).

**What changed (source)**

- `backend/database.py` (new): `load_products_from_db()` selects the original CSV
  columns `ORDER BY id` so the DataFrame matches CSV mode column-for-column.
- `backend/config.py`: `PRODUCT_SOURCE` (`csv` default / `db`), `DATABASE_URL`,
  `PRODUCTS_TABLE`.
- `backend/data_loader.py`: `load_products(source=...)` dispatches CSV/DB through a
  shared `_finalize_products` step (price coerce, dropna, `reset_index`) so both
  modes yield an identical shape and 0..N-1 positional index. Embeddings are
  rebuilt at startup from this exact DB-loaded order (ORDER CONTRACT preserved).
- `backend/.env.example`, `backend/requirements.txt` (`psycopg2-binary`).

**Verification**

- **Eval parity:** CSV mode and DB mode produced **identical** eval results —
  unit tests (30 passed), gold eval (Top-1 0.974 / Top-3 1.000), stress eval
  (Top-1 0.963 / Top-3 1.000) in both modes. A direct DataFrame comparison showed
  0 differing values (only `price` dtype differs: CSV `int64` vs DB `float64`,
  functionally inert).
- **Real API comparison:** performed through the actual local FastAPI endpoint
  `POST /search` (the same path the frontend/chatbot uses), 12 queries × 3 runs
  per mode, Ollama active. DB mode was confirmed to load genuinely from
  PostgreSQL (`Ürünler PostgreSQL'den yüklendi (1000 satır).`), not via fallback.
- **Result:** when `normalized_query` was the same, CSV and DB produced
  **identical** results (12/12 shared normalized queries → byte-identical output).
- The only remaining user-visible differences are caused by **Ollama
  non-determinism** (the normalizer returns different `normalized_query` values
  across repeated runs, even within a single mode) — **not** the DB migration.

**Fail-loud behavior**

- Explicit DB mode (`PRODUCT_SOURCE=db`) now **fails loudly**: if PostgreSQL
  loading fails (bad `DATABASE_URL`, auth error, missing table, missing driver),
  `load_products` raises a `RuntimeError` (chaining the original error) and
  startup stops. It no longer silently falls back to CSV, which previously could
  hide DB misconfiguration. CSV is used only when it is the selected source.
- An automated test (`backend/tests/test_data_loader_db.py`) covers this: it
  mocks the DB loader to fail and asserts `load_products(source="db")` raises and
  never calls the CSV reader. No real PostgreSQL is required for the test.

**Deferred (unchanged from §4)**

- Removing CSV as a product source is the next experiment (branch
  `remove-csv-product-source`); CSV stays in place for now.
- Normalizer output constraint, product_type consolidation, and threshold
  re-tuning remain open.

---

## 9. CSV product source removal — COMPLETED ✅

_Completed: 2026-06-14 (branch `remove-csv-product-source`)_

**PostgreSQL is now the only runtime product source.** `backend/products.csv`
is removed; there is no `PRODUCT_SOURCE` switch and no CSV fallback.

**Runtime model**

- `load_products()` loads only from PostgreSQL (`ORDER BY id`) and returns the
  same DataFrame shape the search pipeline expects. `DATABASE_URL` is required:
  if it is missing or the DB read fails, `load_products()` raises `RuntimeError`
  and startup stops (no silent fallback). Search scoring, chatbot behavior, and
  the frontend are unchanged.

**Source of truth for DB setup**

- `backend/db/seed_products.sql` is now the canonical catalog artifact
  (generated from PostgreSQL with `pg_dump --column-inserts --clean --if-exists`;
  psql-only meta-commands and the `search_path` reset stripped so it is pure SQL
  runnable by both psql and psycopg2). It contains `DROP TABLE IF EXISTS`,
  `CREATE TABLE`, the `PRIMARY KEY`, and 1000 column-based INSERTs with explicit
  ids 1..1000 (preserving the embedding/order contract). It fully recreates the
  table from zero.

**Docker volume persistence (why a committed SQL seed is required)**

- The named volume `aimarket_postgres_data` holds the data and is **not** in Git.
- `docker compose down` (and restarts) **keeps** the data.
- `docker compose down -v` **deletes** the volume → catalog is gone.
- Therefore reproducibility depends on the committed `seed_products.sql`:
  `docker-compose.yml` mounts it into `/docker-entrypoint-initdb.d/`, which
  **auto-runs only on a fresh/empty volume** (first-time init). Existing volumes
  are untouched and must be reseeded manually.

**How to set up / reseed**

- Fresh machine / fresh volume: `docker compose up -d` → catalog auto-seeds.
- Reseed an existing DB (DESTRUCTIVE — drops & recreates `products`):
  `cd backend && python scripts/seed_products_postgres.py`
  (or `psql "$DATABASE_URL" -f backend/db/seed_products.sql`).
- Regenerate the seed after catalog edits:
  `docker exec aimarket-postgres pg_dump -U aimarket_user -d aimarket
  --table=products --no-owner --no-privileges --column-inserts --clean
  --if-exists` (then strip the `\restrict`/`\unrestrict` and `search_path` lines).

**Tests**

- Parser unit tests use a small committed fixture
  (`backend/tests/fixtures/products_sample.csv`, 155 rows) instead of the runtime
  catalog, so tests need neither `products.csv` nor a live DB.
- `test_data_loader_db.py` asserts the DB-only `load_products()` raises on DB
  failure and on missing `DATABASE_URL`.

**Verification (this round)**

- `pytest`: 32 passed (after CSV deletion). Gold eval Top-1 0.974 / Top-3 1.000,
  stress eval Top-1 0.963 / Top-3 1.000 — identical to baseline.
- Real `POST /search` sanity (DB-only backend, 12 queries): behavior matches the
  DB-migration baseline; the only differences are Ollama normalization
  non-determinism (corrected by the original-query fallback, products still
  correct). No CSV file is referenced anywhere at runtime.
- Fresh-volume auto-seed verified in an isolated throwaway container: the init
  script ran `seed_products.sql` and produced 1000 rows (ids 1..1000) from zero,
  without touching the existing volume.
