"""Seed / reseed the PostgreSQL ``products`` table from the SQL seed file.

Run from the backend directory:

    python scripts/seed_products_postgres.py

Connection comes from the DATABASE_URL env var (falls back to the local
docker-compose default in config.py).

This applies ``backend/db/seed_products.sql``, which is the source of truth for
the product catalog (generated from PostgreSQL with pg_dump). The seed file is
self-contained and DESTRUCTIVE by design: it runs ``DROP TABLE IF EXISTS
products`` then recreates and repopulates the table, so re-running it resets the
catalog to the committed snapshot. Rows keep explicit ids 1..N so the app's
``ORDER BY id`` load preserves the embedding/order contract.

Note: a fresh Docker volume auto-applies this same file via
``/docker-entrypoint-initdb.d`` (see docker-compose.yml); this script is for
reseeding an existing database.
"""

import sys
from pathlib import Path

import psycopg2

# Make backend modules importable when run as a standalone script.
BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from config import DATABASE_URL, PRODUCTS_TABLE  # noqa: E402

SEED_SQL_PATH = BACKEND_DIR / "db" / "seed_products.sql"


def main() -> None:
    if not DATABASE_URL:
        raise SystemExit("DATABASE_URL ayarlı değil; seed uygulanamıyor.")
    if not SEED_SQL_PATH.exists():
        raise SystemExit(f"Seed dosyası bulunamadı: {SEED_SQL_PATH}")

    sql = SEED_SQL_PATH.read_text(encoding="utf-8")

    print(f"Seed uygulanıyor: {SEED_SQL_PATH}")
    print("UYARI: bu işlem 'products' tablosunu DROP edip yeniden oluşturur.")

    conn = psycopg2.connect(DATABASE_URL)
    try:
        conn.autocommit = True
        with conn.cursor() as cur:
            # The seed file is pure SQL (no psql meta-commands); psycopg2 can
            # execute the whole multi-statement script in one call.
            cur.execute(sql)
            cur.execute(f"SELECT count(*) FROM {PRODUCTS_TABLE}")
            count = cur.fetchone()[0]
    finally:
        conn.close()

    print(f"Seed tamam: '{PRODUCTS_TABLE}' tablosunda {count} ürün var.")


if __name__ == "__main__":
    main()
