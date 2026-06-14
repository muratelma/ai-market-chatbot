import os
import unittest

import numpy as np
import pandas as pd

from query_parser import (
    build_taxonomy_embeddings,
    extract_price_range,
    infer_main_category_from_query_context,
    parse_query,
)


class DummyModel:
    def encode(self, texts):
        vectors = []
        for text in texts:
            normalized_len = float(len(str(text)) % 7 + 1)
            vectors.append([normalized_len, 1.0, 0.5])
        return np.array(vectors, dtype="float32")


class QueryParserQualityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Parser unit tests use a small committed fixture instead of the
        # runtime catalog: the product source is now PostgreSQL only (no
        # products.csv at runtime), and tests must not require a live DB.
        fixture = os.path.join(
            os.path.dirname(__file__), "fixtures", "products_sample.csv"
        )
        cls.df = pd.read_csv(fixture)
        cls.model = DummyModel()
        cls.taxonomy_records = [
            {"field": "main_category", "value": "Spor", "text": "spor urunleri"},
            {"field": "product_type", "value": "Yoga Matı", "text": "yoga mati"},
        ]
        cls.taxonomy_embeddings = build_taxonomy_embeddings(cls.model, cls.taxonomy_records)

    def test_extract_price_range_swaps_reverse_interval_with_separators(self):
        min_price, max_price = extract_price_range("1.500 TL ile 900 TL arası ayakkabı")
        self.assertEqual(min_price, 900)
        self.assertEqual(max_price, 1500)

    def test_parse_query_applies_ascii_turkish_alias_for_pisik_kremi(self):
        parsed = parse_query(
            "bebek için pisik kremi ariyorum",
            self.df,
            self.model,
            self.taxonomy_embeddings,
            self.taxonomy_records,
            taxonomy_match_threshold=0.99,
        )

        self.assertEqual(parsed["main_category"], "Anne & Bebek")
        self.assertEqual(parsed["sub_category"], "Bakım")
        self.assertEqual(parsed["product_type"], "Pişik Kremi")

    def test_parse_query_keeps_yazlik_as_feature_for_ayakkabi(self):
        parsed = parse_query(
            "yazlık erkek ayakkabı",
            self.df,
            self.model,
            self.taxonomy_embeddings,
            self.taxonomy_records,
            taxonomy_match_threshold=0.99,
        )

        self.assertEqual(parsed["main_category"], "Ayakkabı")
        self.assertIsNone(parsed["product_type"])

    def test_context_inference_returns_none_when_multiple_categories_compete(self):
        self.assertIsNone(infer_main_category_from_query_context("kamp ve spor için mat"))

    def test_context_inference_uses_turkish_normalization_without_substring_noise(self):
        self.assertEqual(infer_main_category_from_query_context("cadir için lamba"), "Kamp")
        self.assertIsNone(infer_main_category_from_query_context("deve figurlu aksesuar"))

    def test_parse_query_contract_keys_are_stable(self):
        parsed = parse_query(
            "1000den 2000e kadar ayakkabı",
            self.df,
            self.model,
            self.taxonomy_embeddings,
            self.taxonomy_records,
            taxonomy_match_threshold=0.99,
        )

        expected_keys = {
            "min_price",
            "max_price",
            "main_category",
            "sub_category",
            "product_type",
            "target_group",
            "features",
            "contexts",
            "taxonomy_match",
        }
        self.assertEqual(set(parsed.keys()), expected_keys)


if __name__ == "__main__":
    unittest.main()
