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
TAXONOMY_MATCH_THRESHOLD = _get_env_float("AI_MARKET_TAXONOMY_MATCH_THRESHOLD", 0.45)
