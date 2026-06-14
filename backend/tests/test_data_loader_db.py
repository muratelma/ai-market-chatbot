"""DB fail-loud behavior for data_loader.load_products.

Verifies that explicit DB mode (source="db") raises instead of silently
falling back to CSV when DB loading fails. Uses mocks only — no real
PostgreSQL server required.
"""
import unittest
from unittest.mock import patch

import data_loader


class TestDbFailLoud(unittest.TestCase):
    def test_db_failure_raises_and_does_not_fall_back_to_csv(self):
        # Simulate the DB load failing (bad URL / auth / missing table).
        db_error = ConnectionError("simulated DB connection failure")

        with patch(
            "database.load_products_from_db", side_effect=db_error
        ), patch.object(data_loader, "_read_products_csv") as csv_reader:
            with self.assertRaises(RuntimeError) as ctx:
                data_loader.load_products("products.csv", source="db")

        # The original DB error must be chained, not swallowed.
        self.assertIs(ctx.exception.__cause__, db_error)
        # Critically: CSV must NOT be used as a hidden fallback in DB mode.
        csv_reader.assert_not_called()


if __name__ == "__main__":
    unittest.main()
