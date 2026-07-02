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
    "yemek": ["pişirme", "yemek yapma"],
    "pişirme": ["pişirme"],
    "pisirme": ["pişirme"],
    "pişir": ["pişirme"],
    "pisir": ["pişirme"],
    "ocak": ["pişirme", "ocak", "kamp ocağı"],
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
        "keywords": ["araç şarj", "arac şarj", "araba şarj", "araç için telefon şarj",
                     "arabada şarj", "arabada telefon şarj"],
        "fields": {
            "main_category": "Otomotiv",
            "sub_category": "Elektronik",
            "product_type": "Araç Şarj Cihazı",
        },
    },
    # Power bank / portable charger.  The word "şarj" semantically attracts the
    # many car chargers ("Araç Şarj Cihazı"), so an explicit power-bank request —
    # or the canonical implicit complaint "şarjım dışarıda bitiyor" once the
    # normalizer expands it — must pin deterministically to the Powerbank
    # product_type.  This keeps the result correct even with Ollama disabled.
    # Sub_category is intentionally left unset: power banks live under both
    # "Telefon Aksesuarı" and "Aksesuar", so we constrain only main_category.
    {
        "keywords": ["powerbank", "power bank", "taşınabilir şarj", "tasinabilir şarj",
                     "taşınabilir şarj cihazı", "taşınabilir şarj aleti",
                     "harici batarya", "harici pil", "yedek batarya",
                     "telefon için taşınabilir şarj"],
        "fields": {
            "main_category": "Elektronik",
            "product_type": "Powerbank",
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
    # Cooking in camp context
    {
        "keywords": ["kamp için yemek yapacak", "kamp yemek yapacak", "kamp için pişirme",
                     "kamp ocağı", "kamp yemeği için ocak", "kamp yemeği ocak",
                     "kamp yaparken yemek", "kampta yemek", "kamp için yemek",
                     "kamp yemeği hazırlamak", "kampta yemek yapmak",
                     "kamp için yemek hazırlamak"],
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
    # Dry shampoo: "su gerektirmeyen" / "susuz" should map to Kuru Şampuan
    {
        "keywords": ["su gerektirmeyen şampuan", "susuz şampuan", "kuru şampuan"],
        "fields": {
            "main_category": "Kişisel Bakım",
            "sub_category": "Saç Bakımı",
            "product_type": "Kuru Şampuan",
        },
    },
    # Action-to-product: listening to music -> headphones
    {
        "keywords": ["müzik dinlemek için", "müzik dinlemek", "şarkı dinlemek"],
        "fields": {
            "main_category": "Elektronik",
            "product_type": "Kulaklık",
        },
    },
    # Tent lighting
    {
        "keywords": ["çadır içi aydınlatma", "çadır aydınlatma", "çadır lambası"],
        "fields": {
            "main_category": "Kamp",
            "sub_category": "Aydınlatma",
            "product_type": "Kamp Lambası",
        },
    },
    # Water bottle / canteen
    {
        "keywords": ["su matarası", "matara", "su şişesi"],
        "fields": {
            "product_type": "Matara",
        },
    },
    # Computer monitor
    {
        "keywords": ["bilgisayar monitörü", "monitör", "bilgisayar ekranı"],
        "fields": {
            "main_category": "Elektronik",
            "sub_category": "Bilgisayar",
            "product_type": "Monitör",
        },
    },
    # Tablet stylus: "dokunmatik kalem" / "stylus" is a touchscreen pen, not a
    # writing pen — without this it mis-routes to Kırtasiye › Kalem.  Pin it to
    # the Elektronik tablet-pen product_type so the tablet styluses surface.
    {
        "keywords": ["dokunmatik kalem", "tablet kalemi", "tablet kalem",
                     "stylus kalem", "stylus", "tablet için kalem",
                     "tablet için dokunmatik kalem"],
        "fields": {
            "main_category": "Elektronik",
            "sub_category": "Tablet Aksesuarı",
            "product_type": "Tablet Kalemi",
        },
    },
    # Outdoor pants
    {
        "keywords": ["doğa yürüyüşü için pantolon", "outdoor pantolon", "trekking pantolon",
                     "yürüyüş pantolonu"],
        "fields": {
            "main_category": "Giyim",
            "sub_category": "Pantolon",
            "product_type": "Kargo Pantolon",
        },
    },
    # Sports towel
    {
        "keywords": ["spor havlusu", "spor salonu havlu", "spor salonu için havlu",
                     "ter havlusu"],
        "fields": {
            "main_category": "Spor",
            "sub_category": "Aksesuar",
            "product_type": "Spor Havlusu",
        },
    },
    # Keyboard Mouse Set
    {
        "keywords": ["klavye mouse takım", "klavye fare set"],
        "fields": {
            "main_category": "Elektronik",
            "sub_category": "Bilgisayar",
            "product_type": "Klavye Mouse Set",
        },
    },
    # Skin serum: the embedding model maps "cilt serum"/"yüz serum" to
    # Cilt Bakımı only weakly (~0.44, below the 0.65 taxonomy threshold), and
    # the Ollama normalizer sometimes hallucinates "cilt" → "saç" — so a skin
    # serum request silently drifts to Saç Serumu.  Pin it deterministically.
    {
        "keywords": ["cilt için serum", "cilt serum", "cilt serumu",
                     "yüz için serum", "yüz serum", "yüz serumu",
                     "cilt bakım serumu", "yüz bakım serumu"],
        "fields": {
            "main_category": "Kişisel Bakım",
            "sub_category": "Cilt Bakımı",
            "product_type": "Cilt Serumu",
        },
    },
    # Hair serum: symmetric pin so "saç (için) serum" always resolves to the
    # hair product_type rather than a generic Saç Bakımı sub-category.
    {
        "keywords": ["saç için serum", "saç serum", "saç serumu",
                     "saç bakım serumu"],
        "fields": {
            "main_category": "Kişisel Bakım",
            "sub_category": "Saç Bakımı",
            "product_type": "Saç Serumu",
        },
    },
    # Hair-loss / general hair-care intent.  Without this, "bakım" matches the
    # Anne & Bebek › Bakım sub-category and "saç" matches baby hair brushes, so a
    # hair-loss request silently drifts to baby products.  Pin the category to
    # Kişisel Bakım › Saç Bakımı but leave product_type unset, so semantic search
    # still picks the right form (şampuan / serum / losyon) inside the pool.
    # Listed AFTER the hair-serum alias so an explicit "saç serumu" keeps its
    # more specific product_type.
    {
        "keywords": ["saç dökülmesi", "sac dokulmesi", "saç dökülme", "saç dökme",
                     "saç dökülmesine karşı", "dökülme karşıtı", "dökülmeye karşı",
                     "saç bakımı", "sac bakimi", "saç bakım", "saç bakım ürünü",
                     "saç güçlendirici", "saç güçlendiren", "kepek"],
        "fields": {
            "main_category": "Kişisel Bakım",
            "sub_category": "Saç Bakımı",
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


# ---------------------------------------------------------------------------
# Inflection-aware term matching (Turkish nominal suffixes)
# ---------------------------------------------------------------------------
# Whole-word matching misses inflected product nouns the user actually typed
# ("elbisesi", "elbiseleri", "pantolonu", "çantası", "şampuanı", "ayakkabıyı").
# That silently drops the explicit positive intent and lets modifier-driven
# taxonomy inference take over.  We match a catalog term against a query word
# when the word is the term plus a known Turkish nominal suffix (case / plural /
# possessive / instrumental).  Text is already folded to ASCII by
# ``normalize_text_for_match`` (ç→c, ğ→g, ı→i, ö→o, ş→s, ü→u), so suffixes are
# listed in their folded form.  Derivational suffixes (-lik/-li) are excluded
# on purpose — they change meaning ("elbiselik" = dress *fabric*).
_TR_INFLECTION_SUFFIXES: frozenset[str] = frozenset({
    "",
    "i", "u",                       # accusative / 3sg possessive
    "yi", "yu", "si", "su",         # same, after a vowel
    "e", "a", "ye", "ya",           # dative
    "de", "da", "te", "ta",         # locative
    "den", "dan", "ten", "tan",     # ablative
    "in", "un", "nin", "nun",       # genitive
    "n", "ni", "nu",                # 2sg possessive / buffer-n
    "ler", "lar",                   # plural
    "leri", "lari", "lere", "lara", # plural + case/possessive
    "lerin", "larin", "lerde", "larda", "lerden", "lardan",
    "le", "la", "yle", "yla",       # instrumental
})

# Minimum stem length for inflection matching — short terms ("bot") only match
# exactly to avoid false positives ("botanik").
_INFLECTION_MIN_STEM = 4


def _word_matches_term(word, term):
    """True when ``word`` is ``term`` (optionally + a Turkish nominal suffix)."""
    if word == term:
        return True
    if len(term) >= _INFLECTION_MIN_STEM and word.startswith(term):
        return word[len(term):] in _TR_INFLECTION_SUFFIXES
    return False


def product_type_overlap(a, b):
    """True when product_types ``a`` and ``b`` overlap at a WORD boundary.

    The catalog matches a shorter product_type inside a longer one for recall
    ("serum" ↔ "Saç Serumu", "şampuan" ↔ "Kuru Şampuan").  A naive ``in`` check,
    however, also fires on mid-word character runs — most damagingly "Bot" ⊂
    "Ro**bot** Süpürge", which makes boots look related to a robot vacuum.  We
    require the shorter type to begin at a word boundary in the longer one, which
    keeps the legitimate stem/prefix overlaps and rejects the spurious ones.
    \\b is Unicode-aware, so Turkish letters (ş, ı, ç …) bound correctly.
    """
    a = str(a).lower().strip()
    b = str(b).lower().strip()
    if not a or not b:
        return False
    if a == b:
        return True
    shorter, longer = (a, b) if len(a) <= len(b) else (b, a)
    return re.search(r"\b" + re.escape(shorter), longer) is not None


def contains_term(text, term):
    """Whole-word OR inflection-aware membership of ``term`` in ``text``.

    Multi-word terms keep the strict whole-phrase rule (``contains_phrase``);
    single-word terms additionally match common Turkish inflected forms.
    """
    if contains_phrase(text, term):
        return True

    term_norm = normalize_text_for_match(term)
    if not term_norm or " " in term_norm:
        return False

    return any(
        _word_matches_term(word, term_norm)
        for word in normalize_text_for_match(text).split()
    )


# Implicit charge-depletion complaint → power bank.  A phrase like "şarjım
# dışarıda bitiyor" / "pilim çabuk bitiyor" is an implicit power-bank request,
# but it semantically taxonomy-matches "Araç Şarj Cihazı" (both involve "şarj"),
# so without a deterministic rule the user gets car chargers.  We detect the
# depletion pattern (a charge noun + a "running out" verb) from the user's
# literal words and route it to Powerbank — independent of the Ollama
# normalizer.  Genuine in-car charging ("araç/araba") is excluded so explicit
# car-charger requests are preserved.  Text is ASCII-folded first (ş→s, ı→i…).
_POWER_COMPLAINT_CHARGE = re.compile(r"\b(sarj|pil|batarya)\w*")
_POWER_COMPLAINT_DEPLETE = re.compile(r"\b(bit|tuken|azal|dayanm|yetm)\w*")
_POWER_COMPLAINT_CAR = re.compile(r"\b(arac|araba|otomobil)\w*")


def is_power_depletion_complaint(query):
    """True for "şarjım/pilim/bataryam bitiyor" complaints (not car-charging)."""
    if not query:
        return False
    folded = normalize_text_for_match(query)
    if _POWER_COMPLAINT_CAR.search(folded):
        return False
    return bool(
        _POWER_COMPLAINT_CHARGE.search(folded)
        and _POWER_COMPLAINT_DEPLETE.search(folded)
    )


# Adult hair-/skin-care intent → Kişisel Bakım.  The generic Turkish word "bakım"
# (care) matches the Anne & Bebek › "Bakım" sub_category, and "saç"/"cilt" then
# pull baby products — so a verb-form complaint like "saçlarım dökülüyor" or
# "cildim çok kuru" silently drifts to Anne & Bebek.  We detect the intent from a
# body-part subject (saç / cilt / yüz) plus a care/symptom word, exclude explicit
# baby context, and pin the right Kişisel Bakım sub-category.  An explicitly named
# product form (şampuan / serum / …) is preserved so semantic search still
# distinguishes it; otherwise product_type is left to the search layer.
_BABY_CONTEXT = re.compile(r"\b(bebek|bebegim|bebegin|bebege|cocugum|cocuguma|yenidogan|emzik)\w*")

_HAIR_SUBJECT = re.compile(r"\b(sac|saclar|sacim|saclarim|saclarimi|sacimi)\w*|\bkepek\w*")
_HAIR_SYMPTOM = re.compile(
    r"\b(dokul|incel|seyrel|kiril|kepek|yagli|guclendir|besle|uzat|bakim|"
    r"sampuan|serum|maske|tonik|losyon|krem)\w*"
)

_SKIN_SUBJECT = re.compile(r"\b(cilt|cildim|cildimi|cildime|cildin|yuzum|yuzumu)\w*")
_SKIN_SYMPTOM = re.compile(
    r"\b(kuru|nemlendir|nem|leke|akne|sivilce|gozenek|yagli|kirisik|"
    r"bakim|krem|serum|tonik|peeling|maske|temizleyici)\w*"
)


def is_hair_care_request(query):
    """True for an adult hair-care intent (hair subject + care/symptom, no baby)."""
    if not query:
        return False
    folded = normalize_text_for_match(query)
    if _BABY_CONTEXT.search(folded):
        return False
    return bool(_HAIR_SUBJECT.search(folded) and _HAIR_SYMPTOM.search(folded))


def is_skin_care_request(query):
    """True for an adult skin-care intent (skin subject + care/symptom, no baby)."""
    if not query:
        return False
    folded = normalize_text_for_match(query)
    if _BABY_CONTEXT.search(folded):
        return False
    return bool(_SKIN_SUBJECT.search(folded) and _SKIN_SYMPTOM.search(folded))


def _hair_product_type(folded):
    """Map an explicitly named hair product form to its catalog product_type."""
    for keyword, product_type in (
        ("sampuan", "Şampuan"),
        ("serum", "Saç Serumu"),
    ):
        if keyword in folded:
            return product_type
    return None


def _skin_product_type(folded):
    """Map an explicitly named skin product form to its catalog product_type."""
    if "serum" in folded:
        return "Cilt Serumu"
    if "nemlendir" in folded or "krem" in folded:
        return "Nemlendirici"
    return None


# Camp cooking → Kamp › Pişirme.  A verbose "kamp yaparken kahve/çorba pişirmek"
# request drifts to Mutfak (a "Kahve Makinesi"/electric appliance) because the
# cooking words outweigh the lost "kamp" context.  We detect camp context + a
# cooking word and pin Kamp › Pişirme.  Pure camp queries without a cooking word
# (tent, chair, lamp) do not fire, so their explicit product types are preserved.
_CAMP_CONTEXT = re.compile(r"\b(kamp|kampta|kampi|kampta|outdoor)\w*")
_CAMP_COOK = re.compile(
    r"\b(pisir|yemek|ocak|kahve|corba|kaynat|isit|mangal|tencere|tava|kahvalti)\w*"
)


def is_camp_cooking_request(query):
    """True for a camp-cooking intent (camp context + a cooking word)."""
    if not query:
        return False
    folded = normalize_text_for_match(query)
    return bool(_CAMP_CONTEXT.search(folded) and _CAMP_COOK.search(folded))


# Yoga/pilates MAT → Spor › Yoga (product_type "Yoga Matı").  "yoga ve pilates"
# alone leans to a Pilates Topu (ball); the discriminating signal is a mat word
# ("mat", "minder", "yere serebileceğim").  Require both so a genuine ball
# request ("pilates topu") is untouched.
_YOGA_CONTEXT = re.compile(r"\b(yoga|pilates)\w*")
_YOGA_MAT = re.compile(r"\b(mat|minder)\w*|\byere ser")


def is_yoga_mat_request(query):
    """True for a yoga/pilates MAT intent (yoga context + a mat word)."""
    if not query:
        return False
    folded = normalize_text_for_match(query)
    return bool(_YOGA_CONTEXT.search(folded) and _YOGA_MAT.search(folded))


# Child shopper → target_group "Çocuk".  Strong child-purchase phrases ("oğlum
# yeni yürümeye başladı", "okula başlayan") carry no literal "çocuk" token, so the
# target group is lost and adult products surface.  Kept deliberately narrow to
# unambiguous child cues to avoid mislabelling adult queries.
_CHILD_CONTEXT = re.compile(
    r"\b(yurumeye basla|yeni yuru|okula basla|okula yeni|anaokul|kres|"
    r"cocugum|cocuguma|bebegim|bebegime)\w*"
)


def has_child_shopper_context(query):
    """True when the query clearly describes shopping for a child."""
    if not query:
        return False
    return bool(_CHILD_CONTEXT.search(normalize_text_for_match(query)))


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

    # "civarı" / "civarında" / "dolaylarında" -> apply ±30% tolerance
    approx_match = re.search(
        r"(\d+)\s*(?:tl|lira)?\s*(?:civarı|civarında|civarinda|dolaylarında|dolaylarinda|dolayı|dolayi)",
        q
    )
    if approx_match:
        center = int(approx_match.group(1))
        min_price = int(center * 0.7)
        max_price = int(center * 1.3)
        return min_price, max_price

    single_match = re.search(r"(\d+)\s*(?:tl|lira)", q)
    if single_match:
        max_price = int(single_match.group(1))

    return min_price, max_price


# ---------------------------------------------------------------------------
# Negative product-type / category constraints
# ---------------------------------------------------------------------------
# Users sometimes name a product/category only to *reject* it
# ("mont veya kaban değil, elbise arıyorum").  Those rejected terms must be
# treated as EXCLUDED, never as the desired intent.  Detection is fully
# deterministic and runs on the user's literal query, so it still works when
# Ollama normalization drops the negation.

# Words that, when they follow a product/category term, mark it as rejected.
_NEGATION_CUES: frozenset[str] = frozenset({
    "degil", "degildir", "degilim",
    "istemiyorum", "istemem", "istemedigim", "istemedim", "istemez",
    "aramiyorum", "aramam", "aramiyor",
    "olmasin", "istemyorum",
    "haric", "disinda",
})

# Connector words allowed between rejected terms in a single negative clause
# ("mont veya kaban değil" → both rejected).
_NEGATION_CONNECTORS: frozenset[str] = frozenset({
    "veya", "ya", "yada", "da", "de", "ve", "ile",
})

# Words that hard-close a negative clause when scanning backwards from a cue,
# so a rejection ("... değil") never reaches a positive term in a prior clause.
_NEGATION_BOUNDARY_WORDS: frozenset[str] = frozenset({
    "ama", "fakat", "ancak", "sadece", "yalniz", "yalnizca",
})

_NEGATION_BOUNDARY = "|"
_NEGATION_MAX_LOOKBACK = 6


def _build_excludable_token_index(df):
    """Map each catalog token → the full normalized category values it belongs to.

    Built from main_category / sub_category / product_type so a single rejected
    word like "mont" can be resolved back to every category value it identifies
    (the sub_category "Mont" and the product_types "Polar Mont", "Şişme Mont",
    ...).  Only tokens of length ≥ 3 are indexed to avoid noise.
    """
    index = {}
    for column in ("main_category", "sub_category", "product_type"):
        for value in df[column].dropna().unique():
            value_norm = normalize_text_for_match(str(value))
            if not value_norm:
                continue
            for token in value_norm.split():
                if len(token) >= 3:
                    index.setdefault(token, set()).add(value_norm)
    return index


def extract_excluded_terms(query, df):
    """Return the set of normalized catalog values the user explicitly rejected.

    Detects negative product-type/category constraints such as "mont değil",
    "kaban istemiyorum", "mont veya kaban değil", "mont/kaban istemiyorum".
    For each negation cue, walks backwards over the immediately preceding
    catalog terms (allowing connector words) and marks every matched catalog
    value as excluded.  Returns normalized full values (e.g. {"mont",
    "polar mont", "kaban"}), which downstream filtering matches against a row's
    main/sub/product fields.
    """
    if not query:
        return set()

    # Fold to ASCII like the catalog index, but keep clause boundaries as a
    # marker token so a rejection cannot cross into a neighbouring clause.
    # "/" is an enumeration separator ("mont/kaban"), NOT a boundary.
    folded = str(query).lower().translate(TURKISH_CHAR_MAP)
    folded = re.sub(r"[,.;:!?\n]+", f" {_NEGATION_BOUNDARY} ", folded)
    folded = re.sub(r"[^\w|\s]", " ", folded)
    tokens = folded.split()
    if not tokens:
        return set()

    token_index = _build_excludable_token_index(df)
    excluded = set()

    for i, token in enumerate(tokens):
        if token not in _NEGATION_CUES:
            continue

        # Walk backwards over the negative clause collecting rejected catalog
        # terms.  Before the first term is found we may skip filler/unknown
        # words (so a rejected term missing from the catalog, or a stray word,
        # doesn't break the chain); once a term is collected we only continue
        # over connectors/terms, stopping at the first other word so the scan
        # can't reach a positive term stated earlier ("elbise ... mont değil").
        started = False
        for j in range(i - 1, max(-1, i - 1 - _NEGATION_MAX_LOOKBACK), -1):
            word = tokens[j]
            if word == _NEGATION_BOUNDARY or word in _NEGATION_BOUNDARY_WORDS:
                break
            if word in token_index:
                excluded.update(token_index[word])
                started = True
                continue
            if word in _NEGATION_CONNECTORS:
                continue
            if started:
                break
            # else: not started yet — skip filler/unknown and keep scanning.

    return excluded


def _is_excluded(value, excluded):
    if not excluded or value is None:
        return False
    return normalize_text_for_match(str(value)) in excluded


def find_value_from_column(query, df, column_name, excluded=None):
    values = df[column_name].dropna().unique().tolist()

    for value in values:
        value_text = str(value)
        if _is_excluded(value_text, excluded):
            continue
        if value_text and contains_term(query, value_text):
            return value

    # Prefix fallback for product_type: when the user writes a base word
    # like "tencere" but the catalog has "Tencere Seti", match the base word
    # as a prefix of the catalog value.  Only applied to product_type to avoid
    # false positives on shorter category/sub-category names.
    if column_name == "product_type":
        q_lower = normalize_text_for_match(query)
        q_words = q_lower.split()

        # Collect main_category and sub_category words to exclude them —
        # "kamp" is a category, not a product-type prefix.
        category_words = set()
        for col in ("main_category", "sub_category"):
            for val in df[col].dropna().unique():
                for w in normalize_text_for_match(str(val)).split():
                    if len(w) >= 4:
                        category_words.add(w)

        # Remove intent/broad words that shouldn't be used as product prefixes
        skip_words = {
            "oner", "oener", "ariyorum", "istiyorum", "lazim",
            "urun", "malzeme", "tavsiye", "oneri", "icin",
            "bir", "sey", "esya",
            # Common Turkish adjectives/verbs that happen to be the first
            # word of a product_type ("Kuru Şampuan", "Okuma Lambası").
            # Without this guard they cause false positives like
            # "kuru cilt için ürün öner" → Kuru Şampuan, or
            # "zihin okuma cihazı" → Okuma Lambası.  Exact-phrase matches
            # for those PTs still work via contains_phrase above.
            "kuru", "okuma",
        }

        for value in values:
            if _is_excluded(value, excluded):
                continue
            value_norm = normalize_text_for_match(str(value))
            if not value_norm:
                continue

            value_words = value_norm.split()
            if len(value_words) < 2:
                # Only prefix-match multi-word product types
                # (single-word types should be caught by exact match above)
                continue

            value_first_word = value_words[0]
            if len(value_first_word) < 4:
                continue

            for q_word in q_words:
                if q_word in skip_words:
                    continue
                if q_word in category_words:
                    continue
                if q_word == value_first_word:
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


def extract_explicit_main_category(query, df, excluded=None):
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

        if _is_excluded(value, excluded):
            continue

        # Check phrase aliases first (most specific match wins)
        if value in category_phrase_aliases:
            for alias in category_phrase_aliases[value]:
                if contains_phrase(query, alias):
                    return value
            continue  # Already checked via aliases; skip generic match below

        # Generic match: category name appears in the query (inflection-aware,
        # so "ayakkabıyı", "giyimi", etc. still resolve to their category).
        if contains_term(query, value_lower):
            return value

        # ASCII Turkish fallback for Ayakkabı
        if value_lower == "ayakkabı" and contains_term(query, "ayakkabi"):
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


# Words that signal a broad product-recommendation intent in the user's
# *original* query.  We check the original (not the Ollama-normalized) form
# because the normalizer can expand a brief "ürün öner" into a richer
# phrase like "saç bakım ürünü" — and "bakım" alone happens to match the
# "Bakım" sub_category (Anne & Bebek / Otomotiv), which silently flips a
# broad request into a focused one.
_BROAD_INTENT_PATTERN = re.compile(
    r"\b(ürün|urun|malzeme|eşya|esya|şey|sey|"
    r"ne kullanabilirim|ne kullanmalıyım|ne kullanmaliyim|"
    r"bakım ürünü|bakim urunu)\w*\b"
)

# Product-type terms that, if the user types them explicitly, signal a
# focused intent — they block the broad strip even when broad-intent words
# are also present (e.g. "saç dökülmesi için şampuan öner").
_EXPLICIT_PRODUCT_TYPE_TERMS = (
    "şampuan", "sampuan",
    "saç kremi", "sac kremi",
    "saç serumu", "sac serumu",
    "saç losyonu", "sac losyonu",
    "saç toniği", "sac tonigi", "saç tonik", "sac tonik",
    "saç maskesi", "sac maskesi",
    "saç yağı", "sac yagi",
    "serum", "losyon", "tonik",
)


def _query_has_broad_intent(query):
    if not query:
        return False
    q_lower = query.lower().replace("ı", "i")
    return bool(_BROAD_INTENT_PATTERN.search(q_lower))


def _query_has_explicit_product_type_term(query):
    if not query:
        return False
    q_lower = query.lower()
    for term in _EXPLICIT_PRODUCT_TYPE_TERMS:
        if re.search(rf"\b{re.escape(term)}\b", q_lower):
            return True
    return False


def find_named_value(query, df, column_name, excluded=None):
    """Strict, inflection-aware detection of a catalog value the user LITERALLY
    named — whole-term (possibly inflected) only, with no prefix/first-word or
    "X için Y" heuristics.

    ``find_value_from_column`` is recall-oriented (it guesses "yemek" →
    "Yemek Takımı"), which is right for resolving the search category but wrong
    as a signal of explicit user intent.  This helper is the conservative
    counterpart used to gate the explicit-intent lock and pool enforcement, so a
    heuristic guess never enforces a category the user did not actually type.
    """
    for value in df[column_name].dropna().unique():
        value_text = str(value)
        if _is_excluded(value_text, excluded):
            continue
        if value_text and contains_term(query, value_text):
            return value
    return None


def _value_belongs_to(df, column, value, owner_column, owner_value):
    """True when ``value`` in ``column`` co-occurs with ``owner_value`` in
    ``owner_column`` somewhere in the catalog (e.g. product_type "Abiye" lives
    under sub_category "Elbise")."""
    rows = df[df[column].astype(str).str.lower() == str(value).lower()]
    if rows.empty:
        return False
    owners = {str(v).lower() for v in rows[owner_column].dropna().unique()}
    return str(owner_value).lower() in owners


def _lock_explicit_intent(taxonomy_match, df,
                          explicit_main, explicit_sub, explicit_product_type):
    """Drop a taxonomy match that would override an explicit positive intent.

    The taxonomy matcher keys off the whole query, so seasonal/warmth modifiers
    ("kışlık", "sıcak tutan") can make it land on outerwear even when the user
    explicitly asked for a dress.  When the user named a concrete
    product_type / sub_category / main_category, a taxonomy match on a DIFFERENT
    category for the same axis is suppressed.  Matches consistent with the
    explicit intent (a narrower product_type within the explicit sub, or the
    same value) are preserved so legitimate refinement still works.
    """
    if taxonomy_match is None:
        return None

    field = taxonomy_match.get("field")
    value = taxonomy_match.get("value")

    if field == "main_category" and explicit_main is not None:
        if str(value).lower() != str(explicit_main).lower():
            return None

    if field == "sub_category":
        # A sub_category taxonomy match must agree with an explicit sub, and
        # must stay inside an explicit main_category if one was given.
        if explicit_sub is not None and str(value).lower() != str(explicit_sub).lower():
            return None
        if (
            explicit_main is not None
            and not _value_belongs_to(df, "sub_category", value, "main_category", explicit_main)
        ):
            return None

    if field == "product_type":
        # A product_type taxonomy match must agree with an explicit product_type,
        # and must live within an explicit sub_category / main_category.
        if explicit_product_type is not None and str(value).lower() != str(explicit_product_type).lower():
            return None
        if (
            explicit_sub is not None
            and not _value_belongs_to(df, "product_type", value, "sub_category", explicit_sub)
        ):
            return None
        if (
            explicit_main is not None
            and not _value_belongs_to(df, "product_type", value, "main_category", explicit_main)
        ):
            return None

    return taxonomy_match


def parse_query(query, df, model, taxonomy_embeddings, taxonomy_records, taxonomy_match_threshold=DEFAULT_TAXONOMY_MATCH_THRESHOLD, original_query=None):
    min_price, max_price = extract_price_range(query)

    # Fast-path: an implicit charge-depletion complaint ("şarjım dışarıda
    # bitiyor") is a power-bank request.  We pin it to the Powerbank product_type
    # BEFORE the taxonomy matcher runs, because "şarj" otherwise lands on
    # "Araç Şarj Cihazı" and the original-query fallback in main.py would then
    # override the correct normalized parse with car chargers.  Checked on both
    # the (possibly normalized) query and the user's original words so it fires
    # even with Ollama disabled.
    if is_power_depletion_complaint(query) or (
        original_query and is_power_depletion_complaint(original_query)
    ):
        return {
            "min_price": min_price,
            "max_price": max_price,
            "main_category": "Elektronik",
            "sub_category": None,
            "product_type": "Powerbank",
            "target_group": None,
            "features": extract_features(query),
            "contexts": extract_contexts(query),
            "taxonomy_match": None,
            "excluded_terms": [],
            "explicit_intent": {
                "main_category": None,
                "sub_category": None,
                "product_type": None,
            },
        }

    # Fast-path: adult hair-/skin-care intent → Kişisel Bakım.  Pinned here, before
    # the generic word "bakım" can match Anne & Bebek › Bakım and drag a verb-form
    # complaint ("saçlarım dökülüyor", "cildim kuru") into baby products.  An
    # explicitly named product form is kept; otherwise the search layer picks it.
    folded_query = normalize_text_for_match(query)
    folded_original = normalize_text_for_match(original_query) if original_query else ""
    if is_hair_care_request(query) or (original_query and is_hair_care_request(original_query)):
        product_type = _hair_product_type(folded_query) or _hair_product_type(folded_original)
        return {
            "min_price": min_price,
            "max_price": max_price,
            "main_category": "Kişisel Bakım",
            "sub_category": "Saç Bakımı",
            "product_type": product_type,
            "target_group": None,
            "features": extract_features(query),
            "contexts": extract_contexts(query),
            "taxonomy_match": None,
            "excluded_terms": [],
            "explicit_intent": {
                "main_category": None,
                "sub_category": None,
                "product_type": None,
            },
        }
    if is_skin_care_request(query) or (original_query and is_skin_care_request(original_query)):
        product_type = _skin_product_type(folded_query) or _skin_product_type(folded_original)
        return {
            "min_price": min_price,
            "max_price": max_price,
            "main_category": "Kişisel Bakım",
            "sub_category": "Cilt Bakımı",
            "product_type": product_type,
            "target_group": None,
            "features": extract_features(query),
            "contexts": extract_contexts(query),
            "taxonomy_match": None,
            "excluded_terms": [],
            "explicit_intent": {
                "main_category": None,
                "sub_category": None,
                "product_type": None,
            },
        }

    # Fast-path: yoga/pilates MAT request → Spor › Yoga (product_type "Yoga Matı").
    if is_yoga_mat_request(query) or (original_query and is_yoga_mat_request(original_query)):
        return {
            "min_price": min_price,
            "max_price": max_price,
            "main_category": "Spor",
            "sub_category": "Yoga",
            "product_type": "Yoga Matı",
            "target_group": None,
            "features": extract_features(query),
            "contexts": extract_contexts(query),
            "taxonomy_match": None,
            "excluded_terms": [],
            "explicit_intent": {
                "main_category": None,
                "sub_category": None,
                "product_type": None,
            },
        }

    # Fast-path: camp-cooking request → Kamp › Pişirme.  A named stove ("ocak")
    # pins the product_type; otherwise the search layer picks within Pişirme.
    if is_camp_cooking_request(query) or (original_query and is_camp_cooking_request(original_query)):
        product_type = "Kamp Ocağı" if ("ocak" in folded_query or "ocak" in folded_original) else None
        return {
            "min_price": min_price,
            "max_price": max_price,
            "main_category": "Kamp",
            "sub_category": "Pişirme",
            "product_type": product_type,
            "target_group": None,
            "features": extract_features(query),
            "contexts": extract_contexts(query),
            "taxonomy_match": None,
            "excluded_terms": [],
            "explicit_intent": {
                "main_category": None,
                "sub_category": None,
                "product_type": None,
            },
        }

    # Negative product-type/category constraints ("mont veya kaban değil").
    # Detected from the user's literal words (both the original and the
    # possibly-normalized query) so rejected terms are never mistaken for the
    # desired intent, even when Ollama drops the negation.
    excluded_terms = extract_excluded_terms(query, df)
    if original_query and original_query != query:
        excluded_terms = excluded_terms | extract_excluded_terms(original_query, df)

    # Explicit positive product/category intent is detected from BOTH the
    # (possibly Ollama-normalized) query and the user's ORIGINAL words, because
    # either form can carry the term the user actually typed — and Ollama may
    # inflect or paraphrase it ("elbisesi" / "elbiseleri").  Inflection-aware
    # matching (contains_term) catches those forms so the explicit intent is
    # never lost to a modifier-driven taxonomy match below.
    def _explicit(column):
        value = find_value_from_column(query, df, column, excluded=excluded_terms)
        if value is None and original_query and original_query != query:
            value = find_value_from_column(original_query, df, column, excluded=excluded_terms)
        return value

    explicit_main_category = extract_explicit_main_category(query, df, excluded=excluded_terms)
    if explicit_main_category is None and original_query and original_query != query:
        explicit_main_category = extract_explicit_main_category(
            original_query, df, excluded=excluded_terms
        )

    taxonomy_match = semantic_taxonomy_match(
        query,
        model,
        taxonomy_embeddings,
        taxonomy_records,
        taxonomy_match_threshold=taxonomy_match_threshold,
    )

    # A taxonomy match that lands on an explicitly rejected category must not
    # re-introduce the excluded intent through the back door.
    if taxonomy_match is not None and _is_excluded(taxonomy_match.get("value"), excluded_terms):
        taxonomy_match = None

    explicit_sub_category = _explicit("sub_category")
    explicit_product_type = _explicit("product_type")

    if " için " in query.lower():
        parts = query.lower().split(" için ", 1)
        if len(parts) == 2:
            y_part = parts[1].strip()
            y_type = find_value_from_column(y_part, df, "product_type", excluded=excluded_terms)
            if y_type:
                explicit_product_type = y_type

    # Strict "did the user literally name it?" signal (no prefix/için guesses),
    # used for the explicit-intent lock and downstream pool enforcement.  This
    # reads the user's ORIGINAL words, never the Ollama-normalized query, so a
    # normalizer expansion ("kamp için ürün öner" → "... kamp ocağı") cannot
    # forge an explicit intent and wrongly narrow a broad browse.
    intent_source = original_query if original_query else query

    def _named(column):
        return find_named_value(intent_source, df, column, excluded=excluded_terms)

    named_sub_category = _named("sub_category")
    named_product_type = _named("product_type")

    # ----- Explicit positive intent lock -----
    # When the user explicitly named a product_type / sub_category / main_category
    # (even inflected), a modifier-driven taxonomy match (e.g. "kışlık, sıcak
    # tutan" → sub_category "Mont") must NOT replace that explicit category with
    # a DIFFERENT one.  Modifiers may only refine ranking within the explicit
    # pool, never switch it.  A taxonomy match that AGREES with the explicit
    # intent (e.g. product_type "Abiye" inside the explicit "Elbise" sub) is
    # kept, so legitimate narrowing still works.
    taxonomy_match = _lock_explicit_intent(
        taxonomy_match, df,
        explicit_main_category, named_sub_category, named_product_type,
    )

    # Yazlık / kışlık gibi ifadeler bazı ürünlerde product_type olabilir,
    # ama ayakkabı gibi kategorilerde mevsim/özellik olarak kalmalıdır.
    seasonal_product_types = ["Yazlık", "Kışlık"]

    if explicit_product_type in seasonal_product_types:
        # Sadece Elbise gibi ürünlerde Yazlık/Abiye benzeri product_type kullanılsın.
        # Örnek: "kadın yazlık elbise" -> product_type Yazlık olabilir.
        # Örnek: "yazlık erkek ayakkabı" -> product_type Yazlık olmamalı.
        if explicit_sub_category != "Elbise":
            explicit_product_type = None
    
    # Target group: the literal value in the query, else "Çocuk" when the query
    # clearly describes shopping for a child ("oğlum yeni yürümeye başladı") even
    # though no literal "çocuk" token is present.
    target_group = find_value_from_column(query, df, "target_group")
    if target_group is None and (
        has_child_shopper_context(query)
        or (original_query and has_child_shopper_context(original_query))
    ):
        target_group = "Çocuk"

    parsed = {
        "min_price": min_price,
        "max_price": max_price,
        "main_category": explicit_main_category,
        "sub_category": explicit_sub_category,
        "product_type": explicit_product_type,
        "target_group": target_group,
        "features": extract_features(query),
        "contexts": extract_contexts(query),
        "taxonomy_match": taxonomy_match,
        "excluded_terms": sorted(excluded_terms),
        # The user-typed positive intent (inflection-aware), captured BEFORE any
        # taxonomy/alias/context inference fills the fields. Downstream uses this
        # to enforce the explicit category pool so modifiers/features only refine
        # ranking inside it and never switch the product type/category.
        "explicit_intent": {
            "main_category": explicit_main_category,
            "sub_category": named_sub_category,
            "product_type": named_product_type,
        },
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

    # Broad query check: if the user used truly-broad words ("ürün", "malzeme",
    # "eşya", "şey", "ne kullanabilirim") AND didn't explicitly name a product
    # type (e.g. "şampuan", "saç kremi", "serum"), remove the taxonomy-inferred
    # product_type to keep the search broad.
    #
    # We check the *original* user query (not the Ollama-normalized one) for
    # both signals.  The normalizer often expands a brief "ürün öner" into a
    # richer phrase like "saç bakım ürünü" — and "bakım" alone happens to
    # match the "Bakım" sub_category (Anne & Bebek / Otomotiv).  Reading the
    # normalized query for the broad/explicit decision lets that expansion
    # silently flip a broad request ("saç dökülmesi için ürün öner") into a
    # focused 5/5-Şampuan result.
    if explicit_product_type is None and parsed.get("product_type") is not None:
        intent_query = original_query if original_query else query

        if (
            _query_has_broad_intent(intent_query)
            and not _query_has_explicit_product_type_term(intent_query)
        ):
            # Local import to avoid load-order coupling; both modules
            # are already imported together by main.py.
            from response_planner import extract_user_problem
            user_problem = extract_user_problem(intent_query)
            parsed["product_type"] = None
            # Keep the inferred sub_category when the user named a
            # specific problem (e.g. "saç dökülmesi") so results stay
            # constrained to the relevant care area instead of broadening
            # to the entire main_category.
            if explicit_sub_category is None and user_problem is None:
                parsed["sub_category"] = None

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

    # Sub-category is a fairly specific signal. On the current catalog
    # having 2-5 products per sub-category is normal; only ask for
    # clarification when there are enough variants to make choice meaningful.
    if has_sub_category and not has_product_type:
        return matching_product_count > 5

    # Product type is already a strong, specific signal. Only ask for
    # clarification when there are many variants of the same type and
    # no other discriminating context (price, features, target group) is given.
    # Threshold tuned for the current catalog where 5-10 items per type is normal.
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

def _most_common_category(series):
    """Return the most frequent value in ``series`` with a deterministic,
    row-order-independent tie-break (alphabetical).

    Several product_types/sub_categories span more than one main_category
    in the catalog (e.g. "Tencere Seti" → {Kamp, Mutfak}).  When counts tie,
    we must pick the same value regardless of DataFrame row order, otherwise
    a DB migration that returns rows in a different order could silently
    change parse results.  ``Series.mode()`` already sorts ascending, but we
    make the guarantee explicit here rather than rely on that behaviour.
    """
    counts = series.dropna().value_counts()
    if counts.empty:
        return None
    top_count = counts.max()
    tied = sorted(str(value) for value, count in counts.items() if count == top_count)
    return tied[0]


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
            return _most_common_category(matched_rows["main_category"])

    if product_type is not None:
        matched_rows = df[
            df["product_type"].astype(str).str.lower() == str(product_type).lower()
        ]

        if not matched_rows.empty:
            return _most_common_category(matched_rows["main_category"])

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

    # An explicit main-category term the user literally typed (e.g. "ayakkabı")
    # must outrank a context word that maps elsewhere (e.g. "koşu" → Spor).
    explicit_main_category = extract_explicit_main_category(query, df)

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
            correct_main_category = _most_common_category(matched_rows["main_category"])
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
    # Ancak kullanıcı açıkça farklı bir ana kategori yazdıysa (örn. "ayakkabı"),
    # bağlam kelimesi ("koşu" -> Spor) onu ezmemeli; açık terim önceliklidir.
    if context_main_category is not None and (
        explicit_main_category is None
        or explicit_main_category == context_main_category
    ):
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
            # Kullanıcı ana kategoriyi açıkça yazdıysa, başka bir kategoriye ait
            # sub_category onu değiştirmemeli; uyumsuz sub_category'yi düşür.
            # Örnek: "koşu için ayakkabı" -> main Ayakkabı kalır, sub Koşu düşer.
            if (
                explicit_main_category is not None
                and str(explicit_main_category).lower()
                == str(parsed_query["main_category"]).lower()
            ):
                parsed_query["sub_category"] = None
                return parsed_query

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