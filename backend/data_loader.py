import pandas as pd


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


def load_products(csv_path="products.csv"):
    # encoding="utf-8-sig" strips a UTF-8 BOM if the CSV is ever re-exported
    # (e.g. from Excel). Without it, the first column header can become
    # "﻿product_name" and silently fail the required-column check below.
    df = pd.read_csv(csv_path, encoding="utf-8-sig")

    for col in REQUIRED_PRODUCT_COLUMNS:
        if col not in df.columns:
            raise ValueError(f"products.csv içinde eksik sütun var: {col}")

    df["price"] = pd.to_numeric(df["price"], errors="coerce")
    # ---- EMBEDDING ORDER CONTRACT ----
    # reset_index(drop=True) gives every product a stable 0..N-1 positional
    # index. product_embeddings (built in main.py from this exact df order) is
    # a positional array, and search_engine.semantic_search looks vectors up by
    # df index. The df row order MUST stay identical to the order the
    # embeddings were built from, or search silently returns wrong products.
    # DB migration must load products in a stable order (preferably ORDER BY id)
    # and rebuild embeddings from that same order.
    df = df.dropna(
        subset=["product_name", "description", "price"]
    ).reset_index(drop=True)

    return df


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