import unittest
from datetime import datetime, timezone

from weather.processing.synop_actual import decode_synop_actual
from weather.collectors.phuquoc_synop_raw import compact_live


class SynopActualDecodeTests(unittest.TestCase):
    def test_decodes_verified_atmospheric_and_marine_sample(self):
        raw=(
            "AAXX 15061 48917 32598 62305 10318 20256 30094 40100 "
            "58008 83208 222// 00328 2//01 333 59010 83895 86299="
        )
        d=decode_synop_actual(raw)
        self.assertEqual(d["wind"]["direction_deg"],230)
        self.assertEqual(d["wind"]["speed_ms"],5.0)
        self.assertEqual(d["wind"]["measurement_origin"],"ANEMOMETER")
        self.assertEqual(d["air_temperature_c"],31.8)
        self.assertEqual(d["dewpoint_c"],25.6)
        self.assertEqual(d["station_pressure_hpa"],1009.4)
        self.assertEqual(d["sea_level_pressure_hpa"],1010.0)
        self.assertEqual(d["marine"]["sea_surface_temperature"]["temperature_c"],32.8)
        wave=d["marine"]["wind_wave"]
        self.assertEqual(wave["height_nominal_m"],0.5)
        self.assertEqual(wave["height_bin_m"],[0.25,0.75])
        self.assertFalse(wave["instrument_hs"])

    def test_decodes_synop_rain_window_without_inventing_rate(self):
        raw=(
            "AAXX 22121 48917 01496 83603 10256 20244 30091 40097 "
            "52019 61624 76398 8392/ 222// 00280 332// 4//02 "
            "333 03025 10293 59001 61622 71623 81894 82995 88499 96163="
        )
        d=decode_synop_actual(raw)
        p={(x["section"],x["raw_group"]):x for x in d["precipitation"]}
        self.assertEqual(p[(1,"61624")]["accumulation_mm"],162.0)
        self.assertEqual(p[(1,"61624")]["window_hours"],24)
        self.assertEqual(p[(3,"61622")]["window_hours"],12)

    def test_compact_live_keeps_48917_separate_from_vvpq(self):
        payload={
            "generated_at":"2026-10-01T06:00:00+00:00",
            "source":"OGIMET_GETSYNOP",
            "source_namespace":"WMO_INDEX",
            "identifier":"48917",
            "station_name":"PHU QUOC",
            "reference_lat":10.22,
            "reference_lon":103.97,
            "station_epoch":"CURRENT_METADATA_EPOCH_UNRESOLVED",
            "identity_policy":"separate",
            "provenance_url":"https://example.test",
            "observations":[{
                "observed_at":"2026-10-01T03:00:00+00:00",
                "source_namespace":"WMO_INDEX",
                "identifier":"48917",
                "raw_observation":"AAXX ...",
                "decoded_actual":{},
            }],
        }
        out=compact_live(payload,datetime(2026,10,1,6,0,tzinfo=timezone.utc))
        self.assertEqual(out["status"],"FRESH")
        self.assertEqual(out["source_namespace"],"WMO_INDEX")
        self.assertEqual(out["identifier"],"48917")
        self.assertIn("NOT_SPATIAL_POINT_ANCHOR",out["production_role"])


if __name__=="__main__":
    unittest.main()
