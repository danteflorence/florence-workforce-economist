"""
Tests for the FastAPI pricing service (pricing_api.py).

Verifies the HTTP layer returns the SAME numbers as calling pricing_engine.price()
directly — so the API can never silently drift from the engine. Skips cleanly if
fastapi isn't installed (it lives in requirements-api.txt, not the app's reqs).

Run: python3 tests/test_pricing_api.py
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from fastapi.testclient import TestClient
    from pricing_api import app
    HAVE_FASTAPI = True
except Exception:  # fastapi/httpx not installed in this environment
    HAVE_FASTAPI = False

from pricing_engine import Calibration, CohortMix, HospitalProfile, price

_KAISER = dict(name="Test Hospital", city="Test City", state="CA",
               taxable_wage_per_hour=66.85, benefit_load_per_hour=17.50,
               all_in_agency_per_hour=121.73, agency_rate_confidence=0.92,
               agency_rate_source="hcris_nmrc")


def _engine(**cal_kwargs):
    prof = HospitalProfile(**_KAISER)
    return price(prof, CohortMix(eta=1.0), Calibration(**cal_kwargs))


@unittest.skipUnless(HAVE_FASTAPI, "fastapi not installed (pip install -r requirements-api.txt)")
class TestPricingAPI(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_health(self):
        r = self.client.get("/health")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json(), {"status": "ok"})

    def test_price_matches_engine(self):
        r = self.client.post("/price", json={"hospital": _KAISER, "cohort": {"eta": 1.0}})
        self.assertEqual(r.status_code, 200)
        data = r.json()
        eng = _engine()
        self.assertAlmostEqual(data["florence_monthly_fee_per_rn"],
                               eng.florence_monthly_fee_per_rn, places=2)
        self.assertAlmostEqual(data["employer_fica_savings_per_rn_per_month"],
                               eng.employer_fica_savings_per_rn_per_month, places=2)
        self.assertAlmostEqual(data["actual_fica_offset_pct"], eng.actual_fica_offset_pct, places=4)
        self.assertAlmostEqual(data["monthly_agency_premium_avoided_per_rn"],
                               eng.monthly_agency_premium_avoided_per_rn, places=2)
        self.assertEqual(data["channel"], eng.channel.value)
        self.assertTrue(data["feasible"])

    def test_partner_markup_passthrough(self):
        r = self.client.post("/price", json={
            "hospital": _KAISER, "calibration": {"direct_partner_markup_pct": 0.20}})
        data = r.json()
        self.assertAlmostEqual(data["partner_markup_pct"], 0.20, places=4)
        self.assertAlmostEqual(data["partner_revenue_monthly"],
                               data["florence_monthly_fee_per_rn"] * 0.20, places=2)
        # Florence's net is the protected core fee, unchanged by the markup
        self.assertAlmostEqual(data["florence_net_monthly"],
                               data["florence_monthly_fee_per_rn"], places=2)

    def test_calibration_defaults_inherit_engine(self):
        """Omitting calibration must inherit the engine's 0.40 default, not a hardcode."""
        r = self.client.post("/price", json={"hospital": _KAISER})
        self.assertAlmostEqual(r.json()["actual_fica_offset_pct"], 0.40, places=3)

    def test_validation_rejects_bad_input(self):
        r = self.client.post("/price", json={"hospital": {"name": "x", "state": "CA"}})
        self.assertEqual(r.status_code, 422)  # missing required taxable_wage_per_hour


if __name__ == "__main__":
    unittest.main(verbosity=2)
