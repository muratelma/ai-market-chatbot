"""Deterministic tests for chat_intent.classify_intent.

Only the rule-based path is exercised. The Ollama fallback (consulted only for
very short ambiguous input) is patched out so the suite never hits the network
and stays deterministic.
"""
import unittest
from unittest.mock import patch

import chat_intent
from chat_intent import (
    classify_intent,
    INTENT_GREETING,
    INTENT_THANKS,
    INTENT_GOODBYE,
    INTENT_PRODUCT_SEARCH,
    INTENT_NONSENSE,
    INTENT_CLARIFICATION_FOLLOWUP,
)


class TestChatIntent(unittest.TestCase):
    def setUp(self):
        # Guarantee determinism: never call Ollama, even for short ambiguous text.
        patcher = patch.object(chat_intent, "_classify_with_ollama", return_value=None)
        self.addCleanup(patcher.stop)
        patcher.start()

    def test_greeting(self):
        result = classify_intent("merhaba")
        self.assertEqual(result.intent, INTENT_GREETING)
        self.assertTrue(result.response)

    def test_thanks(self):
        self.assertEqual(classify_intent("teşekkürler").intent, INTENT_THANKS)

    def test_goodbye(self):
        self.assertEqual(classify_intent("görüşürüz").intent, INTENT_GOODBYE)

    def test_empty_message_is_nonsense(self):
        self.assertEqual(classify_intent("").intent, INTENT_NONSENSE)

    def test_multiword_non_chat_defaults_to_product_search(self):
        # 3+ words, no chat pattern → routed to the search pipeline.
        self.assertEqual(
            classify_intent("kamp için çadır lazım").intent, INTENT_PRODUCT_SEARCH
        )

    def test_pending_clarification_short_reply_is_followup(self):
        result = classify_intent("evet olsun", has_pending_clarification=True)
        self.assertEqual(result.intent, INTENT_CLARIFICATION_FOLLOWUP)


if __name__ == "__main__":
    unittest.main()
