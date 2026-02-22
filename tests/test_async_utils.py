import unittest

from async_utils import RequestCoordinator


class RequestCoordinatorTests(unittest.TestCase):
    def test_dedupes_identical_inflight_key(self):
        coord = RequestCoordinator()
        first = coord.start("qa:hello", dedupe=True)
        second = coord.start("qa:hello", dedupe=True)

        self.assertIsNotNone(first)
        self.assertIsNone(second)

    def test_cancellation_invalidates_snapshot(self):
        coord = RequestCoordinator()
        snap = coord.start("docs:refresh", dedupe=True)
        self.assertIsNotNone(snap)

        coord.cancel()

        self.assertFalse(coord.complete(snap))

    def test_new_request_invalidates_old_completion(self):
        coord = RequestCoordinator()
        old = coord.start("qa:old", dedupe=True)
        new = coord.start("qa:new", dedupe=True)

        self.assertFalse(coord.complete(old))
        self.assertTrue(coord.complete(new))


if __name__ == "__main__":
    unittest.main()
