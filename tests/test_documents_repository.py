import unittest

from documents_repository import DocumentItem, apply_optimistic_favorite


class OptimisticFavoriteTests(unittest.TestCase):
    def test_optimistic_toggle_and_rollback(self):
        docs = [DocumentItem(doc_id=1, title="Doc", source="user", path="/x", is_favorite=False)]

        updated, previous = apply_optimistic_favorite(docs, 0)

        self.assertTrue(updated[0].is_favorite)
        self.assertFalse(previous.is_favorite)

        # rollback
        updated[0] = previous
        self.assertFalse(updated[0].is_favorite)


if __name__ == "__main__":
    unittest.main()
