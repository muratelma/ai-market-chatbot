import re
import numpy as np
import faiss


TAXONOMY_MATCH_THRESHOLD = 0.45


FEATURE_SYNONYMS = {
    "yağmur": ["su geçirmez", "yağmurlu hava", "suya dayanıklı"],
    "yağmurlu": ["su geçirmez", "yağmurlu hava", "suya dayanıklı"],
    "su geçirmez": ["su geçirmez", "suya dayanıklı"],
    "gece": ["aydınlatma", "ışık", "güçlü ışık"],
    "ışık": ["aydınlatma", "ışık"],
    "ucuz": ["uygun fiyatlı"],
    "uygun fiyatlı": ["uygun fiyatlı"],
    "soğuk": ["sıcak", "kışlık"],
    "kış": ["sıcak", "kışlık"],
    "spor": ["spor", "rahat"],
    "rahat": ["rahat"],
    "yürüyüş": ["yürüyüş", "outdoor", "rahat"],
    "uyku": ["uyku", "tulum", "mat", "sıcak"],
    "yemek": ["pişirme", "ocak"],
    "pişirme": ["pişirme", "ocak"],
    "pisirme": ["pişirme", "ocak"],
    "pişir": ["pişirme", "ocak"],
    "pisir": ["pişirme", "ocak"],
    "ocak": ["pişirme", "ocak"],
}


CONTEXT_KEYWORDS = [
    "kamp",
    "ofis",
    "okul",
    "spor",
    "günlük",
    "gunluk",
    "yağmur",
    "yagmur",
    "yağmurlu",
    "yagmurlu",
    "gece",
    "yürüyüş",
    "yuruyus",
    "outdoor",
    "dış mekan",
    "dis mekan",
]


def extract_price_range(query):
    q = query.lower()
    q = q.replace("₺", " tl ")
    q = q.replace(".", "")
    q = q.replace(",", "")

    min_price = None
    max_price = None

    range_match = re.search(
        r"(\d+)\s*(?:tl|lira)?\s*(?:ile|-|arası|arasi)\s*(\d+)\s*(?:tl|lira)?",
        q
    )

    if not range_match:
        range_match = re.search(
            r"(\d+)\s*(?:tl|lira)?\s*(?:den|dan|ten|tan)\s*(\d+)\s*(?:tl|lira)?\s*(?:e|a|ye|ya)?\s*(?:kadar|arası|arasi)",
            q
        )

    if range_match:
        min_price = int(range_match.group(1))
        max_price = int(range_match.group(2))
        if min_price > max_price:
            min_price, max_price = max_price, min_price
        return min_price, max_price

    min_patterns = [
        r"(\d+)\s*(?:tl|lira)?\s*(?:üstü|ustu|üstünde|ustunde|üzeri|uzeri|üzerinde|uzerinde|fazla|yüksek|yuksek)",
        r"(\d+)\s*(?:tl|lira)?\s*(?:den|dan|ten|tan)\s*(?:fazla|yüksek|yuksek)",
        r"(?:en az|min|minimum|alt limit)\s*(\d+)",
    ]

    for pattern in min_patterns:
        match = re.search(pattern, q)
        if match:
            min_price = int(match.group(1))
            return min_price, max_price

    max_patterns = [
        r"(\d+)\s*(?:tl|lira)?\s*(?:altı|alti|altında|altinda|aşağı|asagi|düşük|dusuk)",
        r"(\d+)\s*(?:tl|lira)?\s*(?:den|dan|ten|tan)\s*(?:az|düşük|dusuk|ucuz)",
        r"(?:en fazla|max|maksimum|üst limit|ust limit)\s*(\d+)",
        r"(\d+)\s*(?:tl|lira)?\s*(?:geçmesin|gecmesin)",
    ]

    for pattern in max_patterns:
        match = re.search(pattern, q)
        if match:
            max_price = int(match.group(1))
            return min_price, max_price

    single_match = re.search(r"(\d+)\s*(?:tl|lira)", q)
    if single_match:
        max_price = int(single_match.group(1))

    return min_price, max_price


def find_value_from_column(query, df, column_name):
    q = query.lower()
    values = df[column_name].dropna().unique().tolist()

    for value in values:
        value_text = str(value).lower()
        if value_text and value_text in q:
            return value

    return None


def extract_features(query):
    q = query.lower()
    found_features = []

    for keyword, mapped_features in FEATURE_SYNONYMS.items():
        if keyword in q:
            found_features.extend(mapped_features)

    return list(set(found_features))


def extract_contexts(query):
    q = query.lower()
    contexts = []

    for word in CONTEXT_KEYWORDS:
        if word in q:
            contexts.append(word)

    return list(set(contexts))


def clean_query_for_taxonomy(query):
    q = query.lower()

    q = re.sub(
        r"\d+\s*(?:tl|lira)?\s*(?:den|dan|ten|tan|e|a|ye|ya)?",
        " ",
        q
    )

    remove_words = [
        "kadın", "kadin", "erkek", "unisex", "çocuk", "cocuk",
        "tl", "lira",
        "altında", "altinda", "altı", "alti",
        "üstünde", "ustunde", "üstü", "ustu", "üzeri", "uzeri",
        "arası", "arasi", "ile", "kadar",
        "den", "dan", "ten", "tan", "e", "a", "ye", "ya",
        "için", "icin", "lazım", "lazim",
        "arıyorum", "ariyorum", "istiyorum",
        "ürün", "urun", "şey", "sey", "bir"
    ]

    for word in remove_words:
        q = re.sub(rf"\b{word}\b", " ", q)

    q = re.sub(r"\s+", " ", q).strip()
    return q


def extract_explicit_main_category(query, df):
    q = query.lower()

    ambiguous_categories = ["kamp", "spor"]
    values = df["main_category"].dropna().unique().tolist()

    for value in values:
        value_lower = str(value).lower()

        if value_lower in ambiguous_categories:
            continue

        if value_lower in q:
            return value

        if value_lower == "ayakkabı" and "ayakkabi" in q:
            return value

    return None


def remaining_query_after_category(query, main_category):
    q = clean_query_for_taxonomy(query)

    if main_category is None:
        return q

    category_terms = {
        "Ayakkabı": ["ayakkabı", "ayakkabi"],
        "Giyim": ["giyim", "kıyafet", "kiyafet"],
        "Elektronik": ["elektronik"],
        "Aksesuar": ["aksesuar"],
    }

    for term in category_terms.get(main_category, []):
        q = re.sub(rf"\b{term}\b", " ", q)

    q = re.sub(r"\s+", " ", q).strip()
    return q


def build_taxonomy_embeddings(model, taxonomy_records):
    taxonomy_texts = [item["text"] for item in taxonomy_records]

    taxonomy_embeddings = model.encode(taxonomy_texts)
    taxonomy_embeddings = np.array(taxonomy_embeddings).astype("float32")
    faiss.normalize_L2(taxonomy_embeddings)

    return taxonomy_embeddings


def semantic_taxonomy_match(query, model, taxonomy_embeddings, taxonomy_records):
    cleaned_query = clean_query_for_taxonomy(query)

    if len(cleaned_query) < 3:
        return None

    query_vector = model.encode([cleaned_query])
    query_vector = np.array(query_vector).astype("float32")
    faiss.normalize_L2(query_vector)

    scores = np.dot(taxonomy_embeddings, query_vector[0])

    best_index = int(np.argmax(scores))
    best_score = float(scores[best_index])

    if best_score < TAXONOMY_MATCH_THRESHOLD:
        return None

    matched_item = taxonomy_records[best_index].copy()
    matched_item["score"] = round(best_score, 3)

    return matched_item


def parse_query(query, df, model, taxonomy_embeddings, taxonomy_records):
    min_price, max_price = extract_price_range(query)

    explicit_main_category = extract_explicit_main_category(query, df)
    taxonomy_match = semantic_taxonomy_match(
        query,
        model,
        taxonomy_embeddings,
        taxonomy_records
    )

    parsed = {
        "min_price": min_price,
        "max_price": max_price,
        "main_category": explicit_main_category,
        "sub_category": None,
        "target_group": find_value_from_column(query, df, "target_group"),
        "product_type": None,
        "features": extract_features(query),
        "contexts": extract_contexts(query),
        "taxonomy_match": taxonomy_match,
    }

    if taxonomy_match is not None:
        field = taxonomy_match["field"]
        value = taxonomy_match["value"]

        remaining_query = remaining_query_after_category(query, explicit_main_category)

        if explicit_main_category is not None and field in ["sub_category", "product_type"]:
            if len(remaining_query) < 3:
                return parsed

        if field == "main_category" and explicit_main_category is not None:
            return parsed

        parsed[field] = value

    return parsed