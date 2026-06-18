import numpy as np
import pandas as pd
import faiss

from query_parser import normalize_text_for_match


def filter_excluded(df, excluded_terms):
    """Drop rows whose main/sub/product category was explicitly rejected.

    ``excluded_terms`` is the set of normalized catalog values produced by
    ``query_parser.extract_excluded_terms`` (e.g. {"mont", "kaban"}).  A row is
    removed when any of its main_category / sub_category / product_type matches
    a rejected term.  As a safety net the original frame is returned unchanged
    if the exclusion would empty the pool — we never want a clear negative
    constraint to leave the user with zero results.
    """
    if not excluded_terms or df.empty:
        return df

    excluded = set(excluded_terms)

    def _keep(row):
        for column in ("main_category", "sub_category", "product_type"):
            if normalize_text_for_match(row.get(column, "")) in excluded:
                return False
        return True

    mask = df.apply(_keep, axis=1)
    kept = df[mask]
    return kept if not kept.empty else df


def create_search_text(df):
    texts = []
    for _, row in df.iterrows():
        # Clean null values
        def clean(val):
            return str(val) if not pd.isna(val) and str(val).lower() != "nan" else ""

        name = clean(row.get("product_name"))
        desc = clean(row.get("description"))
        mc = clean(row.get("main_category"))
        sc = clean(row.get("sub_category"))
        pt = clean(row.get("product_type"))
        tg = clean(row.get("target_group"))
        feat = clean(row.get("features"))
        tags = clean(row.get("tags"))
        attr = clean(row.get("attributes"))

        # Build a richer semantic paragraph
        text = f"Ürün: {name}. "
        if pt:
            text += f"Bu bir {pt} ürünüdür. "
        if mc and sc:
            text += f"Kategori: {mc} > {sc}. "
        elif mc:
            text += f"Kategori: {mc}. "
        
        if tg and tg.lower() != "unisex":
            text += f"Hedef kitle: {tg}. "
            
        if feat:
            text += f"Özellikler: {feat}. "
        if tags:
            text += f"Kullanım alanları ve etiketler: {tags}. "
        if attr:
            text += f"Teknik detaylar: {attr}. "
            
        text += f"Açıklama: {desc}"
        
        # Remove extra spaces
        text = " ".join(text.split())
        texts.append(text)
        
    return texts

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

def apply_filters(df, parsed_query, enforce_explicit_category=False):
    filtered = df.copy()

    # 0. Honor explicit negative constraints ("mont veya kaban değil"): remove
    # rejected categories/types before any other filtering so they cannot
    # resurface via the broad fallback pool below.
    filtered = filter_excluded(filtered, parsed_query.get("excluded_terms"))

    # 1. Price is the ONLY absolute strict filter
    if parsed_query["min_price"] is not None:
        filtered = filtered[filtered["price"] >= parsed_query["min_price"]]

    if parsed_query["max_price"] is not None:
        filtered = filtered[filtered["price"] <= parsed_query["max_price"]]

    base_pool = filtered.copy()

    # 2. Apply strict filters to see if we get a strong candidate pool
    if parsed_query.get("target_group") is not None:
        filtered = filtered[
            filtered["target_group"].astype(str).str.lower() == str(parsed_query["target_group"]).lower()
        ]

    for field in ["main_category", "sub_category"]:
        value = parsed_query.get(field)
        if value is not None:
            temp = filtered[
                filtered[field].astype(str).str.lower() == str(value).lower()
            ]
            if not temp.empty:
                filtered = temp

    # Pool after category (target_group/main/sub) narrowing but before the
    # looser product_type match.
    category_pool = filtered.copy()

    product_type = parsed_query.get("product_type")
    if product_type is not None:
        value_lower = str(product_type).lower()
        product_series = filtered["product_type"].astype(str).str.lower()
        mask = (
            (product_series == value_lower)
            | (product_series.str.contains(value_lower, regex=False, na=False))
            | (product_series.apply(lambda item: item in value_lower))
        )
        temp = filtered[mask]
        if not temp.empty:
            filtered = temp

    # If strict filters produce a strong candidate pool, use it
    if len(filtered) >= 10:
        return filtered

    # When the caller asks us to enforce an explicitly named category (e.g. the
    # query carried a seasonal modifier like "kışlık"/"yazlık" that otherwise
    # lets the broad pool drift to a sibling category — "kışlık elbise" → Mont),
    # stay within the named category instead of diluting with the whole catalog.
    # Prefer the (small) product_type pool when it exists, else the sub/main
    # category pool — but never widen back to the full catalog.
    if enforce_explicit_category:
        if not filtered.empty:
            return filtered
        if not category_pool.empty:
            return category_pool

    # Otherwise, if strict filters produce empty or very small/weak candidates,
    # fall back to the broader candidate pool and let hybrid scoring decide
    return base_pool


def calculate_match_percentage(final_score):
    percentage = final_score * 80
    return int(max(35, min(99, round(percentage))))


def semantic_search(query, candidate_df, model, product_embeddings, parsed_query, top_k=5):
    if candidate_df.empty:
        return candidate_df

    query_vector = model.encode([query])
    query_vector = np.array(query_vector).astype("float32")
    faiss.normalize_L2(query_vector)

    # EMBEDDING ORDER CONTRACT: product_embeddings is a positional array aligned
    # to the original df row order, so candidate_df.index values are valid row
    # positions into it. This holds only because apply_filters preserves the
    # original index (no reset_index) and the df is never reordered after the
    # embeddings are built. See data_loader.load_products / main.py.
    candidate_indices = candidate_df.index.to_numpy()
    candidate_embeddings = product_embeddings[candidate_indices]

    scores = np.dot(candidate_embeddings, query_vector[0])

    top_positions = np.argsort(scores)[::-1]

    result_df = candidate_df.iloc[top_positions].copy()
    result_df["semantic_score"] = scores[top_positions]
    result_df["score"] = 0.0
    result_df["bonus_score"] = 0.0
    result_df["penalty_score"] = 0.0
    result_df["match_percent"] = 0

    for i, row in result_df.iterrows():
        bonus = 0.0
        penalty = 0.0

        combined_text = (
            str(row["description"]) + " " +
            str(row["features"]) + " " +
            str(row["tags"]) + " " +
            str(row["attributes"]) + " " +
            str(row["product_type"]) + " " +
            str(row["sub_category"]) + " " +
            str(row["main_category"])
        ).lower()

        # 1. Product Type Match & Penalty
        if parsed_query.get("product_type") is not None:
            parsed_pt_lower = str(parsed_query["product_type"]).lower()
            row_pt_lower = str(row["product_type"]).lower()
            query_lower = query.lower()
            
            is_exact_parsed = (parsed_pt_lower == row_pt_lower)
            is_explicit = (row_pt_lower in query_lower and len(row_pt_lower) > 3)
            
            if is_explicit:
                explicit_bonus = 0.12 + min(0.08, len(row_pt_lower) * 0.008)
            else:
                explicit_bonus = 0.0
                
            if is_exact_parsed and not is_explicit:
                # Smart parser (e.g. "su gerektirmeyen" -> "Kuru Şampuan")
                bonus += 0.22
            elif is_exact_parsed and is_explicit:
                # Generic parser match (e.g. "mouse" in "oyuncu mouse")
                bonus += max(0.18, explicit_bonus)
            elif is_explicit:
                # Dumb parser, but highly specific explicit match
                bonus += explicit_bonus
            elif parsed_pt_lower in row_pt_lower or row_pt_lower in parsed_pt_lower:
                # Special cases (e.g. Kuru Şampuan vs Şampuan)
                if parsed_pt_lower == "şampuan" and "kuru şampuan" in row_pt_lower and "kuru" not in query_lower and "susuz" not in query_lower and "su gerektir" not in query_lower:
                    penalty += 0.15
                else:
                    row_words = set(row_pt_lower.split())
                    query_words = set(query_lower.split())
                    if len(row_words.intersection(query_words)) > 1:
                        bonus += 0.08
                    else:
                        bonus += 0.05
            else:
                penalty += 0.15

        # 2. Main Category Match & Penalty
        if parsed_query.get("main_category") is not None:
            if str(parsed_query["main_category"]).lower() == str(row["main_category"]).lower():
                bonus += 0.04
            else:
                penalty += 0.10

        # 3. Sub Category Match
        if parsed_query.get("sub_category") is not None:
            if str(parsed_query["sub_category"]).lower() == str(row["sub_category"]).lower():
                bonus += 0.05

        # 4. Target Group Match & Penalty
        if parsed_query.get("target_group") is not None:
            parsed_tg_lower = str(parsed_query["target_group"]).lower()
            row_tg_lower = str(row["target_group"]).lower()
            
            if parsed_tg_lower == row_tg_lower:
                bonus += 0.08
            elif row_tg_lower != "nan" and row_tg_lower != "unisex" and parsed_tg_lower != "unisex":
                # Opposite gender (e.g. Kadın vs Erkek)
                penalty += 0.30
                
        # 5. Taxonomy Match Bonus
        if parsed_query.get("taxonomy_match") is not None:
            tax_field = parsed_query["taxonomy_match"]["field"]
            tax_val = str(parsed_query["taxonomy_match"]["value"]).lower()
            if tax_field in row and str(row[tax_field]).lower() == tax_val:
                bonus += 0.06

        # 6. Feature / Tag / Attribute Bonus
        for feature in parsed_query.get("features", []):
            if feature.lower() in combined_text:
                bonus += 0.10

        # 7. Context Bonus
        for context in parsed_query.get("contexts", []):
            if context.lower() in combined_text:
                bonus += 0.03

        final_score = row["semantic_score"] + bonus - penalty
        
        result_df.at[i, "score"] = final_score
        result_df.at[i, "bonus_score"] = bonus
        result_df.at[i, "penalty_score"] = penalty
        result_df.at[i, "match_percent"] = calculate_match_percentage(final_score)

    result_df = result_df.sort_values(
        by=["score", "match_percent"],
        ascending=False
    )

    # 8. Smart Threshold for Nonsense Queries
    # If the query has no strong categories/product types AND the top semantic score is very low,
    # it's likely a nonsense query (e.g. "uzay mekiği")
    if not result_df.empty:
        has_hard_filter = (
            parsed_query.get("main_category") is not None or
            parsed_query.get("sub_category") is not None or
            parsed_query.get("product_type") is not None or
            parsed_query.get("taxonomy_match") is not None
        )
        max_score = result_df["score"].max()
        if not has_hard_filter and max_score < 0.40:
            return pd.DataFrame(columns=result_df.columns)

    result_df = result_df.head(top_k).reset_index(drop=True)

    return result_df


def diversify_results(result_df, top_k=5):
    """
    Rerank search results to maximize product_type diversity.

    Uses a round-robin strategy: iterate through unique product_types
    (ordered by their best score) and pick one product per type until
    top_k is reached.  This ensures the user sees a representative
    sample across product types for broad queries.

    Parameters
    ----------
    result_df : pd.DataFrame
        Scored search results (output of ``semantic_search``).
        Must contain ``product_type`` and ``score`` columns.
    top_k : int
        Maximum number of results to return.

    Returns
    -------
    pd.DataFrame
        Reranked DataFrame with at most ``top_k`` rows.
    """
    if result_df.empty or len(result_df) <= 1:
        return result_df

    # Group by product_type, keeping original score order within each group
    groups = {}
    for idx, row in result_df.iterrows():
        pt = str(row.get("product_type", "")).strip()
        if pt not in groups:
            groups[pt] = []
        groups[pt].append(idx)

    # Order groups by their best (first) product's score — highest first
    sorted_types = sorted(
        groups.keys(),
        key=lambda pt: result_df.loc[groups[pt][0], "score"],
        reverse=True,
    )

    # Round-robin pick
    selected_indices = []
    round_num = 0

    while len(selected_indices) < top_k:
        added_this_round = False

        for pt in sorted_types:
            if len(selected_indices) >= top_k:
                break

            items = groups[pt]
            if round_num < len(items):
                selected_indices.append(items[round_num])
                added_this_round = True

        if not added_this_round:
            break

        round_num += 1

    diversified_df = result_df.loc[selected_indices].reset_index(drop=True)

    return diversified_df


def build_answer(parsed_query, product_count):
    if product_count == 0:
        has_hard_filter = (
            parsed_query.get("main_category") is not None or
            parsed_query.get("sub_category") is not None or
            parsed_query.get("product_type") is not None or
            parsed_query.get("taxonomy_match") is not None or
            parsed_query.get("min_price") is not None or
            parsed_query.get("max_price") is not None
        )
        if not has_hard_filter:
            return "Maalesef ne aradığınızı tam olarak anlayamadım veya stoklarımızda bu tip bir ürün bulunmuyor. Lütfen farklı kelimelerle tekrar deneyin."
        return "Aradığınız kriterlere uygun ürün bulunamadı. Fiyat aralığını veya filtreleri genişletebilirsiniz."

    # Build a context-aware chatbot response
    parts = []

    product_type = parsed_query.get("product_type")
    main_category = parsed_query.get("main_category")
    target_group = parsed_query.get("target_group")
    min_price = parsed_query.get("min_price")
    max_price = parsed_query.get("max_price")

    # Describe what we found.  Plain text only — no Markdown emphasis (`**`):
    # the chatbot renders these strings verbatim, so raw markers would leak
    # into the UI as literal asterisks.
    if product_type:
        parts.append(f"{product_type} kategorisinde")
    elif main_category:
        parts.append(f"{main_category} bölümünde")

    if target_group:
        parts.append(f"{target_group} için")

    if min_price is not None and max_price is not None:
        parts.append(f"₺{min_price} - ₺{max_price} fiyat aralığında")
    elif max_price is not None:
        parts.append(f"₺{max_price} altında")
    elif min_price is not None:
        parts.append(f"₺{min_price} üzeri")

    if parts:
        context = " ".join(parts)
        return f"{context} size en uygun {product_count} ürün listelendi. 🛍️"

    return f"Sorgunuza göre en uygun {product_count} ürünü listeledim. 🛍️"