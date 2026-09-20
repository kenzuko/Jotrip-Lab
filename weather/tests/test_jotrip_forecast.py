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
        p=build(ensemble)
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

if __name__=="__main__":
    unittest.main()
