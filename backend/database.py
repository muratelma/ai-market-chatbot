"""PostgreSQL access for the product catalog.

This module is intentionally small: the rest of the system still loads the
ENTIRE catalog once at startup into an in-memory pandas DataFrame and never
does per-request SQL. The only job here is to hand ``data_loader`` a DataFrame
that is shape-for-shape identical to the one produced from ``products.csv``.

-------------------------------------------------------------------------------
DB / DataFrame / embedding ORDER CONTRACT  (read before changing anything)
-------------------------------------------------------------------------------
``product_embeddings`` (built in main.py and eval/run_eval.py) is a *positional*
array: ``product_embeddings[i]`` belongs to DataFrame row ``i``, and
``search_engine.semantic_search`` looks vectors up by DataFrame index. The
DataFrame row order MUST therefore be deterministic and identical to the order
the embeddings were built from, or search silently returns the wrong products.

To guarantee this in DB mode:
  * the catalog is loaded with a stable ``ORDER BY id`` (the integer primary key
    the seed script assigns in CSV order), and
  * embeddings are always rebuilt from that exact loaded order at startup.

The query selects ONLY the original CSV columns (no ``id`` column) in the CSV
column order, so the resulting DataFrame matches CSV mode column-for-column.
``data_loader.load_products`` then applies the same finalize step (price coerce,
dropna, reset_index) to both sources, producing the same 0..N-1 positional index.
"""

import logging

import pandas as pd
import psycopg2

from config import DATABASE_URL, PRODUCTS_TABLE
from data_loader import REQUIRED_PRODUCT_COLUMNS

logger = logging.getLogger(__name__)


def get_connection(database_url: str | None = None):
    """Open a psycopg2 connection from a libpq URI (DATABASE_URL by default)."""
    return psycopg2.connect(database_url or DATABASE_URL)


def load_products_from_db(database_url: str | None = None, table: str | None = None):
    """Load the full product catalog from PostgreSQL into a DataFrame.

    Returns a *raw* DataFrame containing exactly ``REQUIRED_PRODUCT_COLUMNS``
    (in CSV order, no ``id`` column) ordered by the integer primary key. The
    shared finalize step in ``data_loader.load_products`` then makes the shape
    identical to CSV mode. See the ORDER CONTRACT note at the top of this file.
    """
    table = table or PRODUCTS_TABLE
    columns = list(REQUIRED_PRODUCT_COLUMNS)
    column_sql = ", ".join(columns)

    # ORDER BY id is REQUIRED, not cosmetic: it pins the row order the
    # embeddings are aligned to. Do not remove it.
    query = f"SELECT {column_sql} FROM {table} ORDER BY id"

    conn = get_connection(database_url)
    try:
        with conn.cursor() as cur:
            cur.execute(query)
            rows = cur.fetchall()
    finally:
        conn.close()

    return pd.DataFrame(rows, columns=columns)
