"""DB fail-loud behavior for data_loader.load_products.

PostgreSQL is the only product source. These tests verify load_products()
raises clearly (instead of silently falling back to CSV) when the DB cannot be
loaded or DATABASE_URL is missing. Uses mocks only — no real PostgreSQL needed.
"""
import unittest
from unittest.mock import patch

import data_loader


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


if __name__ == "__main__":
    unittest.main()
