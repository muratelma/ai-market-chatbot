import pandas as pd


OUTPUT_COLUMNS = [
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


def prepare_dataset(input_path="raw_products.csv", output_path="products_prepared.csv"):
    raw_df = pd.read_csv(input_path)

    prepared_df = pd.DataFrame()

    # Bu kısım büyük dataset'e göre değiştirilecek.
    # Şimdilik örnek kolon isimleri üzerinden çalışıyor.
    prepared_df["product_name"] = raw_df.get("product_name", raw_df.get("name", raw_df.get("title", "")))
    prepared_df["description"] = raw_df.get("description", raw_df.get("product_details", ""))

    prepared_df["main_category"] = raw_df.get("main_category", raw_df.get("category", "Genel"))
    prepared_df["sub_category"] = raw_df.get("sub_category", "")
    prepared_df["target_group"] = raw_df.get("target_group", "Unisex")
    prepared_df["product_type"] = raw_df.get("product_type", "")

    prepared_df["features"] = raw_df.get("features", "")
    prepared_df["tags"] = raw_df.get("tags", "")
    prepared_df["attributes"] = raw_df.get("attributes", "{}")

    prepared_df["price"] = raw_df.get("price", raw_df.get("selling_price", 0))

    # Boş isim/açıklama/fiyat olanları temizle
    prepared_df = prepared_df.dropna(subset=["product_name", "description", "price"])

    # Fiyatı sayıya çevir
    prepared_df["price"] = (
        prepared_df["price"]
        .astype(str)
        .str.replace("₺", "", regex=False)
        .str.replace("TL", "", regex=False)
        .str.replace(",", "", regex=False)
        .str.strip()
    )

    prepared_df["price"] = pd.to_numeric(prepared_df["price"], errors="coerce")
    prepared_df = prepared_df.dropna(subset=["price"])

    # Kolon sırasını sabitle
    prepared_df = prepared_df[OUTPUT_COLUMNS]

    prepared_df.to_csv(output_path, index=False, encoding="utf-8-sig")

    print(f"Dönüştürme tamamlandı: {output_path}")
    print(f"Toplam ürün sayısı: {len(prepared_df)}")


if __name__ == "__main__":
    prepare_dataset()