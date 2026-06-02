import unittest
from unittest.mock import patch

from eval.run_eval import evaluate_queries, product_matches_expectation


class EvalHarnessTests(unittest.TestCase):
    def test_product_matches_expectation_success(self):
        product = {
            "main_category": "Elektronik",
            "sub_category": "Bilgisayar",
            "target_group": "Unisex",
            "product_type": "Mouse",
        }
        expected = {
            "main_category": "Elektronik",
            "sub_category": "Bilgisayar",
            "product_types_any": ["Mouse", "Oyuncu Mouse"],
        }
        self.assertTrue(product_matches_expectation(product, expected))

    def test_product_matches_expectation_failure(self):
        product = {
            "main_category": "Elektronik",
            "sub_category": "Bilgisayar",
            "target_group": "Unisex",
            "product_type": "Klavye",
        }
        expected = {
            "main_category": "Elektronik",
            "sub_category": "Bilgisayar",
            "product_types_any": ["Mouse", "Oyuncu Mouse"],
        }
        self.assertFalse(product_matches_expectation(product, expected))

    def test_evaluate_queries_metrics(self):
        gold_queries = [
            {"id": "Q1", "query": "mouse öner", "expected": {"main_category": "Elektronik", "product_types_any": ["Mouse"]}},
            {"id": "Q2", "query": "ayakkabı öner", "expects_clarification": True},
            {"id": "Q3", "query": "ışın kılıcı", "expects_empty_result": True},
        ]

        mocked_results = [
            {
                "needs_clarification": False,
                "products": [
                    {
                        "name": "X",
                        "main_category": "Elektronik",
                        "sub_category": "Bilgisayar",
                        "target_group": "Unisex",
                        "product_type": "Mouse",
                        "match_percent": 88,
                    }
                ],
                "parsed_query": {},
            },
            {
                "needs_clarification": True,
                "products": [],
                "parsed_query": {},
            },
            {
                "needs_clarification": False,
                "products": [],
                "parsed_query": {},
            },
        ]

        with patch("eval.run_eval.run_single_query", side_effect=mocked_results):
            report = evaluate_queries(gold_queries, context=None)

        self.assertAlmostEqual(report["metrics"]["top1_relevance"], 1.0)
        self.assertAlmostEqual(report["metrics"]["top3_hit_rate"], 1.0)
        self.assertAlmostEqual(report["metrics"]["clarification_rate"], 1 / 3)
        self.assertAlmostEqual(report["metrics"]["empty_result_rate"], 1 / 3)
        self.assertEqual(report["counters"]["topk_denominator"], 1)


if __name__ == "__main__":
    unittest.main()
