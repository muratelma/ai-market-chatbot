"""Static validation of db/seed_products.sql (no DB required).

seed_products.sql is the source of truth for the product catalog. These tests
guard its reproducibility contract: it must recreate the table from zero and
keep explicit ids 1..1000 in order so the embedding/ORDER BY id contract holds.
"""
import re
from pathlib import Path

from data_loader import REQUIRED_PRODUCT_COLUMNS

SEED_PATH = Path(__file__).resolve().parents[1] / "db" / "seed_products.sql"
SEED_SQL = SEED_PATH.read_text(encoding="utf-8")

EXPECTED_ROWS = 1000


def test_seed_file_exists():
    assert SEED_PATH.exists()


def test_seed_recreates_table_from_zero():
    upper = SEED_SQL.upper()
    assert "DROP TABLE IF EXISTS" in upper
    assert "CREATE TABLE" in upper
    assert "PRIMARY KEY" in upper


def test_seed_has_expected_insert_count():
    assert len(re.findall(r"INSERT INTO", SEED_SQL)) == EXPECTED_ROWS


def test_seed_ids_are_contiguous_1_to_n():
    ids = [int(m) for m in re.findall(r"VALUES\s*\((\d+),", SEED_SQL)]
    assert len(ids) == EXPECTED_ROWS
    assert sorted(ids) == list(range(1, EXPECTED_ROWS + 1))


def test_seed_insert_columns_match_contract():
    # First INSERT's column list, minus the id PK, must equal the catalog columns
    # in the exact order data_loader/database expect.
    m = re.search(r"INSERT INTO \S+ \(([^)]*)\) VALUES", SEED_SQL)
    assert m is not None
    cols = [c.strip() for c in m.group(1).split(",")]
    assert cols[0] == "id"
    assert cols[1:] == list(REQUIRED_PRODUCT_COLUMNS)
