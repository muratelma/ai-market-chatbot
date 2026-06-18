import os
import unittest

import numpy as np
import pandas as pd

from query_parser import (
    build_taxonomy_embeddings,
    contains_term,
    extract_excluded_terms,
    extract_price_range,
    find_named_value,
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
            "excluded_terms",
            "explicit_intent",
        }
        self.assertEqual(set(parsed.keys()), expected_keys)


    def test_parse_query_preserves_positive_intent_over_negated_terms(self):
        # "Mont veya kaban değil, elbise arıyorum" — the rejected mont/kaban
        # terms must NOT be parsed as the desired intent; the explicit positive
        # category (elbise) must win and survive the seasonal "kışlık" modifier.
        parsed = parse_query(
            "Kışlık kadın elbisesi önerir misin? Mont veya kaban değil, elbise arıyorum.",
            self.df,
            self.model,
            self.taxonomy_embeddings,
            self.taxonomy_records,
            taxonomy_match_threshold=0.99,
        )

        self.assertEqual(parsed["sub_category"], "Elbise")
        self.assertEqual(parsed["main_category"], "Giyim")
        # The negated outerwear must not leak into the desired product_type.
        self.assertNotEqual(parsed["product_type"], "Mont")
        self.assertNotIn(parsed["product_type"], ("Kaban", "Polar Mont", "Yağmurluk"))
        # And the rejected sub_category is recorded as excluded.
        self.assertIn("mont", parsed["excluded_terms"])

    def test_extract_excluded_terms_handles_negation_forms(self):
        # Each phrasing the user might use to reject the Mont category. (The
        # fixture has no Kaban product, so only catalog-present terms can be
        # excluded — Kaban exclusion is verified against the live catalog.)
        for query in (
            "mont değil",
            "mont değil, elbise öner",
            "mont veya kaban değil, elbise arıyorum",
            "mont/kaban istemiyorum",
            "mont aramıyorum",
        ):
            excluded = extract_excluded_terms(query, self.df)
            self.assertIn("mont", excluded, msg=f"query={query!r}")

    def test_extract_excluded_terms_does_not_reach_positive_clause(self):
        # The positive term in a separate clause must NOT be excluded.
        excluded = extract_excluded_terms("mont değil, elbise arıyorum", self.df)
        self.assertIn("mont", excluded)
        self.assertNotIn("elbise", excluded)

    def test_extract_excluded_terms_empty_without_cue(self):
        self.assertEqual(extract_excluded_terms("kışlık mont öner", self.df), set())

    # ----- Explicit positive product intent lock -----

    def test_contains_term_matches_turkish_inflections(self):
        # The explicit product noun is preserved even when inflected, but a
        # different word that merely shares the stem is not a match.
        self.assertTrue(contains_term("kadın elbisesi", "Elbise"))
        self.assertTrue(contains_term("kışlık kadın elbiseleri", "Elbise"))
        self.assertTrue(contains_term("elbiseyi arıyorum", "Elbise"))
        self.assertTrue(contains_term("pantolonu beğendim", "Pantolon"))
        self.assertFalse(contains_term("montaj kiti", "Mont"))
        self.assertFalse(contains_term("botanik bahçesi", "Bot"))

    def test_find_named_value_is_strict_no_prefix_guess(self):
        # find_named_value must NOT guess "yemek" -> "Yemek ..." product types;
        # it only matches a literally-named (possibly inflected) catalog value.
        self.assertEqual(
            find_named_value("kadın elbisesi öner", self.df, "sub_category"),
            "Elbise",
        )
        self.assertIsNone(
            find_named_value("yemek yapacak bir şey lazım", self.df, "product_type")
        )

    def _seasonal_taxonomy(self):
        # A Mont taxonomy entry whose text is dominated by warmth/seasonal words,
        # reproducing the real catalog where "kışlık, sıcak tutan" pulls the
        # matcher onto outerwear.
        records = [
            {"field": "sub_category", "value": "Mont",
             "text": "mont kaban kışlık sıcak tutan soğuk hava dış giyim"},
            {"field": "sub_category", "value": "Elbise", "text": "elbise kadın"},
        ]
        return records, build_taxonomy_embeddings(self.model, records)

    def test_explicit_dress_intent_survives_seasonal_taxonomy(self):
        # "Kışlık, sıcak tutan ... kadın elbisesi" must stay in Elbise even when
        # the seasonal taxonomy entry for Mont scores above threshold.
        records, embeddings = self._seasonal_taxonomy()
        for query in (
            "kışlık kadın elbiseleri",
            "sıcak tutan kadın elbisesi",
            "Kışlık, sıcak tutan ve günlük kullanıma uygun bir kadın elbisesi önerir misin?",
        ):
            parsed = parse_query(
                query, self.df, self.model, embeddings, records,
                taxonomy_match_threshold=0.5,
            )
            self.assertEqual(parsed["sub_category"], "Elbise", msg=f"query={query!r}")
            self.assertNotEqual(parsed["sub_category"], "Mont", msg=f"query={query!r}")
            self.assertEqual(parsed["explicit_intent"]["sub_category"], "Elbise")

    def test_explicit_mont_intent_is_preserved(self):
        # The opposite case must still work: an explicit Mont request stays Mont.
        records, embeddings = self._seasonal_taxonomy()
        parsed = parse_query(
            "kışlık mont öner", self.df, self.model, embeddings, records,
            taxonomy_match_threshold=0.5,
        )
        self.assertEqual(parsed["sub_category"], "Mont")
        self.assertEqual(parsed["explicit_intent"]["sub_category"], "Mont")

    def test_parse_query_does_not_overtrigger_negation_without_cue(self):
        # No negation cue → nothing excluded; positive mont intent preserved.
        parsed = parse_query(
            "kışlık mont öner",
            self.df,
            self.model,
            self.taxonomy_embeddings,
            self.taxonomy_records,
            taxonomy_match_threshold=0.99,
        )

        self.assertEqual(parsed["sub_category"], "Mont")
        self.assertEqual(parsed["excluded_terms"], [])


if __name__ == "__main__":
    unittest.main()
