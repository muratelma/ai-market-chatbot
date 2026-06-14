import logging

import pandas as pd

from config import DATABASE_URL

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


def _finalize_products(df):
    """Post-processing applied to the DB-loaded catalog: required-column check,
    price coercion, dropna, and reset_index. This establishes the stable
    DataFrame shape and positional index the search pipeline expects."""
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
    # The upstream ORDER BY id (see database.load_products_from_db) establishes
    # the stable order before this reset_index pins it as 0..N-1, and embeddings
    # are rebuilt from this exact order at startup.
    df = df.dropna(
        subset=["product_name", "description", "price"]
    ).reset_index(drop=True)

    return df


def load_products():
    """Load the product catalog from PostgreSQL into a pandas DataFrame.

    PostgreSQL is the ONLY product source. There is no CSV path and no silent
    fallback: if ``DATABASE_URL`` is missing, or the DB read fails (auth error,
    missing table, driver missing, ...), this raises ``RuntimeError`` so startup
    stops loudly instead of serving an incomplete/incorrect catalog.

    Rows are loaded with ``ORDER BY id`` and finalized by ``_finalize_products``
    to produce the stable DataFrame shape and 0..N-1 positional index the search
    pipeline expects (the embedding/order contract).
    """
    if not DATABASE_URL:
        raise RuntimeError(
            "DATABASE_URL ayarlı değil. Ürünler PostgreSQL'den yüklenir; "
            "lütfen DATABASE_URL ortam değişkenini ayarlayın."
        )

    try:
        # Imported lazily to avoid an import cycle (database.py imports
        # REQUIRED_PRODUCT_COLUMNS from this module).
        from database import load_products_from_db

        df = load_products_from_db()
        logger.info("Ürünler PostgreSQL'den yüklendi (%d satır).", len(df))
    except Exception as exc:
        logger.error("PostgreSQL'den ürün yüklenemedi: %s", exc)
        raise RuntimeError(
            "Ürünler PostgreSQL'den yüklenemedi. DATABASE_URL ve veritabanı "
            "bağlantısını kontrol edin. (CSV'ye geri dönüş yoktur.)"
        ) from exc

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