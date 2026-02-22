import tempfile
import unittest
from pathlib import Path
from unittest import mock

import kb


class KbFtsTests(unittest.TestCase):
    def test_sanitize_fts5_query_punctuation(self):
        self.assertEqual(kb.sanitize_fts5_query("1+1?"), '"1" "1"')
        self.assertEqual(kb.sanitize_fts5_query("hello?"), '"hello"')

    def test_sanitize_fts5_query_quotes(self):
        self.assertEqual(kb.sanitize_fts5_query('"hello" world'), '"hello" "world"')

    def test_sanitize_fts5_query_empty(self):
        self.assertEqual(kb.sanitize_fts5_query(""), "")
        self.assertEqual(kb.sanitize_fts5_query("   "), "")

    def test_search_with_feedback_never_raises_on_punctuation(self):
        with tempfile.TemporaryDirectory() as td:
            db_path = Path(td) / "test.sqlite"
            kb.init_db(db_path)
            kb.add_document(
                db_path=db_path,
                title="Math",
                source="user",
                text="what is 1 plus 1",
                path=None,
            )
            results, warning = kb.search_with_feedback(db_path, "what is 1+1?", limit=5)
            self.assertIsInstance(results, list)
            self.assertIn(warning, (None, "We couldn't search that exact punctuation. Try simpler keywords."))

    def test_hybrid_search_falls_back_to_lexical_when_vector_deps_missing(self):
        with tempfile.TemporaryDirectory() as td:
            db_path = Path(td) / "test.sqlite"
            embed_dir = Path(td) / "embed-model"
            embed_dir.mkdir()
            kb.init_db(db_path)
            kb.add_document(
                db_path=db_path,
                title="Fallback",
                source="user",
                text="alpha beta gamma",
                path=None,
            )
            with mock.patch("kb._vector_dependencies_available", return_value=False), mock.patch(
                "kb.vector_search"
            ) as vector_search_mock:
                results = kb.hybrid_search(
                    db_path=db_path,
                    query="alpha",
                    embed_model_path=embed_dir,
                    index_path=Path(td) / "vector_index.bin",
                    meta_path=Path(td) / "vector_meta.npz",
                    limit=3,
                )
            vector_search_mock.assert_not_called()
            self.assertGreaterEqual(len(results), 1)


if __name__ == "__main__":
    unittest.main()
