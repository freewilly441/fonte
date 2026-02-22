import unittest

from error_mapper import ValidationError, map_exception, to_ui_error


class ErrorMapperTests(unittest.TestCase):
    def test_maps_validation_error(self):
        err = ValidationError({"question": "required"})
        mapped = map_exception(err)
        self.assertEqual(mapped.code, "validation")
        self.assertEqual(mapped.recovery_action, "Edit")
        self.assertIn("question", mapped.field_errors)

    def test_maps_timeout_error(self):
        mapped = map_exception(TimeoutError("request timed out"))
        self.assertEqual(mapped.code, "network_timeout")
        self.assertEqual(mapped.recovery_action, "Retry")

    def test_maps_unknown_error(self):
        mapped = map_exception(RuntimeError("boom"))
        ui_error = to_ui_error(mapped)
        self.assertEqual(mapped.code, "unknown")
        self.assertEqual(ui_error.category, "unknown")
        self.assertTrue(ui_error.message)

    def test_maps_offline_error(self):
        mapped = map_exception(OSError("network is unreachable"))
        self.assertEqual(mapped.code, "offline")
        self.assertEqual(mapped.recovery_action, "Retry")


if __name__ == "__main__":
    unittest.main()
