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
    "yaz": ["yazlık", "hafif", "nefes alabilir"],
    "yazlık": ["yazlık", "hafif", "nefes alabilir"],
    "yazlik": ["yazlık", "hafif", "nefes alabilir"],
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
        "öner", "oner", "öneri", "oneri", "tavsiye",
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

def remaining_query_after_known_intent(query, parsed_query):
    q = clean_query_for_taxonomy(query)

    terms = [
        parsed_query.get("main_category"),
        parsed_query.get("sub_category"),
        parsed_query.get("product_type"),
    ]

    extra_terms = {
        "Ayakkabı": ["ayakkabı", "ayakkabi"],
        "Giyim": ["giyim", "kıyafet", "kiyafet"],
        "Elektronik": ["elektronik"],
        "Kamp": ["kamp"],
        "Spor": ["spor"],
    }

    for term in terms:
        if term is None:
            continue

        term_text = str(term).lower()
        q = re.sub(rf"\b{re.escape(term_text)}\b", " ", q)

        for extra in extra_terms.get(str(term), []):
            q = re.sub(rf"\b{re.escape(extra)}\b", " ", q)

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
    
    explicit_sub_category = find_value_from_column(query, df, "sub_category")
    explicit_product_type = find_value_from_column(query, df, "product_type")

    # Yazlık / kışlık gibi ifadeler bazı ürünlerde product_type olabilir,
    # ama ayakkabı gibi kategorilerde mevsim/özellik olarak kalmalıdır.
    seasonal_product_types = ["Yazlık", "Kışlık"]

    if explicit_product_type in seasonal_product_types:
        # Sadece Elbise gibi ürünlerde Yazlık/Abiye benzeri product_type kullanılsın.
        # Örnek: "kadın yazlık elbise" -> product_type Yazlık olabilir.
        # Örnek: "yazlık erkek ayakkabı" -> product_type Yazlık olmamalı.
        if explicit_sub_category != "Elbise":
            explicit_product_type = None
    
    parsed = {
        "min_price": min_price,
        "max_price": max_price,
        "main_category": explicit_main_category,
        "sub_category": explicit_sub_category,
        "product_type": explicit_product_type,
        "target_group": find_value_from_column(query, df, "target_group"),
        "features": extract_features(query),
        "contexts": extract_contexts(query),
        "taxonomy_match": taxonomy_match,
    }

    if taxonomy_match is not None:
        field = taxonomy_match["field"]
        value = taxonomy_match["value"]

        remaining_query = remaining_query_after_known_intent(query, parsed)

        # Kullanıcı açıkça genel bir ana kategori yazdıysa ve geriye detay kalmadıysa
        # taxonomy'nin daha dar alt kategori/product_type seçmesine izin verme.
        # Örnek: "ayakkabı öner" -> Sneaker yapma.
        if explicit_main_category is not None and field in ["sub_category", "product_type"]:
            if len(remaining_query) < 3:
                return parsed

        # Kullanıcı açıkça alt kategori yazdıysa ve geriye detay kalmadıysa
        # taxonomy'nin product_type seçmesine izin verme.
        # Örnek: "elbise öner" -> Abiye yapma.
        if explicit_sub_category is not None and field == "product_type":
            if len(remaining_query) < 3:
                return parsed

        if field == "main_category" and explicit_main_category is not None:
            return parsed

        seasonal_product_types = ["Yazlık", "Kışlık"]

        if field == "product_type" and value in seasonal_product_types:
            clothing_words = [
                "giyim", "elbise", "gömlek", "gomlek",
                "mont", "pantolon", "tişört", "tisort"
            ]

            q_lower = query.lower()

            # Yazlık/Kışlık bazı durumlarda ürün tipi değil, özellik/mevsim bilgisidir.
            # Örnek: "yazlık erkek ayakkabı" -> product_type Yazlık olmamalı.
            # Ama "kadın yazlık elbise" -> product_type Yazlık olabilir.
            if not any(word in q_lower for word in clothing_words):
                return parsed

        if parsed.get(field) is None:
            parsed[field] = value

    return parsed


def count_matching_products_for_intent(parsed_query, df):
    filtered = df.copy()

    for field in ["main_category", "sub_category", "product_type"]:
        value = parsed_query.get(field)

        if value is not None:
            filtered = filtered[
                filtered[field].astype(str).str.lower() == str(value).lower()
            ]

    return len(filtered)


def has_any_product_signal(parsed_query):
    return any([
        parsed_query["main_category"] is not None,
        parsed_query["sub_category"] is not None,
        parsed_query["product_type"] is not None,
        parsed_query["target_group"] is not None,
        len(parsed_query["features"]) > 0,
        len(parsed_query["contexts"]) > 0,
        parsed_query["min_price"] is not None,
        parsed_query["max_price"] is not None,
    ])


def is_query_too_general(query, parsed_query, df):
    has_price = (
        parsed_query["min_price"] is not None or
        parsed_query["max_price"] is not None
    )

    has_target_group = parsed_query["target_group"] is not None
    has_features = len(parsed_query["features"]) > 0
    has_contexts = len(parsed_query["contexts"]) > 0

    has_detail = any([
        has_price,
        has_target_group,
        has_features,
        has_contexts,
    ])

    has_main_category = parsed_query["main_category"] is not None
    has_sub_category = parsed_query["sub_category"] is not None
    has_product_type = parsed_query["product_type"] is not None

    has_category_intent = has_main_category or has_sub_category or has_product_type

    # Kullanıcı fiyat/hedef/özellik vermiş ama ne tür ürün istediğini söylememişse
    # direkt ürün önermek yerine kategori sormak daha doğru.
    # Örnek: "1500 TL altında yazlık erkek"
    if not has_category_intent and has_detail:
        return True

    matching_product_count = count_matching_products_for_intent(parsed_query, df)

    # Kullanıcı zaten fiyat, hedef kitle, özellik veya bağlam verdiyse detaylıdır.
    if has_detail:
        return False

    # Sadece ana kategori varsa çok geneldir.
    # Örnek: ayakkabı, giyim, elektronik
    if has_main_category and not has_sub_category and not has_product_type:
        return True

    # Alt kategori varsa ama altında birden fazla ürün varsa soru sor.
    # Örnek: elbise -> yazlık mı, abiye mi?
    if has_sub_category and not has_product_type:
        return matching_product_count > 1

    # Ürün tipi varsa genelde yeterince nettir.
    # Örnek: powerbank, mouse, klavye, akıllı saat
    # Ama aynı ürün tipinden çok fazla seçenek varsa soru sorabilir.
    if has_product_type:
        return matching_product_count > 3

    return False


CATEGORY_FOLLOW_UP_QUESTIONS = {
    "Ayakkabı": "Ayakkabıyı günlük kullanım, spor, yürüyüş, yazlık/kışlık kullanım veya özel gün için mi arıyorsun? Ayrıca belirli bir bütçen var mı?",

    "Giyim": "Giyim ürününü günlük kullanım, ofis, özel gün, yazlık veya kışlık kullanım için mi arıyorsun? Bütçen varsa onu da yazabilirsin.",

    "Kişisel Bakım": "Kişisel bakım ürünü için hangi ihtiyaca odaklanıyorsun? Örneğin saç dökülmesi, kepek, kuruluk, yağlı cilt veya nemlendirme gibi bir problem var mı?",

    "Elektronik": "Elektronik ürünü hangi kullanım için arıyorsun? Oyun, ofis, telefon, spor veya günlük kullanım gibi bir amaç ve bütçe belirtebilirsin.",

    "Kamp": "Kamp ürünü için neye ihtiyacın var? Uyku, aydınlatma, yemek hazırlama, oturma veya barınma gibi kullanım amacını yazabilirsin.",

    "Spor": "Spor ürününü hangi amaçla arıyorsun? Fitness, koşu, yoga, outdoor veya günlük egzersiz gibi bir kullanım amacı belirtebilirsin.",
}

def infer_main_category_from_parsed(parsed_query, df):
    if parsed_query.get("main_category") is not None:
        return parsed_query["main_category"]

    sub_category = parsed_query.get("sub_category")
    product_type = parsed_query.get("product_type")

    if sub_category is not None:
        matched_rows = df[
            df["sub_category"].astype(str).str.lower() == str(sub_category).lower()
        ]

        if not matched_rows.empty:
            return matched_rows["main_category"].mode().iloc[0]

    if product_type is not None:
        matched_rows = df[
            df["product_type"].astype(str).str.lower() == str(product_type).lower()
        ]

        if not matched_rows.empty:
            return matched_rows["main_category"].mode().iloc[0]

    return None

def build_follow_up_question(parsed_query, df):
    main_category = infer_main_category_from_parsed(parsed_query, df)

    if main_category in CATEGORY_FOLLOW_UP_QUESTIONS:
        return CATEGORY_FOLLOW_UP_QUESTIONS[main_category]

    return "Biraz daha detay verebilir misin? Kullanım amacı, hedef kişi, fiyat aralığı veya aradığın özellikleri yazarsan daha doğru ürün önerebilirim."


def get_clarification_response(query, parsed_query, df):
    # Katalogda hiçbir kategori, ürün tipi, özellik veya bağlam yakalanmadıysa
    # tüm ürünlerde arama yapıp alakasız sonuç döndürme.
    if not has_any_product_signal(parsed_query):
        return {
            "needs_clarification": False,
            "follow_up_question": None,
            "no_catalog_match": True,
        }

    if is_query_too_general(query, parsed_query, df):
        question = build_follow_up_question(parsed_query, df)

        return {
            "needs_clarification": True,
            "follow_up_question": question,
            "no_catalog_match": False,
        }

    return {
        "needs_clarification": False,
        "follow_up_question": None,
        "no_catalog_match": False,
    }