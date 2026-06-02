import numpy as np
import faiss


def create_search_text(df):
    return (
        df["product_name"].astype(str) + " | " +
        df["description"].astype(str) + " | " +
        df["main_category"].astype(str) + " | " +
        df["sub_category"].astype(str) + " | " +
        df["target_group"].astype(str) + " | " +
        df["product_type"].astype(str) + " | " +
        df["features"].astype(str) + " | " +
        df["tags"].astype(str) + " | " +
        df["attributes"].astype(str)
    ).tolist()

def row_contains_any_feature(row, features):
    combined_text = (
        str(row.get("product_name", "")) + " " +
        str(row.get("description", "")) + " " +
        str(row.get("features", "")) + " " +
        str(row.get("tags", "")) + " " +
        str(row.get("attributes", "")) + " " +
        str(row.get("product_type", "")) + " " +
        str(row.get("sub_category", "")) + " " +
        str(row.get("main_category", ""))
    ).lower()

    return any(str(feature).lower() in combined_text for feature in features)

def apply_filters(df, parsed_query):
    filtered = df.copy()

    # 1. Price and target_group are strict constraints
    if parsed_query["min_price"] is not None:
        filtered = filtered[filtered["price"] >= parsed_query["min_price"]]

    if parsed_query["max_price"] is not None:
        filtered = filtered[filtered["price"] <= parsed_query["max_price"]]

    if parsed_query.get("target_group") is not None:
        filtered = filtered[
            filtered["target_group"].astype(str).str.lower() == str(parsed_query["target_group"]).lower()
        ]

    # Keep a copy of strictly filtered candidates (preserving target_group) to fallback on
    strict_filtered = filtered.copy()

    # 2. Main category and sub category filters (soft: fallback if empty)
    for field in ["main_category", "sub_category"]:
        value = parsed_query.get(field)
        if value is not None:
            temp = filtered[
                filtered[field].astype(str).str.lower() == str(value).lower()
            ]
            if not temp.empty:
                filtered = temp

    # 3. Product type filter (strict: can make it empty)
    product_type = parsed_query.get("product_type")
    if product_type is not None:
        value_lower = str(product_type).lower()
        product_series = filtered["product_type"].astype(str).str.lower()
        mask = (
            (product_series == value_lower)
            | (product_series.str.contains(value_lower, regex=False, na=False))
            | (product_series.apply(lambda item: item in value_lower))
        )
        filtered = filtered[mask]

    # If category filter made it empty, fallback to target_group filtered dataframe
    # only if we don't have a product_type filter constraint (since product_type mismatch should remain empty)
    if filtered.empty and parsed_query.get("product_type") is None:
        filtered = strict_filtered

    # Apply feature filter only when the candidate pool is large enough
    FEATURE_FILTER_MIN_POOL = 10
    features = parsed_query.get("features", [])

    if features and not filtered.empty and len(filtered) > FEATURE_FILTER_MIN_POOL:
        feature_mask = []
        for _, row in filtered.iterrows():
            feature_mask.append(row_contains_any_feature(row, features))
        feature_filtered = filtered.loc[feature_mask]
        if not feature_filtered.empty:
            filtered = feature_filtered

    return filtered

  


def calculate_match_percentage(semantic_score, bonus_score):
    normalized = (semantic_score - 0.20) / 0.45
    normalized = max(0, min(1, normalized))

    percentage = 50 + (normalized * 32)
    percentage += min(bonus_score * 170, 16)

    return int(max(35, min(96, round(percentage))))


def semantic_search(query, candidate_df, model, product_embeddings, parsed_query, top_k=5):
    if candidate_df.empty:
        return candidate_df

    query_vector = model.encode([query])
    query_vector = np.array(query_vector).astype("float32")
    faiss.normalize_L2(query_vector)

    candidate_indices = candidate_df.index.to_numpy()
    candidate_embeddings = product_embeddings[candidate_indices]

    scores = np.dot(candidate_embeddings, query_vector[0])

    top_count = min(max(top_k * 3, top_k), len(candidate_df))
    top_positions = np.argsort(scores)[::-1][:top_count]

    result_df = candidate_df.iloc[top_positions].copy()
    result_df["semantic_score"] = scores[top_positions]
    result_df["score"] = scores[top_positions]
    result_df["bonus_score"] = 0.0
    result_df["match_percent"] = 0

    for i, row in result_df.iterrows():
        bonus = 0

        combined_text = (
            str(row["description"]) + " " +
            str(row["features"]) + " " +
            str(row["tags"]) + " " +
            str(row["attributes"]) + " " +
            str(row["product_type"]) + " " +
            str(row["sub_category"]) + " " +
            str(row["main_category"])
        ).lower()

        for feature in parsed_query["features"]:
            if feature.lower() in combined_text:
                bonus += 0.04

        for context in parsed_query["contexts"]:
            if context.lower() in combined_text:
                bonus += 0.025

        # Exact product_type match: strongest ranking signal — rewards products
        # whose type precisely matches what the query asked for (e.g. "Kamp Ocağı"
        # should outrank "Kamp Tabak Seti" even if both are semantically similar).
        if parsed_query["product_type"] is not None:
            parsed_pt_lower = str(parsed_query["product_type"]).lower()
            row_pt_lower = str(row["product_type"]).lower()
            if parsed_pt_lower == row_pt_lower:
                bonus += 0.10  # Exact match — strong boost
            elif parsed_pt_lower in row_pt_lower or row_pt_lower in parsed_pt_lower:
                # Special case: "şampuan" query should not match "kuru şampuan" unless "kuru" is in the query.
                if parsed_pt_lower == "şampuan" and "kuru şampuan" in row_pt_lower and "kuru" not in query.lower():
                    pass
                else:
                    bonus += 0.03  # Partial / superset match — moderate boost

        if parsed_query["main_category"] is not None:
            if str(parsed_query["main_category"]).lower() == str(row["main_category"]).lower():
                bonus += 0.06

        if parsed_query["sub_category"] is not None:
            if str(parsed_query["sub_category"]).lower() == str(row["sub_category"]).lower():
                bonus += 0.08

        if parsed_query["target_group"] is not None:
            if str(parsed_query["target_group"]).lower() == str(row["target_group"]).lower():
                bonus += 0.05

        final_score = min(row["semantic_score"] + bonus, 0.95)

        result_df.at[i, "score"] = final_score
        result_df.at[i, "bonus_score"] = bonus
        result_df.at[i, "match_percent"] = calculate_match_percentage(
            row["semantic_score"],
            bonus
        )

    result_df = result_df.sort_values(
        by=["match_percent", "bonus_score", "score"],
        ascending=False
    )

    result_df = result_df.head(top_k).reset_index(drop=True)

    return result_df


def build_answer(parsed_query, product_count):
    if product_count == 0:
        return "Aradığınız kriterlere uygun ürün bulunamadı. Fiyat aralığını veya filtreleri genişletebilirsiniz."

    has_filter = any([
        parsed_query["min_price"] is not None,
        parsed_query["max_price"] is not None,
        parsed_query["main_category"] is not None,
        parsed_query["sub_category"] is not None,
        parsed_query["target_group"] is not None,
        parsed_query["product_type"] is not None,
        len(parsed_query["features"]) > 0,
        len(parsed_query["contexts"]) > 0,
    ])

    if has_filter:
        return "Arama kriterlerinize en yakın ürünler listelendi."

    return "Sorgunuza göre en uygun ürünleri listeledim."