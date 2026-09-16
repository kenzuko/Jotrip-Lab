import unittest

from weather.processing.convective_proxy import convective_signal


class ConvectiveProxyTests(unittest.TestCase):
    def test_low_signal(self):
        out = convective_signal(-20.0, 4000, 0.0)
        self.assertEqual(out["level"], "LOW")
        self.assertEqual(out["score"], 0)

    def test_deep_convection_is_not_named_lightning(self):
        out = convective_signal(-55.0, 11000, -4.0)
        self.assertEqual(out["level"], "ELEVATED")
        self.assertGreaterEqual(out["score"], 50)
        self.assertIn("NOT_LIGHTNING_OBSERVATION", out["method"])

    def test_high_signal_caps_at_100(self):
        out = convective_signal(-70.0, 15000, -10.0)
        self.assertEqual(out["level"], "HIGH")
        self.assertLessEqual(out["score"], 100)


if __name__ == "__main__":
    unittest.main()
