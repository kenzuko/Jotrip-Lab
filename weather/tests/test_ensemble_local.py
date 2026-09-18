import unittest
from weather.processing.ensemble_local import (
    apply_member_correction, correct_distribution, learn_additive_bias,
    learn_rain_factor,
)

class EnsembleLocalTests(unittest.TestCase):
    def test_learning_gate_does_not_change_members(self):
        cases=[{"observed":12,"forecast":10,"observation_class":"ACTUAL"} for _ in range(10)]
        cal=learn_additive_bias(cases,min_samples=30)
        self.assertEqual(cal["status"],"LEARNING")
        self.assertEqual(apply_member_correction([9,10,11],cal,variable="temperature"),[9.0,10.0,11.0])

    def test_ready_additive_is_applied_per_member(self):
        cases=[{"observed":12,"forecast":10,"observation_class":"ACTUAL"} for _ in range(60)]
        cal=learn_additive_bias(cases,min_samples=30,shrink_k=30)
        self.assertEqual(cal["status"],"READY")
        self.assertAlmostEqual(cal["applied_bias"],4/3,places=5)
        out=correct_distribution([8,10,12],cal,variable="temperature",threshold=11)
        self.assertEqual(out["status"],"CALIBRATED")
        self.assertGreater(out["corrected"]["q50"],out["raw"]["q50"])
        self.assertEqual(len(out["member_values_corrected"]),3)

    def test_rain_factor_nonnegative(self):
        cases=[{"observed":4.0,"forecast":2.0,"observation_class":"ACTUAL"} for _ in range(60)]
        cal=learn_rain_factor(cases,min_samples=30,shrink_k=30)
        self.assertEqual(cal["status"],"READY")
        vals=apply_member_correction([0,1,2],cal,variable="rain")
        self.assertTrue(all(v>=0 for v in vals))
        self.assertGreater(vals[-1],2)

    def test_estimated_now_is_never_training_truth(self):
        cases=[{"observed":100,"forecast":0,"observation_class":"ESTIMATED_NOW"} for _ in range(100)]
        cal=learn_additive_bias(cases,min_samples=1)
        self.assertEqual(cal["sample_count"],0)
        self.assertEqual(cal["status"],"LEARNING")

if __name__=="__main__":
    unittest.main()
