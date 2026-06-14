"""Tests for the PostgreSQL-only product loading path.

PostgreSQL is the only product source. These tests cover, with mocks only
(no real PostgreSQL, no network):
  * fail-loud behavior (DB error / missing DATABASE_URL),
  * the DataFrame / embedding ORDER CONTRACT enforced by _finalize_products,
  * the success path of load_products(), and
  * the SQL built by database.load_products_from_db (ORDER BY id contract).
"""
import unittest
from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd

import data_loader
from data_loader import REQUIRED_PRODUCT_COLUMNS


def _raw_rows():
    """A raw catalog as load_products_from_db would return it: exactly the
    required columns, in a deliberate (non-sorted) row order, with two rows
    that must be dropped (missing/invalid price) and string prices to coerce."""
    rows = [
        ("A", "descA", "Giyim", "Elbise", "Kadın", "Abiye", "f", "t", "{}", "300"),
        ("B", "descB", "Giyim", "Elbise", "Kadın", "Midi", "f", "t", "{}", "100"),
        ("C", "descC", "Giyim", "Elbise", "Kadın", "Maxi", "f", "t", "{}", None),
        ("D", "descD", "Giyim", "Elbise", "Kadın", "Mini", "f", "t", "{}", "abc"),
    ]
    return pd.DataFrame(rows, columns=list(REQUIRED_PRODUCT_COLUMNS))


class TestDbFailLoud(unittest.TestCase):
    def test_db_load_failure_raises_runtime_error(self):
        # Simulate the DB load failing (bad URL / auth / missing table).
        # DATABASE_URL is set so we reach the DB-load path (not the missing-URL
        # short-circuit, which is covered by the test below).
        db_error = ConnectionError("simulated DB connection failure")

        with patch.object(data_loader, "DATABASE_URL", "postgresql://x/y"), patch(
            "database.load_products_from_db", side_effect=db_error
        ):
            with self.assertRaises(RuntimeError) as ctx:
                data_loader.load_products()

        # The original DB error must be chained, not swallowed.
        self.assertIs(ctx.exception.__cause__, db_error)

    def test_missing_database_url_raises_runtime_error(self):
        # With no DATABASE_URL, loading must fail loudly before touching the DB.
        with patch.object(data_loader, "DATABASE_URL", ""):
            with patch("database.load_products_from_db") as db_loader:
                with self.assertRaises(RuntimeError):
                    data_loader.load_products()
        # The DB loader must not even be attempted when the URL is absent.
        db_loader.assert_not_called()


class TestFinalizeProductsOrderContract(unittest.TestCase):
    """_finalize_products must preserve row order, coerce price, drop invalid
    rows, and reset to a 0..N-1 positional index (the embedding contract)."""

    def test_shape_order_and_price_coercion(self):
        finalized = data_loader._finalize_products(_raw_rows())

        # Columns unchanged and in the same order.
        self.assertEqual(list(finalized.columns), list(REQUIRED_PRODUCT_COLUMNS))
        # Rows with missing/invalid price dropped (C, D); A and B kept.
        self.assertEqual(list(finalized["product_name"]), ["A", "B"])
        # Order is preserved (NOT sorted by price) — contract-critical.
        self.assertEqual(finalized["price"].tolist(), [300.0, 100.0])
        # Price is numeric.
        self.assertTrue(np.issubdtype(finalized["price"].dtype, np.number))
        # Stable 0..N-1 positional index.
        self.assertEqual(finalized.index.tolist(), [0, 1])

    def test_missing_column_raises(self):
        bad = _raw_rows().drop(columns=["price"])
        with self.assertRaises(ValueError):
            data_loader._finalize_products(bad)


class TestLoadProductsSuccess(unittest.TestCase):
    def test_success_path_returns_finalized_frame(self):
        with patch.object(data_loader, "DATABASE_URL", "postgresql://x/y"), patch(
            "database.load_products_from_db", return_value=_raw_rows()
        ):
            df = data_loader.load_products()

        # Same finalize contract applied to the DB rows.
        self.assertEqual(list(df.columns), list(REQUIRED_PRODUCT_COLUMNS))
        self.assertEqual(list(df["product_name"]), ["A", "B"])
        self.assertEqual(df.index.tolist(), [0, 1])


class TestLoadProductsFromDbQuery(unittest.TestCase):
    """database.load_products_from_db must SELECT the required columns and
    ORDER BY id, using a connection it then closes."""

    def test_query_uses_order_by_id_and_required_columns(self):
        import database

        fake_cur = MagicMock()
        fake_cur.fetchall.return_value = [
            ("A", "d", "mc", "sc", "tg", "pt", "f", "t", "{}", 100)
        ]
        fake_conn = MagicMock()
        fake_conn.cursor.return_value.__enter__.return_value = fake_cur

        with patch.object(database, "get_connection", return_value=fake_conn), patch.object(
            database, "PRODUCTS_TABLE", "products"
        ):
            df = database.load_products_from_db()

        sql = fake_cur.execute.call_args[0][0]
        self.assertTrue(sql.strip().upper().startswith("SELECT"))
        self.assertIn(", ".join(REQUIRED_PRODUCT_COLUMNS), sql)
        self.assertIn("FROM products", sql)
        self.assertIn("ORDER BY id", sql)
        # Returned DataFrame carries exactly the required columns (no id column).
        self.assertEqual(list(df.columns), list(REQUIRED_PRODUCT_COLUMNS))
        fake_conn.close.assert_called_once()


if __name__ == "__main__":
    unittest.main()
