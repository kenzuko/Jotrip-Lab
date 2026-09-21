import unittest
from weather.pipeline.build_jotrip_forecast import build

class JoTripRegionalForecastTests(unittest.TestCase):
    def sample_row(self,lead,base):
        def v(q50,q90,spread,prob=None):
            members=[q50-6,q50-4,q50-2,q50,q50+2,q50+4,q90]
            return {"corrected":{"q50":q50,"q90":q90,"q95":q90+1,"spread":spread,
                                 "exceedance_probability":prob,"member_count":31},
                    "member_values_corrected":members}
        return {
            "lead_hours":lead,
            "valid_time":f"2026-09-{18+lead//24:02d}T00:00:00+00:00",
            "member_count":31,
            "variables":{
                "temperature":v(28+base,29+base,.5),
                "wind":v(18+base,28+base,5,.2+base/100),
                "rain":v(2+base,8+base,3,.3+base/100),
            },
        }

    def test_regions_and_public_cadence(self):
        points={}
        ids=["duong_dong","cua_can","ganh_dau","bai_thom","ham_ninh","bai_sao","an_thoi"]
        for idx,p in enumerate(ids):
            points[p]=[self.sample_row(lead,idx/10) for lead in range(6,241,6)]
        ensemble={
            "run_time":"2026-09-18T00:00:00+00:00",
            "generated_at":"2026-09-18T01:00:00+00:00",
            "horizon_hours":240,
            "completion_ratio":.96,
            "calibration_status":"LEARNING",
            "points":points,
        }
        nowcast={
            "points":{
                "duong_dong":{
                    "score":90,
                    "cloud_motion":{
                        "status":"APPROACHING","approaching":True,"predicted_impact":True,"public_track_usable":True,"eta_minutes":35,
                        "source_sector":"Đông","motion_heading":"Tây","motion_speed_kmh":28,
                        "tracking_confidence":"MEDIUM",
                    },
                }
            }
        }
        p=build(ensemble,nowcast)
        self.assertEqual(p["horizon_hours"],240)
        self.assertEqual(set(p["regions"]),{"north_northwest","central_west","east_northeast","south_southeast"})
        for region in p["regions"].values():
            leads=[r["lead_hours"] for r in region["rows"]]
            self.assertEqual(leads[:12],list(range(6,73,6)))
            self.assertTrue(all(x%12==0 for x in leads[12:]))
            self.assertEqual(leads[-1],240)
            self.assertEqual(len(leads),26)
        north=p["regions"]["north_northwest"]["rows"][0]
        self.assertEqual(north["point_count"],2)
        self.assertIsNotNone(north["wind_q10_kmh"])
        self.assertLessEqual(north["wind_q10_kmh"],north["wind_kmh"])
        self.assertLessEqual(north["wind_kmh"],north["wind_q90_kmh"])
        self.assertIn(north["risk_driver"]["rain"],{"Gành Dầu","Cửa Cạn"})
        self.assertEqual(north["confidence_band"],"KHÁ")
        central=p["regions"]["central_west"]["rows"][0]
        self.assertEqual(central["nowcast_overlay"]["level"],"HIGH")
        self.assertTrue(central["nowcast_overlay"]["applies"])
        self.assertEqual(central["nowcast_overlay"]["eta_minutes"],35)
        self.assertEqual(central["risk_driver"]["nowcast"],"Dương Đông")
        # Satellite context must not rewrite raw ensemble distribution values.
        self.assertEqual(central["rain_mm"],2.0)
        self.assertTrue(p["nowcast_context"]["applied"])
        self.assertTrue(central["nowcast_overlay"]["operational_impact"])

    def test_moving_away_cloud_is_context_not_operational_impact(self):
        points={"duong_dong":[self.sample_row(6,0.0)]}
        ensemble={
            "run_time":"2026-09-21T00:00:00+00:00",
            "generated_at":"2026-09-21T08:40:00+00:00",
            "horizon_hours":240,
            "completion_ratio":1.0,
            "calibration_status":"LEARNING",
            "points":points,
        }
        nowcast={
            "sampled_time":"2026-09-21T08:30:00+00:00",
            "points":{"duong_dong":{
                "score":90,
                "cloud_motion":{
                    "status":"MOVING_AWAY","approaching":False,
                    "predicted_impact":False,"public_track_usable":True,
                    "eta_minutes":None,
                }
            }},
        }
        p=build(ensemble,nowcast)
        row=p["regions"]["central_west"]["rows"][0]
        self.assertTrue(p["nowcast_context"]["applied"])
        self.assertIsNotNone(row["nowcast_overlay"])
        self.assertFalse(row["nowcast_overlay"]["operational_impact"])
        self.assertIsNone(row["risk_driver"]["nowcast"])

    def test_newer_nowcast_generation_than_ensemble_still_applies(self):
        points={"duong_dong":[self.sample_row(6,0.0)]}
        ensemble={
            "run_time":"2026-09-21T00:00:00+00:00",
            "generated_at":"2026-09-21T08:42:00+00:00",
            "horizon_hours":240,
            "completion_ratio":1.0,
            "calibration_status":"LEARNING",
            "points":points,
        }
        nowcast={
            "generated_at":"2026-09-21T09:54:00+00:00",
            "sampled_time":"2026-09-21T09:20:00+00:00",
            "points":{"duong_dong":{
                "score":90,
                "cloud_motion":{
                    "status":"APPROACHING","approaching":True,
                    "predicted_impact":True,"public_track_usable":True,
                    "eta_minutes":30,
                }
            }},
        }
        p=build(ensemble,nowcast)
        self.assertTrue(p["nowcast_context"]["applied"])
        self.assertTrue(p["regions"]["central_west"]["rows"][0]["nowcast_overlay"]["operational_impact"])

    def test_stale_nowcast_is_not_used_as_live_context(self):
        points={"duong_dong":[self.sample_row(6,0.0)]}
        ensemble={
            "run_time":"2026-09-21T00:00:00+00:00",
            "generated_at":"2026-09-21T08:40:00+00:00",
            "horizon_hours":240,
            "completion_ratio":1.0,
            "calibration_status":"LEARNING",
            "points":points,
        }
        nowcast={
            "sampled_time":"2026-09-21T06:40:00+00:00",
            "points":{"duong_dong":{"score":90,"cloud_motion":{"approaching":True,"eta_minutes":30}}},
        }
        p=build(ensemble,nowcast)
        row=p["regions"]["central_west"]["rows"][0]
        self.assertFalse(p["nowcast_context"]["applied"])
        self.assertIsNone(row["nowcast_overlay"])
        self.assertIsNone(row["risk_driver"]["nowcast"])

if __name__=="__main__":
    unittest.main()
