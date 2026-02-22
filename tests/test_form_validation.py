import unittest

from form_validation import route_search_answer, should_generate_search_answer, validate_question


class FormValidationTests(unittest.TestCase):
    def test_requires_non_empty_question(self):
        self.assertEqual(validate_question("   "), "Question is required.")

    def test_rejects_too_short_question(self):
        self.assertEqual(validate_question("hi"), "Question is too short.")

    def test_rejects_too_long_question(self):
        self.assertIn("too long", validate_question("x" * 601))

    def test_accepts_normal_question(self):
        self.assertIsNone(validate_question("How does offline search work?"))

    def test_detects_question_mark(self):
        self.assertTrue(should_generate_search_answer("What causes inflation?"))

    def test_detects_question_word_prefix(self):
        self.assertTrue(should_generate_search_answer("how to learn python"))

    def test_detects_sentence_like_query(self):
        self.assertTrue(should_generate_search_answer("Can you explain this concept in simple terms"))

    def test_keeps_keyword_queries_as_search_only(self):
        self.assertFalse(should_generate_search_answer("python tkinter tutorial"))

    def test_route_search_answer_off(self):
        self.assertEqual(route_search_answer("What is inflation?", ai_enabled=False, model_installed=False), "off")

    def test_route_search_answer_missing_model(self):
        self.assertEqual(
            route_search_answer("How does caching work?", ai_enabled=True, model_installed=False),
            "not_installed",
        )

    def test_route_search_answer_generate(self):
        self.assertEqual(route_search_answer("How does caching work?", ai_enabled=True, model_installed=True), "generate")


if __name__ == "__main__":
    unittest.main()
