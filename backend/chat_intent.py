"""
Chat intent router for AI-Market chatbot.

Classifies user messages into conversational intents **before** the
query normalizer / search pipeline runs.  Simple intents like greetings,
thanks, and goodbye are answered instantly without touching the search
engine.

Design
------
* Deterministic keyword/regex checks first — instant, no Ollama round-trip.
* Only falls through to Ollama when the message is ambiguous.
* Never chooses, ranks, or invents products.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass

from ollama_client import call_ollama

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Intent enum (plain strings for JSON serialisation)
# ---------------------------------------------------------------------------

INTENT_GREETING = "greeting"
INTENT_HELP = "help"
INTENT_THANKS = "thanks"
INTENT_GOODBYE = "goodbye"
INTENT_WELLBEING = "wellbeing"
INTENT_PRODUCT_SEARCH = "product_search"
INTENT_CLARIFICATION_FOLLOWUP = "clarification_followup"
INTENT_NONSENSE = "nonsense"


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------

@dataclass
class IntentResult:
    intent: str
    response: str | None = None   # Pre-built answer for non-search intents
    confidence: float = 1.0
    method: str = "rules"         # "rules" or "ollama"


# ---------------------------------------------------------------------------
# Keyword / pattern tables
# ---------------------------------------------------------------------------

# Each list is checked with _matches_any().  Patterns are matched as
# whole-word substrings against the lowered, stripped message.

_GREETING_EXACT = {
    "merhaba", "selam", "selamlar", "hey", "hi", "hello",
    "meraba", "mrb", "slm", "sa", "selamun aleyküm",
    "selamün aleyküm", "günaydın", "iyi akşamlar",
    "iyi günler", "iyi geceler", "hayırlı günler",
}

_GREETING_PATTERNS: list[re.Pattern] = [
    re.compile(r"\b(merhaba|selam|meraba|hey|hi|hello)\b", re.IGNORECASE),
]

_HELP_PATTERNS: list[re.Pattern] = [
    re.compile(r"\bne\s+yapabilirsin\b", re.IGNORECASE),
    re.compile(r"\bneler\s+yapabilirsin\b", re.IGNORECASE),
    re.compile(r"\bne\s+yapıyorsun\b", re.IGNORECASE),
    re.compile(r"\bnasıl\s+çalışıyorsun\b", re.IGNORECASE),
    re.compile(r"\bnasıl\s+yardımcı\s+olabilirsin\b", re.IGNORECASE),
    re.compile(r"\bne\s+iş\s+yapıyorsun\b", re.IGNORECASE),
    re.compile(r"\byardım\b", re.IGNORECASE),
    re.compile(r"\bhelp\b", re.IGNORECASE),
    re.compile(r"\bsen\s+kimsin\b", re.IGNORECASE),
    re.compile(r"\bsen\s+nesin\b", re.IGNORECASE),
    re.compile(r"\bne\s+önerebilirsin\b", re.IGNORECASE),
    re.compile(r"\bne\s+biliyorsun\b", re.IGNORECASE),
    re.compile(r"\bnasıl\s+kullanırım\b", re.IGNORECASE),
]

_THANKS_EXACT = {
    "teşekkürler", "teşekkür ederim", "tesekkurler", "tesekkür ederim",
    "sağ ol", "sağol", "sagol", "sag ol", "eyvallah",
    "eyv", "tşk", "tsk", "thanks", "thank you", "thx",
    "çok teşekkürler", "çok sağ ol",
}

_THANKS_PATTERNS: list[re.Pattern] = [
    re.compile(r"\b(teşekkür|tesekkur|sağ\s*ol|sagol|eyvallah)\b", re.IGNORECASE),
]

_GOODBYE_EXACT = {
    "görüşürüz", "gorusuruz", "hoşça kal", "hosca kal",
    "güle güle", "gule gule", "bye", "bb", "bay bay",
    "iyi geceler", "kendine iyi bak",
    "hoşçakal", "hoscakal",
}

_GOODBYE_PATTERNS: list[re.Pattern] = [
    re.compile(r"\b(görüşürüz|gorusuruz|hoşça\s*kal|hosca\s*kal|güle\s*güle|gule\s*gule|bye|bay\s*bay)\b", re.IGNORECASE),
]

_WELLBEING_EXACT = {
    "nasılsın", "nasilsin", "iyi misin", "naber", "nbr",
    "ne haber", "keyfin nasıl", "napıyorsun", "napiyorsun",
    "ne yapıyorsun", "ne yapiyorsun",
}

_WELLBEING_PATTERNS: list[re.Pattern] = [
    re.compile(r"\b(nasılsın|nasilsin|iyi\s*misin|naber|ne\s*haber|keyfin\s*nasıl|napıyorsun|napiyorsun)\b", re.IGNORECASE),
]

# Words that strongly signal a product search — used to reject false
# positives when a greeting/thanks word co-occurs with product intent.
_PRODUCT_SIGNAL_PATTERNS: list[re.Pattern] = [
    re.compile(r"\d+\s*(tl|lira)", re.IGNORECASE),
    re.compile(r"\b(lazım|lazim|arıyorum|ariyorum|istiyorum|öner|oner|bakıyorum|bakiyorum)\b", re.IGNORECASE),
    re.compile(r"\b(ayakkabı|ayakkabi|şampuan|sampuan|telefon|laptop|kulaklık|kulaklik)\b", re.IGNORECASE),
    re.compile(r"\b(kamp|spor|elektronik|giyim|mutfak|powerbank)\b", re.IGNORECASE),
    re.compile(r"\b(kadın|kadin|erkek|çocuk|cocuk|unisex)\b", re.IGNORECASE),
    re.compile(r"\b(altında|altinda|üstünde|ustunde|arasında|arasinda|civarı|civarinda)\b", re.IGNORECASE),
    re.compile(r"\b(için|icin|ürün|urun|ürünler|urunler)\b", re.IGNORECASE),
]


# ---------------------------------------------------------------------------
# Response templates
# ---------------------------------------------------------------------------

GREETING_RESPONSES = [
    "Merhaba! 👋 Ben AI-Market alışveriş asistanı. Bana doğal dille ne aradığını yazabilirsin. "
    "Örneğin \"1500 TL altında erkek ayakkabı\" veya \"yağlı saç için şampuan\" gibi.",
]

HELP_RESPONSES = [
    "Ürün, kategori, fiyat aralığı veya kullanım amacına göre öneri yapabilirim. 🛍️\n\n"
    "Örnek aramalar:\n"
    "• \"1500 TL altında erkek ayakkabı\"\n"
    "• \"yağlı saç için şampuan\"\n"
    "• \"kamp için uyku tulumu\"\n"
    "• \"çocuk akıllı saat\"\n"
    "• \"araç şarj cihazı\"\n\n"
    "Doğal dille yazmandan anlıyorum, merak etme! 😊",
]

THANKS_RESPONSES = [
    "Rica ederim! 😊 Başka bir ürün aramak istersen buradayım.",
]

GOODBYE_RESPONSES = [
    "Görüşmek üzere! 👋 İyi alışverişler dilerim.",
]

WELLBEING_RESPONSES = [
    "İyiyim, teşekkür ederim 😊 Sana ürün bulma konusunda yardımcı olmaya hazırım. Ne arıyorsun?",
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _has_product_signal(text: str) -> bool:
    """Return True if the message contains words that indicate product intent."""
    return any(p.search(text) for p in _PRODUCT_SIGNAL_PATTERNS)


def _matches_exact(text: str, exact_set: set[str]) -> bool:
    return text.lower().strip() in exact_set


def _matches_pattern(text: str, patterns: list[re.Pattern]) -> bool:
    return any(p.search(text) for p in patterns)


# ---------------------------------------------------------------------------
# Ollama fallback intent classifier
# ---------------------------------------------------------------------------

_INTENT_CLASSIFIER_PROMPT = """\
Kullanıcının mesajını aşağıdaki kategorilerden birine sınıfla.

Kategoriler:
- greeting: Selamlama (merhaba, selam vb.)
- help: Ne yapabilirsin, nasıl çalışıyorsun, yardım vb.
- thanks: Teşekkür (teşekkürler, sağ ol vb.)
- goodbye: Vedalaşma (görüşürüz, hoşça kal vb.)
- wellbeing: Hal hatır sorma (nasılsın, iyi misin, naber vb.)
- product_search: Ürün arama niyeti var (herhangi bir ürün, fiyat, kategori, ihtiyaç belirtilmiş)
- nonsense: Anlamsız, alakasız veya sınıflandırılamayan mesaj

Yalnızca geçerli JSON döndür:
{"intent": "...", "confidence": 0.0-1.0}
"""


def _classify_with_ollama(text: str) -> IntentResult | None:
    """Use Ollama as a fallback intent classifier. Returns None on failure."""
    data = call_ollama(
        prompt=f'Kullanıcı mesajı: "{text}"',
        system_prompt=_INTENT_CLASSIFIER_PROMPT,
    )

    if data is None:
        return None

    intent = str(data.get("intent", "")).strip().lower()
    confidence = 0.0
    try:
        confidence = float(data.get("confidence", 0.0))
    except (TypeError, ValueError):
        confidence = 0.0

    valid_intents = {
        INTENT_GREETING, INTENT_HELP, INTENT_THANKS,
        INTENT_GOODBYE, INTENT_WELLBEING, INTENT_PRODUCT_SEARCH, INTENT_NONSENSE,
    }

    if intent not in valid_intents:
        return None

    # Map to response
    response = None
    if intent == INTENT_GREETING:
        response = GREETING_RESPONSES[0]
    elif intent == INTENT_HELP:
        response = HELP_RESPONSES[0]
    elif intent == INTENT_THANKS:
        response = THANKS_RESPONSES[0]
    elif intent == INTENT_GOODBYE:
        response = GOODBYE_RESPONSES[0]
    elif intent == INTENT_WELLBEING:
        response = WELLBEING_RESPONSES[0]

    return IntentResult(
        intent=intent,
        response=response,
        confidence=confidence,
        method="ollama",
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def classify_intent(message: str, has_pending_clarification: bool = False) -> IntentResult:
    """
    Classify *message* into a chat intent.

    Fast deterministic rules run first.  Ollama is only consulted when
    the message is short and ambiguous (no clear product signal, no
    keyword match).

    Parameters
    ----------
    message : str
        Raw user message.
    has_pending_clarification : bool
        Whether the session is waiting for a follow-up answer.

    Returns
    -------
    IntentResult
        The detected intent plus an optional pre-built response.
    """
    text = message.strip()

    if not text:
        return IntentResult(intent=INTENT_NONSENSE, response=None)

    text_lower = text.lower().strip()
    has_product = _has_product_signal(text)

    # ---- Short-circuit: if message has product signals, skip chat intents ----
    # e.g. "merhaba, ayakkabı arıyorum" should go to search
    if has_product:
        return IntentResult(intent=INTENT_PRODUCT_SEARCH)

    # ---- If there is a pending clarification, short messages are follow-ups ----
    if has_pending_clarification:
        word_count = len(text.split())
        if word_count <= 5:
            return IntentResult(intent=INTENT_CLARIFICATION_FOLLOWUP)

    # ---- Deterministic keyword checks (order: most common first) ----
    if _matches_exact(text_lower, _GREETING_EXACT) or (
        len(text_lower.split()) <= 4 and _matches_pattern(text, _GREETING_PATTERNS)
    ):
        return IntentResult(intent=INTENT_GREETING, response=GREETING_RESPONSES[0])

    if _matches_pattern(text, _HELP_PATTERNS):
        return IntentResult(intent=INTENT_HELP, response=HELP_RESPONSES[0])

    if _matches_exact(text_lower, _THANKS_EXACT) or (
        len(text_lower.split()) <= 4 and _matches_pattern(text, _THANKS_PATTERNS)
    ):
        return IntentResult(intent=INTENT_THANKS, response=THANKS_RESPONSES[0])

    if _matches_exact(text_lower, _GOODBYE_EXACT) or (
        len(text_lower.split()) <= 4 and _matches_pattern(text, _GOODBYE_PATTERNS)
    ):
        return IntentResult(intent=INTENT_GOODBYE, response=GOODBYE_RESPONSES[0])

    if _matches_exact(text_lower, _WELLBEING_EXACT) or (
        len(text_lower.split()) <= 4 and _matches_pattern(text, _WELLBEING_PATTERNS)
    ):
        return IntentResult(intent=INTENT_WELLBEING, response=WELLBEING_RESPONSES[0])

    # ---- Short ambiguous messages: try Ollama only for very short input ----
    # Messages of 3+ words that didn't match any chat pattern are very likely
    # implicit product requests (e.g. "şarjım dışarıda bitiyor") — send them
    # straight to the search pipeline rather than risking Ollama misclassification.
    word_count = len(text.split())
    if word_count <= 2 and not has_product:
        ollama_result = _classify_with_ollama(text)
        if ollama_result is not None and ollama_result.confidence >= 0.7:
            logger.info(
                "Intent router (Ollama): '%s' → %s (%.2f)",
                text, ollama_result.intent, ollama_result.confidence,
            )
            return ollama_result

    # ---- Default: assume product search ----
    return IntentResult(intent=INTENT_PRODUCT_SEARCH)

