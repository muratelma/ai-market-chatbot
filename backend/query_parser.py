import re
import numpy as np
import faiss


DEFAULT_TAXONOMY_MATCH_THRESHOLD = 0.45
TURKISH_CHAR_MAP = str.maketrans({
    "ç": "c",
    "ğ": "g",
    "ı": "i",
    "ö": "o",
    "ş": "s",
    "ü": "u",
})


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
    # Cooking: tighten to distinguish "yemek yapmak" (cooking) from dishes/plates
    "yemek": ["pişirme", "ocak", "kamp ocağı", "yemek yapma"],
    "pişirme": ["pişirme", "ocak", "kamp ocağı"],
    "pisirme": ["pişirme", "ocak", "kamp ocağı"],
    "pişir": ["pişirme", "ocak"],
    "pisir": ["pişirme", "ocak"],
    "ocak": ["pişirme", "ocak"],
    "yaz": ["yazlık", "hafif", "nefes alabilir"],
    "yazlık": ["yazlık", "hafif", "nefes alabilir"],
    "yazlik": ["yazlık", "hafif", "nefes alabilir"],
    "dökülme": ["saç dökülmesi", "dökülme karşıtı", "güçlendirici"],
    "saç dökülmesi": ["saç dökülmesi", "dökülme karşıtı", "güçlendirici"],
    "kepek": ["kepek", "kepek karşıtı"],
    "kuru saç": ["kuru saç", "nemlendirici", "onarıcı"],
    "yağlı saç": ["yağlı saç", "yağ dengeleyici"],
    # Skin care
    "yağlı cilt": ["yağlı cilt", "yağ dengeleyici", "mat"],
    "kuru cilt": ["kuru cilt", "nemlendirici", "onarıcı"],
    "hassas cilt": ["hassas cilt", "parfümsüz"],
    "sivilce": ["sivilce", "akne", "arındırıcı", "yağ dengeleyici"],
    "morluk": ["morluk", "aydınlatıcı", "göz altı"],
    "pişik": ["pişik", "kızarıklık", "koruyucu"],
    # Sports / fitness
    "egzersiz": ["egzersiz", "spor", "antrenman"],
    "fitness": ["fitness", "egzersiz", "antrenman"],
    "koşu": ["koşu", "maraton", "outdoor"],
    # Automotive
    "araç": ["araç", "araba", "otomotiv"],
    "araba": ["araç", "araba"],
    # Home
    "dekoratif": ["dekoratif", "dekorasyon", "süsleme"],
    "lamba": ["lamba", "aydınlatma", "ışık"],
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

QUERY_ALIASES = [
    {
        "keywords": ["pişik kremi", "pisik kremi"],
        "fields": {
            "main_category": "Anne & Bebek",
            "sub_category": "Bakım",
            "product_type": "Pişik Kremi",
        },
    },
    {
        "keywords": ["yoga için mat", "yoga mat", "yoga matı"],
        "fields": {
            "main_category": "Spor",
            "product_type": "Yoga Matı",
            "features": ["yoga", "mat", "kaymaz"],
        },
    },
    {
        "keywords": ["araç şarj", "arac şarj", "araba şarj", "araç için telefon şarj"],
        "fields": {
            "main_category": "Otomotiv",
            "sub_category": "Elektronik",
            "product_type": "Araç Şarj Cihazı",
        },
    },
    {
        "keywords": ["dekoratif lamba", "dekoratif ışık", "dekoratif isik"],
        "fields": {
            "main_category": "Ev & Yaşam",
            "sub_category": "Aydınlatma",
            "features": ["dekoratif", "lamba", "ışık"],
        },
    },
    # Cooking in camp context: "yemek yapacak" should prefer Kamp Ocağı over dishes/plates
    {
        "keywords": ["kamp için yemek yapacak", "kamp yemek yapacak", "kamp için pişirme", "kamp ocağı"],
        "fields": {
            "main_category": "Kamp",
            "sub_category": "Pişirme",
            "product_type": "Kamp Ocağı",
        },
    },
    {
        "keywords": ["kahve makinesi", "türk kahvesi makinesi", "espresso makinesi"],
        "fields": {
            "main_category": "Mutfak",
            "sub_category": "Küçük Ev Aleti",
            "product_type": "Kahve Makinesi",
        },
    },
    {
        "keywords": ["robot süpürge", "akıllı süpürge"],
        "fields": {
            "main_category": "Ev & Yaşam",
        },
    },
]

def normalize_text_for_match(text):
    normalized = str(text).lower().translate(TURKISH_CHAR_MAP)
    normalized = re.sub(r"[^\w\s]", " ", normalized)
    normalized = re.sub(r"\s+", " ", normalized).strip()
    return normalized


def contains_phrase(text, phrase):
    normalized_text = normalize_text_for_match(text)
    normalized_phrase = normalize_text_for_match(phrase)

    if not normalized_phrase:
        return False

    pattern = rf"(?:^|\s){re.escape(normalized_phrase)}(?:\s|$)"
    return re.search(pattern, normalized_text) is not None


def apply_query_aliases(query, parsed_query):
    for rule in QUERY_ALIASES:
        if any(contains_phrase(query, keyword) for keyword in rule["keywords"]):
            for field, value in rule["fields"].items():
                if field == "features":
                    for feature in value:
                        if feature not in parsed_query["features"]:
                            parsed_query["features"].append(feature)
                else:
                    parsed_query[field] = value

    return parsed_query

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
    values = df[column_name].dropna().unique().tolist()

    for value in values:
        value_text = str(value)
        if value_text and contains_phrase(query, value_text):
            return value

    return None


def extract_features(query):
    found_features = []

    for keyword, mapped_features in FEATURE_SYNONYMS.items():
        if contains_phrase(query, keyword):
            found_features.extend(mapped_features)

    return list(set(found_features))


def extract_contexts(query):
    contexts = []

    for word in CONTEXT_KEYWORDS:
        if contains_phrase(query, word):
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
    # Category names that are also common context words and need special handling
    ambiguous_categories = ["kamp", "spor"]

    # Phrase aliases for compound or abbreviated category names that won't match
    # their full name as it appears in the database (e.g. "Ev & Yaşam" → "ev")
    category_phrase_aliases = {
        "Ev & Yaşam": ["ev & yaşam", "ev & yasam"],
        "Anne & Bebek": ["anne & bebek"],
        "Kişisel Bakım": ["kişisel bakım", "kisisel bakim"],
        "Otomotiv": ["otomotiv", "araç", "arac", "araba"],
        "Mutfak": ["mutfak"],
        "Kırtasiye": ["kırtasiye", "kirtasiye"],
        "Aksesuar": ["aksesuar"],
    }

    values = df["main_category"].dropna().unique().tolist()

    for value in values:
        value_lower = str(value).lower()

        if value_lower in ambiguous_categories:
            continue

        # Check phrase aliases first (most specific match wins)
        if value in category_phrase_aliases:
            for alias in category_phrase_aliases[value]:
                if contains_phrase(query, alias):
                    return value
            continue  # Already checked via aliases; skip generic match below

        # Generic match: category name appears literally in the query
        if contains_phrase(query, value_lower):
            return value

        # ASCII Turkish fallback for Ayakkabı
        if value_lower == "ayakkabı" and contains_phrase(query, "ayakkabi"):
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


def semantic_taxonomy_match(query, model, taxonomy_embeddings, taxonomy_records, taxonomy_match_threshold=DEFAULT_TAXONOMY_MATCH_THRESHOLD):
    cleaned_query = clean_query_for_taxonomy(query)

    if len(cleaned_query) < 3:
        return None

    query_vector = model.encode([cleaned_query])
    query_vector = np.array(query_vector).astype("float32")
    faiss.normalize_L2(query_vector)

    scores = np.dot(taxonomy_embeddings, query_vector[0])

    best_index = int(np.argmax(scores))
    best_score = float(scores[best_index])

    if best_score < taxonomy_match_threshold:
        return None

    matched_item = taxonomy_records[best_index].copy()
    matched_item["score"] = round(best_score, 3)

    return matched_item


def parse_query(query, df, model, taxonomy_embeddings, taxonomy_records, taxonomy_match_threshold=DEFAULT_TAXONOMY_MATCH_THRESHOLD):
    min_price, max_price = extract_price_range(query)

    explicit_main_category = extract_explicit_main_category(query, df)
    taxonomy_match = semantic_taxonomy_match(
        query,
        model,
        taxonomy_embeddings,
        taxonomy_records,
        taxonomy_match_threshold=taxonomy_match_threshold,
    )
    
    explicit_sub_category = find_value_from_column(query, df, "sub_category")
    explicit_product_type = find_value_from_column(query, df, "product_type")

    if " için " in query.lower():
        parts = query.lower().split(" için ", 1)
        if len(parts) == 2:
            y_part = parts[1].strip()
            y_type = find_value_from_column(y_part, df, "product_type")
            if y_type:
                explicit_product_type = y_type

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

    parsed = apply_query_aliases(query, parsed)
    inferred_main_category = infer_main_category_from_parsed(parsed, df)

    if parsed["main_category"] is None and inferred_main_category is not None:
        parsed["main_category"] = inferred_main_category

    if taxonomy_match is not None:
        field = taxonomy_match["field"]
        value = taxonomy_match["value"]

        remaining_query = remaining_query_after_known_intent(query, parsed)

        # Kullanıcı açıkça genel bir ana kategori yazdıysa ve geriye detay kalmadıysa
        # taxonomy'nin daha dar alt kategori/product_type seçmesine izin verme.
        # Örnek: "ayakkabı öner" -> Sneaker yapma.
        if explicit_main_category is not None and field in ["sub_category", "product_type"]:
            if len(remaining_query) < 3:
                parsed = normalize_category_consistency(parsed, df, query)
                return parsed

        # Kullanıcı açıkça alt kategori yazdıysa ve geriye detay kalmadıysa
        # taxonomy'nin product_type seçmesine izin verme.
        # Örnek: "elbise öner" -> Abiye yapma.
        if explicit_sub_category is not None and field == "product_type":
            if len(remaining_query) < 3:
                parsed = normalize_category_consistency(parsed, df, query)
                return parsed

        if field == "main_category" and parsed["main_category"] is not None:
            parsed = normalize_category_consistency(parsed, df, query)
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
                parsed = normalize_category_consistency(parsed, df, query)
                return parsed

        if parsed.get(field) is None:
            parsed[field] = value

    parsed = normalize_category_consistency(parsed, df, query)

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

    # Filter out direct category synonyms or context terms from the features/contexts count
    # ONLY when this is a generic category-level query (no subcategory or product type specified).
    # This avoids treating a category term as a query detail for itself (e.g. "spor" under "Spor").
    main_category = parsed_query.get("main_category")
    features = parsed_query.get("features", [])
    contexts = parsed_query.get("contexts", [])

    if main_category is not None and parsed_query.get("sub_category") is None and parsed_query.get("product_type") is None:
        main_cat_lower = str(main_category).lower()
        ignore_terms = {main_cat_lower}
        if main_cat_lower in FEATURE_SYNONYMS:
            ignore_terms.update([term.lower() for term in FEATURE_SYNONYMS[main_cat_lower]])
        
        features = [f for f in features if f.lower() not in ignore_terms]
        contexts = [c for c in contexts if c.lower() not in ignore_terms]

    has_features = len(features) > 0
    has_contexts = len(contexts) > 0

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

    # Sub-category is a fairly specific signal. On a 750-product catalog
    # having 2-5 products per sub-category is normal; only ask for
    # clarification when there are enough variants to make choice meaningful.
    if has_sub_category and not has_product_type:
        return matching_product_count > 5

    # Product type is already a strong, specific signal. Only ask for
    # clarification when there are many variants of the same type and
    # no other discriminating context (price, features, target group) is given.
    # Threshold tuned for a 750-product catalog where 5-10 items per type is normal.
    if has_product_type:
        return matching_product_count > 20


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

def infer_main_category_from_query_context(query):
    context_category_map = {
        "kamp": "Kamp",
        "outdoor": "Kamp",
        "çadır": "Kamp",
        "cadir": "Kamp",
        "spor": "Spor",
        "fitness": "Spor",
        "kosu": "Spor",
        "koşu": "Spor",
        # Home & Living
        "ev": "Ev & Yaşam",
        "dekoratif": "Ev & Yaşam",
        "dekorasyon": "Ev & Yaşam",
        # Kitchen
        "mutfak": "Mutfak",
        "kahve": "Mutfak",
        "blender": "Mutfak",
        "mikser": "Mutfak",
        # Baby & Mother
        "bebek": "Anne & Bebek",
        "pişik": "Anne & Bebek",
        "pisik": "Anne & Bebek",
        "hamile": "Anne & Bebek",
        "emzik": "Anne & Bebek",
        # Automotive
        "araç": "Otomotiv",
        "arac": "Otomotiv",
        "otomobil": "Otomotiv",
        "araba": "Otomotiv",
        # Stationery
        "kırtasiye": "Kırtasiye",
        "kalem": "Kırtasiye",
        "defter": "Kırtasiye",
    }

    matched_categories = set()

    for keyword, category in context_category_map.items():
        if contains_phrase(query, keyword):
            matched_categories.add(category)

    if len(matched_categories) == 1:
        return list(matched_categories)[0]

    return None


def normalize_category_consistency(parsed_query, df, query):
    context_main_category = infer_main_category_from_query_context(query)

    # Ana kategori ile alt kategori aynıysa alt kategoriyi temizle.
    # Örnek: main_category=Elektronik, sub_category=Elektronik yanlış.
    if (
        parsed_query.get("main_category") is not None and
        parsed_query.get("sub_category") is not None and
        str(parsed_query["main_category"]).lower() == str(parsed_query["sub_category"]).lower()
    ):
        parsed_query["sub_category"] = None

    product_type = parsed_query.get("product_type")

    # Product type varsa en güvenilir bilgi genelde product_type'tır.
    # Örnek: Akıllı Saat -> Elektronik / Giyilebilir Teknoloji
    if product_type is not None:
        product_type_lower = str(product_type).lower()

        matched_rows = df[
            df["product_type"].astype(str).str.lower() == product_type_lower
        ]

        if not matched_rows.empty:
            correct_main_category = matched_rows["main_category"].mode().iloc[0]
            parsed_query["main_category"] = correct_main_category

            unique_sub_categories = matched_rows["sub_category"].dropna().unique().tolist()

            # Eğer product_type sadece tek sub_category altında geçiyorsa onu kullan.
            # Örnek: Kahve Makinesi -> Küçük Ev Aleti
            if len(unique_sub_categories) == 1:
                parsed_query["sub_category"] = unique_sub_categories[0]

            # Eğer product_type birden fazla sub_category altında geçiyorsa
            # sub_category filtresini kaldır. Çünkü product_type zaten yeterince net.
            # Örnek: Yoga Matı hem Egzersiz hem Yoga altında olabilir.
            else:
                parsed_query["sub_category"] = None

            # [Precedence Check] If there is a strong query context main category that differs from
            # the product type's default main category, allow the context category to take precedence
            # ONLY if we can find a matching relaxed product type in that category.
            # Do NOT relax if the user explicitly typed the exact product type in their query.
            if context_main_category is not None and context_main_category != correct_main_category and not contains_phrase(query, product_type_lower):
                words = [w for w in product_type_lower.split() if len(w) > 2]
                relaxed_type = None
                for word in reversed(words):
                    candidate_types = df[df["main_category"] == context_main_category]["product_type"].dropna().unique()
                    for c_type in candidate_types:
                        if word in c_type.lower():
                            relaxed_type = word.title()
                            break
                    if relaxed_type:
                        break
                
                if relaxed_type:
                    parsed_query["main_category"] = context_main_category
                    parsed_query["product_type"] = relaxed_type
                else:
                    # Restore correct main category and return early since no match exists in context_main_category
                    parsed_query["main_category"] = correct_main_category
                    return parsed_query
            else:
                return parsed_query

    # Product type yoksa ve sorguda güçlü bağlam varsa onu ana kategori olarak kullan.
    # Örnek: "kamp için gece ışık" -> Kamp > Aydınlatma
    if context_main_category is not None:
        parsed_query["main_category"] = context_main_category

    # Context düzeltmesinden sonra ana kategori ve alt kategori aynı olduysa temizle.
    if (
        parsed_query.get("main_category") is not None and
        parsed_query.get("sub_category") is not None and
        str(parsed_query["main_category"]).lower() == str(parsed_query["sub_category"]).lower()
    ):
        parsed_query["sub_category"] = None

    # Main category + sub_category birlikte varsa gerçekten ürünlerde var mı kontrol et.
    if (
        parsed_query.get("main_category") is not None and
        parsed_query.get("sub_category") is not None
    ):
        check_rows = df[
            (df["main_category"].astype(str).str.lower() == str(parsed_query["main_category"]).lower()) &
            (df["sub_category"].astype(str).str.lower() == str(parsed_query["sub_category"]).lower())
        ]

        # Eğer bu ikili dataset'te yoksa, sub_category'nin gerçek main_category'sini bulmaya çalış
        if check_rows.empty:
            sub_category_lower = str(parsed_query["sub_category"]).lower()
            matched_rows = df[df["sub_category"].astype(str).str.lower() == sub_category_lower]
            if not matched_rows.empty:
                unique_main_categories = matched_rows["main_category"].dropna().unique().tolist()
                if len(unique_main_categories) == 1:
                    parsed_query["main_category"] = unique_main_categories[0]
                else:
                    parsed_query["sub_category"] = None
            else:
                parsed_query["sub_category"] = None

    # Hâlâ main_category boş ama sub_category varsa, sadece tek ana kategoriye bağlıysa doldur.
    if (
        parsed_query.get("main_category") is None and
        parsed_query.get("sub_category") is not None
    ):
        sub_category_lower = str(parsed_query["sub_category"]).lower()

        matched_rows = df[
            df["sub_category"].astype(str).str.lower() == sub_category_lower
        ]

        if not matched_rows.empty:
            unique_main_categories = matched_rows["main_category"].dropna().unique().tolist()

            if len(unique_main_categories) == 1:
                parsed_query["main_category"] = unique_main_categories[0]

    return parsed_query

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