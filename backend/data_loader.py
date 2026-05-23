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
    "price",
]


REQUIRED_TAXONOMY_COLUMNS = [
    "field",
    "value",
    "text",
]


def load_products(csv_path="products.csv"):
    df = pd.read_csv(csv_path)

    for col in REQUIRED_PRODUCT_COLUMNS:
        if col not in df.columns:
            raise ValueError(f"products.csv içinde eksik sütun var: {col}")

    df["price"] = pd.to_numeric(df["price"], errors="coerce")
    df = df.dropna(
        subset=["product_name", "description", "price"]
    ).reset_index(drop=True)

    return df


def load_taxonomy(csv_path="taxonomy.csv"):
    taxonomy_df = pd.read_csv(csv_path)

    for col in REQUIRED_TAXONOMY_COLUMNS:
        if col not in taxonomy_df.columns:
            raise ValueError(f"taxonomy.csv içinde eksik sütun var: {col}")

    taxonomy_df = taxonomy_df.dropna(
        subset=REQUIRED_TAXONOMY_COLUMNS
    ).reset_index(drop=True)

    return taxonomy_df.to_dict("records")