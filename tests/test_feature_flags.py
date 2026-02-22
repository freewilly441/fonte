import unittest

from feature_flags import can_access_feature, from_config


class FeatureFlagsTests(unittest.TestCase):
    def test_from_config(self):
        flags = from_config({"feature_ab_testing": "true", "feature_referrals": "false"})
        self.assertTrue(flags.ab_testing_hook)
        self.assertFalse(flags.referral_hook)

    def test_feature_access_default_true(self):
        self.assertTrue(can_access_feature(cfg={}, feature_key="online_import"))

    def test_feature_access_false(self):
        self.assertFalse(can_access_feature(cfg={"feature_online_import_enabled": "false"}, feature_key="online_import"))


if __name__ == "__main__":
    unittest.main()
