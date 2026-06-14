import logging

import pandas as pd

from config import PRODUCT_SOURCE

logger = logging.getLogger(__name__)


REQUIRED_PRODUCT_COLUMNS = [
    "product_name",
    "description",
    "main_category",
    "sub_category",
    "target_group",
    "product_type",
    "features",
    "tags",
    "attributes",
    "price",
]


REQUIRED_TAXONOMY_COLUMNS = [
    "field",
    "value",
    "text",
]


def _read_products_csv(csv_path):
    # encoding="utf-8-sig" strips a UTF-8 BOM if the CSV is ever re-exported
    # (e.g. from Excel). Without it, the first column header can become
    # "﻿product_name" and silently fail the required-column check below.
    return pd.read_csv(csv_path, encoding="utf-8-sig")


def _finalize_products(df):
    """Shared post-processing applied to BOTH csv and db sources so the two
    modes return an identical DataFrame shape, columns, and (positional) index.

    Keeping this single function is what guarantees DB mode matches CSV mode:
    same required-column check, same price coercion, same dropna, same
    reset_index. Do not branch the logic per-source here."""
    for col in REQUIRED_PRODUCT_COLUMNS:
        if col not in df.columns:
            raise ValueError(f"ürün verisinde eksik sütun var: {col}")

    df["price"] = pd.to_numeric(df["price"], errors="coerce")
    # ---- EMBEDDING ORDER CONTRACT ----
    # reset_index(drop=True) gives every product a stable 0..N-1 positional
    # index. product_embeddings (built in main.py from this exact df order) is
    # a positional array, and search_engine.semantic_search looks vectors up by
    # df index. The df row order MUST stay identical to the order the
    # embeddings were built from, or search silently returns wrong products.
    # In DB mode the upstream ORDER BY id (see database.load_products_from_db)
    # establishes that stable order before this reset_index pins it as 0..N-1,
    # and embeddings are rebuilt from this exact order at startup.
    df = df.dropna(
        subset=["product_name", "description", "price"]
    ).reset_index(drop=True)

    return df


def load_products(csv_path="products.csv", source=None):
    """Load the product catalog into a pandas DataFrame.

    ``source`` selects the backing store and defaults to ``config.PRODUCT_SOURCE``
    (``"csv"`` unless overridden by the PRODUCT_SOURCE env var):
      * ``"csv"`` -> read ``csv_path`` (unchanged legacy behavior, the default).
      * ``"db"``  -> read PostgreSQL via ``database.load_products_from_db``
                     (ORDER BY id).

    Explicit DB mode FAILS LOUDLY: when ``PRODUCT_SOURCE=db`` and the DB read
    fails (bad DATABASE_URL, auth error, missing table, psycopg2 not installed),
    the error is re-raised so startup stops instead of silently serving stale
    CSV data. Silently falling back would hide DB misconfiguration and
    invalidate DB-mode tests. CSV is only ever used when it is the selected
    (default/explicit) source, never as a hidden DB rescue.

    Both paths go through ``_finalize_products`` so the returned DataFrame has
    the same columns, data shape, and 0..N-1 positional index in either mode.
    """
    source = (source or PRODUCT_SOURCE or "csv").lower()

    if source == "db":
        try:
            # Imported lazily so CSV mode (and importers that never touch the
            # DB) don't require psycopg2 to be installed, and to avoid an
            # import cycle (database.py imports REQUIRED_PRODUCT_COLUMNS here).
            from database import load_products_from_db

            df = load_products_from_db()
            logger.info("Ürünler PostgreSQL'den yüklendi (%d satır).", len(df))
        except Exception as exc:
            # Explicit DB mode: do NOT fall back to CSV. Surface the failure so
            # the operator fixes the DB config instead of unknowingly running
            # on CSV.
            logger.error(
                "PRODUCT_SOURCE=db ama PostgreSQL'den ürün yüklenemedi: %s", exc
            )
            raise RuntimeError(
                "PRODUCT_SOURCE=db iken ürünler PostgreSQL'den yüklenemedi. "
                "DATABASE_URL ve veritabanı bağlantısını kontrol edin. "
                "(CSV'ye otomatik geri dönüş yapılmaz.)"
            ) from exc
    else:
        df = _read_products_csv(csv_path)

    return _finalize_products(df)


def load_taxonomy(csv_path="taxonomy.csv"):
    # See load_products: utf-8-sig guards against a BOM on re-export.
    taxonomy_df = pd.read_csv(csv_path, encoding="utf-8-sig")

    for col in REQUIRED_TAXONOMY_COLUMNS:
        if col not in taxonomy_df.columns:
            raise ValueError(f"taxonomy.csv içinde eksik sütun var: {col}")

    taxonomy_df = taxonomy_df.dropna(
        subset=REQUIRED_TAXONOMY_COLUMNS
    ).reset_index(drop=True)

    return taxonomy_df.to_dict("records")