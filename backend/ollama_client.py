"""
Low-level HTTP client for the Ollama /api/generate endpoint.

Design principles
-----------------
* Return ``None`` on **any** failure (timeout, connection refused, bad JSON …).
  The caller is responsible for falling back to non-Ollama behaviour.
* Log warnings so problems are visible but never let Ollama break the API.
* Keep the interface minimal: one public function ``call_ollama``.
"""

import json
import logging
import re

import httpx

from config import (
    OLLAMA_BASE_URL,
    OLLAMA_ENABLED,
    OLLAMA_MODEL,
    OLLAMA_TIMEOUT_SECONDS,
    OLLAMA_KEEP_ALIVE,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# JSON extraction helpers
# ---------------------------------------------------------------------------

def _extract_json_from_text(text: str) -> dict | None:
    """
    Try to parse *text* as JSON.  If that fails, look for a fenced
    ``json`` code-block (Ollama sometimes wraps its answer) and parse
    that instead.  Returns ``None`` when nothing works.
    """
    text = text.strip()

    # 1. Straight parse
    try:
        return json.loads(text)
    except (json.JSONDecodeError, ValueError):
        pass

    # 2. Fenced code-block: ```json ... ```  or  ``` ... ```
    match = re.search(r"```(?:json)?\s*\n?(.*?)```", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1).strip())
        except (json.JSONDecodeError, ValueError):
            pass

    # 3. First { … } block (greedy)
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(0))
        except (json.JSONDecodeError, ValueError):
            pass

    return None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def call_ollama(prompt: str, system_prompt: str) -> dict | None:
    """
    Send *prompt* to the configured Ollama model and return the parsed
    JSON dict, or ``None`` when anything goes wrong.

    Parameters
    ----------
    prompt : str
        The user-facing prompt (will be placed in the ``"prompt"`` field).
    system_prompt : str
        Instruction text for the model (``"system"`` field).

    Returns
    -------
    dict | None
        Parsed JSON from the model response, or ``None`` on failure.
    """
    if not OLLAMA_ENABLED:
        logger.debug("Ollama is disabled via configuration.")
        return None

    url = f"{OLLAMA_BASE_URL.rstrip('/')}/api/generate"

    payload = {
        "model": OLLAMA_MODEL,
        "prompt": prompt,
        "system": system_prompt,
        "stream": False,
        # Constrain the model to emit a syntactically valid JSON object. Every
        # caller parses JSON, and small models (e.g. gemma3:4b) otherwise drop
        # the JSON envelope and reply in free-form prose as the prompt grows,
        # which then fails parsing and forces a template fallback. This decouples
        # output-format reliability from prompt length/complexity.
        "format": "json",
        # Keep the model resident in VRAM between requests so an idle gap does
        # not trigger a slow re-load on the next query.
        "keep_alive": OLLAMA_KEEP_ALIVE,
        "options": {
            "temperature": 0.3,
            "num_predict": 512,
        },
    }

    try:
        response = httpx.post(
            url,
            json=payload,
            timeout=OLLAMA_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
    except httpx.TimeoutException:
        logger.warning("Ollama request timed out after %ss.", OLLAMA_TIMEOUT_SECONDS)
        return None
    except httpx.ConnectError:
        logger.warning("Could not connect to Ollama at %s.", url)
        return None
    except httpx.HTTPStatusError as exc:
        logger.warning("Ollama returned HTTP %s: %s", exc.response.status_code, exc.response.text[:200])
        return None
    except Exception:
        logger.warning("Unexpected error calling Ollama.", exc_info=True)
        return None

    # Ollama returns {"response": "<model text>", ...}
    try:
        raw_body = response.json()
    except (json.JSONDecodeError, ValueError):
        logger.warning("Ollama returned non-JSON HTTP body.")
        return None

    model_text = raw_body.get("response", "")
    if not model_text:
        logger.warning("Ollama returned an empty 'response' field.")
        return None

    parsed = _extract_json_from_text(model_text)
    if parsed is None:
        logger.warning("Could not extract valid JSON from Ollama response: %.300s", model_text)

    return parsed


def warm_up_model() -> bool:
    """Load the model into VRAM ahead of the first user query.

    Sends a tiny generate request so Ollama resolves and resident-loads the
    model. The first query a user sends would otherwise pay this cold-load cost,
    which exceeds OLLAMA_TIMEOUT_SECONDS and degrades to a template answer.

    Safe to call from a background thread at startup: never raises, returns True
    on success and False on any error (Ollama down, model missing, timeout).
    A generous fixed timeout is used because a cold load can take far longer
    than the per-request OLLAMA_TIMEOUT_SECONDS.
    """
    if not OLLAMA_ENABLED:
        return False

    url = f"{OLLAMA_BASE_URL.rstrip('/')}/api/generate"
    payload = {
        "model": OLLAMA_MODEL,
        "prompt": "merhaba",
        "stream": False,
        "keep_alive": OLLAMA_KEEP_ALIVE,
        "options": {"num_predict": 1},
    }
    try:
        response = httpx.post(url, json=payload, timeout=180)
        response.raise_for_status()
    except Exception as exc:  # noqa: BLE001 — warm-up must never break startup
        logger.warning("Ollama warm-up failed (%s); first query may be slow.", exc)
        return False

    logger.info("Ollama model '%s' warmed up and resident.", OLLAMA_MODEL)
    return True
