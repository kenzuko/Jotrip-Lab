import unittest

from weather.processing.synop_actual import decode_synop_actual


class SynopActualDecodeTests(unittest.TestCase):
    def test_phu_quoc_20260922_12z_measured_wind_and_rain(self):
        raw = (
            "AAXX 22121 48917 01496 83603 10256 20244 30091 40097 52019 "
            "61624 76398 8392/ 222// 00280 332// 4//02 333 03025 10293 "
            "59001 61622 71623 81894 82995 88499 96163 555 20250="
        )
        d = decode_synop_actual(raw)

        self.assertEqual(d["wind"]["measurement_origin"], "ANEMOMETER")
        self.assertEqual(d["wind"]["direction_deg"], 360)
        self.assertEqual(d["wind"]["speed_ms"], 3.0)

        precip = {(x["section"], x["raw_group"]): x for x in d["precipitation"]}
        self.assertEqual(precip[(1, "61624")]["accumulation_mm"], 162.0)
        self.assertEqual(precip[(1, "61624")]["window_hours"], 24)
        self.assertEqual(precip[(3, "61622")]["accumulation_mm"], 162.0)
        self.assertEqual(precip[(3, "61622")]["window_hours"], 12)

    def test_phu_quoc_20260922_06z(self):
        raw = (
            "AAXX 22061 48917 01498 70503 10280 20254 30088 40094 58017 "
            "60073 72582 8391/ 222// 00290 2//01 333 59014 60071 "
            "82894 82995 86499="
        )
        d = decode_synop_actual(raw)
        self.assertEqual(d["wind"]["direction_deg"], 50)
        self.assertEqual(d["wind"]["speed_ms"], 3.0)
        precip = {(x["section"], x["raw_group"]): x for x in d["precipitation"]}
        self.assertEqual(precip[(1, "60073")]["accumulation_mm"], 7.0)
        self.assertEqual(precip[(1, "60073")]["window_hours"], 18)
        self.assertEqual(precip[(3, "60071")]["accumulation_mm"], 7.0)
        self.assertEqual(precip[(3, "60071")]["window_hours"], 6)

    def test_nil_report_has_no_measurements(self):
        d = decode_synop_actual("AAXX 22031 48917 NIL=")
        self.assertIsNone(d["wind"])
        self.assertEqual(d["precipitation"], [])


if __name__ == "__main__":
    unittest.main()
