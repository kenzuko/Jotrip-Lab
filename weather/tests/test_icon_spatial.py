import unittest

from weather.collectors.icon_point import _lead_hours


class IconSpatialTests(unittest.TestCase):
    def test_lead_hours_accepts_minutes(self):
        self.assertEqual(_lead_hours("0m"), 0)
        self.assertEqual(_lead_hours("60m"), 1)

    def test_lead_hours_accepts_hours_and_numeric(self):
        self.assertEqual(_lead_hours("3h"), 3)
        self.assertEqual(_lead_hours(6), 6)


if __name__ == "__main__":
    unittest.main()
