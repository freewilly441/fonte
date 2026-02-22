import tempfile
import unittest
from pathlib import Path

import kb


class KbPaginationTests(unittest.TestCase):
    def test_count_and_pagination(self):
        with tempfile.TemporaryDirectory() as td:
            db_path = Path(td) / "test.sqlite"
            kb.init_db(db_path)
            for i in range(12):
                kb.add_document(
                    db_path=db_path,
                    title=f"Doc {i}",
                    source="user",
                    text=f"hello world {i}",
                    path=None,
                )

            total = kb.count_documents(db_path)
            page1 = kb.list_documents_paged(db_path, limit=5, offset=0)
            page2 = kb.list_documents_paged(db_path, limit=5, offset=5)

            self.assertEqual(total, 12)
            self.assertEqual(len(page1), 5)
            self.assertEqual(len(page2), 5)


if __name__ == "__main__":
    unittest.main()
