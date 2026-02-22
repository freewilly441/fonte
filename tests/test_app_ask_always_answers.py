import unittest
from unittest.mock import patch

from app import DB_PATH, KnowledgeApp


class _Cfg(dict):
    def get(self, key, default=None):
        return super().get(key, default)


class _Analytics:
    def track(self, *args, **kwargs):
        return None


class AskAlwaysAnswersTests(unittest.TestCase):
    @patch("app.kb.search", return_value=[])
    @patch("app.llm_lmstudio.chat", return_value="constant mocked answer")
    def test_build_qa_response_returns_llm_answer_when_kb_empty(self, mock_chat, mock_search):
        app = KnowledgeApp.__new__(KnowledgeApp)
        app.cfg = _Cfg(
            {
                "max_tokens": "192",
                "llm_max_tokens": "192",
                "temperature": "0.2",
                "timeout_seconds": "20",
                "lmstudio_base_url": "http://localhost:1234/v1",
                "model_small_id": "small-model",
                "model_large_id": "large-model",
            }
        )
        app.llm = object()
        app.analytics = _Analytics()

        payload = KnowledgeApp._build_qa_response(app, "What is Foo?")

        self.assertEqual(payload["answer_text"], "constant mocked answer")
        self.assertEqual(payload["answer"], "constant mocked answer")
        self.assertTrue(payload["answer_text"].strip())
        self.assertFalse(payload["had_context"])
        self.assertEqual(payload["citations"], [])
        mock_search.assert_called_once_with(DB_PATH, "What is Foo?", limit=4)
        self.assertTrue(mock_chat.called)

    def test_direct_fallback_answers_simple_number_after_question(self):
        app = KnowledgeApp.__new__(KnowledgeApp)
        out = KnowledgeApp._direct_fallback_answer(app, "what is the number after 9?", [])
        self.assertEqual(out, "10")


if __name__ == "__main__":
    unittest.main()
