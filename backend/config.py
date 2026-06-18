import os
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parent


def _get_env_str(name: str, default: str) -> str:
    value = os.getenv(name, "").strip()
    return value or default


def _get_env_int(name: str, default: int, minimum: int = 1) -> int:
    raw_value = os.getenv(name)
    if raw_value is None:
        return default

    try:
        parsed = int(raw_value)
    except ValueError:
        return default

    return max(minimum, parsed)


def _get_env_float(name: str, default: float, minimum: float = 0.0, maximum: float = 1.0) -> float:
    raw_value = os.getenv(name)
    if raw_value is None:
        return default

    try:
        parsed = float(raw_value)
    except ValueError:
        return default

    return max(minimum, min(maximum, parsed))


def _resolve_data_path(env_key: str, default_file_name: str) -> Path:
    configured_value = _get_env_str(env_key, default_file_name)
    configured_path = Path(configured_value)

    if configured_path.is_absolute():
        return configured_path

    return (BACKEND_DIR / configured_path).resolve()


def _resolve_model_name_or_path() -> str:
    configured_value = _get_env_str("AI_MARKET_MODEL_NAME", "paraphrase-multilingual-MiniLM-L12-v2")
    configured_path = Path(configured_value)

    if configured_path.is_absolute():
        return str(configured_path)

    local_candidate = (BACKEND_DIR / configured_path).resolve()
    if local_candidate.exists():
        return str(local_candidate)

    return configured_value


MODEL_NAME_OR_PATH = _resolve_model_name_or_path()
TAXONOMY_CSV_PATH = _resolve_data_path("AI_MARKET_TAXONOMY_CSV", "taxonomy.csv")

SEARCH_TOP_K = _get_env_int("AI_MARKET_TOP_K", 5, minimum=1)
TAXONOMY_MATCH_THRESHOLD = _get_env_float("AI_MARKET_TAXONOMY_MATCH_THRESHOLD", 0.65)

# ---- Core ranking (Stage 2) ----
# When enabled, the final search results are re-ordered by a directness tier
# (DIRECT > RELATED > OTHER) before the blended score, so direct-intent matches
# lead. Enabled by default after live validation (Stage 3) and CI regression
# locks (tests/test_ranking_v2_regression.py). Set AI_MARKET_RANKING_V2=false to
# fall back to the legacy diversify/head ordering. See
# ranking_core.finalize_ranking_v2 and the embedding/order contract note in
# data_loader (tiering reorders FINAL results only; it never reorders the source
# DataFrame or its embeddings).
RANKING_V2_ENABLED = _get_env_str("AI_MARKET_RANKING_V2", "true").lower() in ("true", "1", "yes")

# ---- Primary/alternative grouping ----
# When enabled, each result is labeled with a match_group ("primary" |
# "alternative") derived from the V2 directness tier, plus a result_grouping
# ("primary_alternative" | "flat"); the response also exposes grouped views
# (primary_products / alternative_products).  The products list itself stays
# primary-first and backward-compatible, so older clients are unaffected.
# Enabled by default now that Stage 6-8 validation passed; set false to fall
# back to the ungrouped response. See ranking_core.determine_result_grouping.
GROUPED_RANKING_ENABLED = _get_env_str("AI_MARKET_GROUPED_RANKING", "true").lower() in ("true", "1", "yes")

# ---- Product catalog source ----
# PostgreSQL is the ONLY runtime product source (there is no CSV fallback).
# The catalog is loaded once at startup with ORDER BY id; see data_loader and
# database.py for the embedding/order contract.
# DATABASE_URL is a libpq connection URI accepted directly by psycopg2.connect.
# It is REQUIRED and has no default: runtime is PostgreSQL-only with no CSV
# fallback, so if it is missing/empty, load_products raises and startup stops.
# See backend/.env.example for the local docker-compose URL (host port 5433).
# PRODUCTS_TABLE lets the table name be overridden without code changes.
DATABASE_URL = _get_env_str("DATABASE_URL", "")
PRODUCTS_TABLE = _get_env_str("PRODUCTS_TABLE", "products")

# ---- Ollama configuration ----
OLLAMA_BASE_URL = _get_env_str("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_MODEL = _get_env_str("OLLAMA_MODEL", "gemma3:4b")
OLLAMA_ENABLED = _get_env_str("OLLAMA_ENABLED", "true").lower() in ("true", "1", "yes")
OLLAMA_TIMEOUT_SECONDS = _get_env_int("OLLAMA_TIMEOUT_SECONDS", 15, minimum=3)
OLLAMA_CONFIDENCE_THRESHOLD = _get_env_float(
    "OLLAMA_CONFIDENCE_THRESHOLD", 0.6, minimum=0.0, maximum=1.0
)

