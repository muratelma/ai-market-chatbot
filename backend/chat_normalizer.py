"""
Ollama-powered query normalizer for Turkish e-commerce search.

Converts informal, misspelled, colloquial, or implicit user messages into
cleaner search queries that the existing ``query_parser`` can understand
better.  Falls back to the original query whenever Ollama is unavailable
or returns low-confidence / invalid output.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from config import OLLAMA_CONFIDENCE_THRESHOLD
from ollama_client import call_ollama

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------

@dataclass
class NormalizationResult:
    """Outcome of the query-normalization step."""

    normalized_query: str
    original_query: str
    confidence: float = 0.0
    detected_synonyms: dict = field(default_factory=dict)
    needs_clarification: bool = False
    clarification_question: str | None = None
    reason: str = ""
    used: bool = False            # True when Ollama output was actually adopted
    fallback_reason: str | None = None  # Why we fell back, if we did


# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

NORMALIZER_SYSTEM_PROMPT = """\
Sen bir Türkçe e-ticaret arama sorgusu normalleştiricisisin.

## Görevin
Kullanıcının doğal, günlük dildeki mesajını alıp, bir e-ticaret katalog arama motorunun daha iyi anlayabileceği temiz bir arama sorgusuna dönüştürmek.

## Katalog alanları
Katalogda şu alanlar var: product_name, description, main_category, sub_category, target_group, product_type, features, tags, attributes, price.

## Kurallar
1. Ürün ismi UYDURMA. Sadece kullanıcının niyetini daha net ifade et.
2. Fiyat UYDURMA.
3. Stok bilgisi UYDURMA.
4. Marka UYDURMA.
5. Argo, günlük konuşma, yazım hatası ve dolaylı ifadeleri katalog/arama dostu dile çevir.
6. Eğer kullanıcının ne aradığı belirsizse, düşük confidence ver ve clarification_question yaz.
7. Eğer mesaj bir ürün aramasıyla hiç ilgili değilse (selamlama, sohbet vb.), orijinal metni aynen döndür ve confidence 1.0 yap.
8. Eğer kullanıcı spesifik bir ürün tipi (örn: saç kremi, serum, maske, vb.) belirtmişse, O ÜRÜN TİPİNİ KORU. Asla şampuan ile değiştirme veya şampuan ekleme.
9. Kullanıcı sadece bir problemden bahsedip "ürün", "ne kullanabilirim" veya "öner" diyorsa, sorguyu spesifik bir ürün tipine (örn. şampuan) daraltma. Genel bir ürün araması olarak (örn. "saç bakım ürünü") bırak.

## Normalleştirme örnekleri
- "papuç lazım" → "ayakkabı"
- "pabuç bakıyorum" → "ayakkabı"
- "şarjım dışarıda bitiyor" → "telefon için taşınabilir şarj powerbank"
- "telefonum hemen bitiyor" → "telefon için powerbank"
- "kampda yemek yapacağım" → "kamp için yemek pişirme ürünü kamp ocağı"
- "kamp için yemek yapacak şey" → "kamp ocağı veya kamp mutfak seti"
- "kafa feneri lazım" → "baş lambası kafa lambası"
- "arabada şarj" → "araç şarj cihazı"
- "çadırın içine ışık" → "çadır içi kamp lambası"
- "çocuk için saat" → "çocuk akıllı saat"
- "ev süpürsün kendi kendine" → "robot süpürge"
- "su gerektirmeyen şampuan" → "kuru şampuan"
- "yemek yapmalık kamp ürünü" → "kamp ocağı veya kamp mutfak seti"
- "saç kremi arıyorum" → "saç kremi arıyorum"
- "saç dökülmesi için saç kremi arıyorum" → "saç dökülmesi saç kremi"
- "saç dökülmesi problemi için ürün arıyorum" → "saç dökülmesi için saç bakım ürünü"
- "saç dökülmesine iyi gelen ürün öner" → "saç dökülmesi için saç bakım ürünü"
- "saç dökülmesi için ne kullanabilirim" → "saç dökülmesi için saç bakım ürünü"
- "saçım hemen yağlanıyor" → "yağlı saç için şampuan veya bakım ürünü"
- "kepek var" → "kepek karşıtı şampuan veya bakım ürünü"

## Yanıt formatı
Yalnızca geçerli JSON döndür, başka bir şey yazma.

{
  "normalized_query": "...",
  "confidence": 0.0-1.0,
  "detected_synonyms": {"orijinal ifade": "normalleştirilmiş ifade"},
  "needs_clarification": true/false,
  "clarification_question": "..." veya null,
  "reason": "Kısa açıklama"
}
"""


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def normalize_query(user_message: str) -> NormalizationResult:
    """
    Normalize *user_message* via Ollama.

    Returns a ``NormalizationResult`` that always contains a usable
    ``normalized_query`` (worst case: the original message itself).
    """
    original = user_message.strip()

    if not original:
        return NormalizationResult(
            normalized_query=original,
            original_query=original,
            fallback_reason="empty_query",
        )

    prompt = f'Kullanıcı mesajı: "{original}"'

    data = call_ollama(prompt, NORMALIZER_SYSTEM_PROMPT)

    if data is None:
        logger.info("Normalizer: Ollama returned no data, falling back to original query.")
        return NormalizationResult(
            normalized_query=original,
            original_query=original,
            fallback_reason="ollama_unavailable",
        )

    # ---- Extract and validate fields ----
    normalized = str(data.get("normalized_query", "")).strip()
    confidence = 0.0
    try:
        confidence = float(data.get("confidence", 0.0))
    except (TypeError, ValueError):
        confidence = 0.0

    detected_synonyms = data.get("detected_synonyms") or {}
    needs_clarification = bool(data.get("needs_clarification", False))
    clarification_question = data.get("clarification_question")
    reason = str(data.get("reason", ""))

    # Guard: if normalized_query came back empty, fall back
    if not normalized:
        return NormalizationResult(
            normalized_query=original,
            original_query=original,
            confidence=confidence,
            reason=reason,
            fallback_reason="empty_normalized_query",
        )

    # ---- Confidence threshold logic ----
    if confidence >= OLLAMA_CONFIDENCE_THRESHOLD:
        return NormalizationResult(
            normalized_query=normalized,
            original_query=original,
            confidence=confidence,
            detected_synonyms=detected_synonyms,
            needs_clarification=needs_clarification,
            clarification_question=clarification_question if needs_clarification else None,
            reason=reason,
            used=True,
        )

    # Low confidence
    if needs_clarification and clarification_question:
        return NormalizationResult(
            normalized_query=normalized,
            original_query=original,
            confidence=confidence,
            detected_synonyms=detected_synonyms,
            needs_clarification=True,
            clarification_question=clarification_question,
            reason=reason,
            used=True,
        )

    # Low confidence, no clarification → fall back to original
    logger.info(
        "Normalizer: confidence %.2f below threshold %.2f, falling back.",
        confidence,
        OLLAMA_CONFIDENCE_THRESHOLD,
    )
    return NormalizationResult(
        normalized_query=original,
        original_query=original,
        confidence=confidence,
        reason=reason,
        fallback_reason="low_confidence",
    )
