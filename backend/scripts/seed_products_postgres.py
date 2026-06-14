"""Seed the PostgreSQL ``products`` table from backend/products.csv.

Run from the backend directory:

    python scripts/seed_products_postgres.py

Connection comes from the DATABASE_URL env var (falls back to the local
docker-compose default in config.py). The script is safely re-runnable: it
TRUNCATEs and reloads the table on every run inside a single transaction.

-------------------------------------------------------------------------------
ORDER CONTRACT (must match data_loader / database / main)
-------------------------------------------------------------------------------
Rows are inserted in CSV order and assigned a stable integer ``id`` = CSV row
position (1..N). The app later loads ``SELECT ... ORDER BY id``, which exactly
reproduces CSV order, so the embeddings stay aligned to the DataFrame rows.
The id is assigned explicitly here (not via SERIAL) so the order does not
depend on insertion timing.
"""

import sys
from pathlib import Path

import pandas as pd
import psycopg2
from psycopg2.extras import execute_values

# Make backend modules importable when run as a standalone script.
BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from config import DATABASE_URL, PRODUCTS_TABLE  # noqa: E402
from data_loader import REQUIRED_PRODUCT_COLUMNS  # noqa: E402

CSV_PATH = BACKEND_DIR / "products.csv"


def _create_table_sql(table: str) -> str:
    # Preserve every CSV column; add a stable integer primary key.
    # Text columns are TEXT to keep the exact original strings (incl. the
    # JSON-ish ``attributes`` column). price is NUMERIC to allow decimals.
    return f"""
        CREATE TABLE IF NOT EXISTS {table} (
            id            INTEGER PRIMARY KEY,
            product_name  TEXT NOT NULL,
            description   TEXT,
            main_category TEXT,
            sub_category  TEXT,
            target_group  TEXT,
            product_type  TEXT,
            features      TEXT,
            tags          TEXT,
            attributes    TEXT,
            price         NUMERIC
        )
    """


def main() -> None:
    # encoding="utf-8-sig" strips a possible UTF-8 BOM (matches data_loader).
    df = pd.read_csv(CSV_PATH, encoding="utf-8-sig")

    missing = [c for c in REQUIRED_PRODUCT_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(f"products.csv içinde eksik sütun var: {missing}")

    # Keep CSV column order; convert NaN -> None so NULLs land in PostgreSQL.
    df = df[REQUIRED_PRODUCT_COLUMNS].where(pd.notna(df), None)

    insert_columns = ["id"] + REQUIRED_PRODUCT_COLUMNS
    # id = CSV row position (1-based) -> stable ORDER BY id reproduces CSV order.
    rows = [
        (i + 1, *(record[col] for col in REQUIRED_PRODUCT_COLUMNS))
        for i, record in enumerate(df.to_dict("records"))
    ]

    column_sql = ", ".join(insert_columns)
    insert_sql = f"INSERT INTO {PRODUCTS_TABLE} ({column_sql}) VALUES %s"

    conn = psycopg2.connect(DATABASE_URL)
    try:
        with conn:  # transaction: commit on success, rollback on error
            with conn.cursor() as cur:
                cur.execute(_create_table_sql(PRODUCTS_TABLE))
                # Re-runnable: wipe and reload so re-seeding never duplicates.
                cur.execute(f"TRUNCATE TABLE {PRODUCTS_TABLE}")
                execute_values(cur, insert_sql, rows)
    finally:
        conn.close()

    print(
        f"Seed tamam: {len(rows)} ürün '{PRODUCTS_TABLE}' tablosuna yüklendi "
        f"(id 1..{len(rows)}, CSV sırasına göre)."
    )


if __name__ == "__main__":
    main()
