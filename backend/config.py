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
PRODUCTS_CSV_PATH = _resolve_data_path("AI_MARKET_PRODUCTS_CSV", "products.csv")
TAXONOMY_CSV_PATH = _resolve_data_path("AI_MARKET_TAXONOMY_CSV", "taxonomy.csv")

SEARCH_TOP_K = _get_env_int("AI_MARKET_TOP_K", 5, minimum=1)
TAXONOMY_MATCH_THRESHOLD = _get_env_float("AI_MARKET_TAXONOMY_MATCH_THRESHOLD", 0.65)

# ---- Product catalog source ----
# PRODUCT_SOURCE selects where the catalog is loaded from once at startup:
#   "csv" (default) -> backend/products.csv  (unchanged legacy behavior)
#   "db"            -> PostgreSQL via DATABASE_URL, loaded with ORDER BY id
# CSV stays the safe fallback: if DB loading fails, data_loader falls back to CSV.
# DATABASE_URL is a libpq connection URI accepted directly by psycopg2.connect.
# PRODUCTS_TABLE lets the table name be overridden without code changes.
PRODUCT_SOURCE = _get_env_str("PRODUCT_SOURCE", "csv").lower()
DATABASE_URL = _get_env_str(
    "DATABASE_URL",
    "postgresql://aimarket_user:aimarket_pass@localhost:5433/aimarket",
)
PRODUCTS_TABLE = _get_env_str("PRODUCTS_TABLE", "products")

# ---- Ollama configuration ----
OLLAMA_BASE_URL = _get_env_str("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_MODEL = _get_env_str("OLLAMA_MODEL", "gemma3:4b")
OLLAMA_ENABLED = _get_env_str("OLLAMA_ENABLED", "true").lower() in ("true", "1", "yes")
OLLAMA_TIMEOUT_SECONDS = _get_env_int("OLLAMA_TIMEOUT_SECONDS", 15, minimum=3)
OLLAMA_CONFIDENCE_THRESHOLD = _get_env_float(
    "OLLAMA_CONFIDENCE_THRESHOLD", 0.6, minimum=0.0, maximum=1.0
)

