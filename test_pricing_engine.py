"""
Unit tests for the v2 pricing engine.

Run with: python3 -m pytest test_pricing_engine.py -v
Or directly: python3 test_pricing_engine.py
"""

from __future__ import annotations

import math
import unittest

from pricing_engine import (
    Calibration, Channel, CohortMix, HospitalProfile, PricingMode,
    EMPLOYER_SS_RATE, EMPLOYER_MEDICARE_RATE,
    REQUIRED_COMPLIANCE_SENTENCE,
    price, render_evidence_pack,
)


def kaiser_like() -> HospitalProfile:
    """A Kaiser-class hospital profile for testing."""
    return HospitalProfile(
        name="Test Hospital", city="Test City", state="CA",
        taxable_wage_per_hour=66.85, benefit_load_per_hour=17.50,
        all_in_agency_per_hour=121.73,  # Kaiser median post-overlay
        agency_rate_confidence=0.92,
        agency_rate_source="hcris_nmrc",
    )


def low_premium() -> HospitalProfile:
    """A hospital where agency premium is small."""
    return HospitalProfile(
        name="Tight Hospital", city="X", state="AR",
        taxable_wage_per_hour=36.0, benefit_load_per_hour=10.0,
        all_in_agency_per_hour=52.0,
        agency_rate_confidence=0.92,
        agency_rate_source="hcris_nmrc",
    )


def negative_premium() -> HospitalProfile:
    """A hospital where agency rate is BELOW staff cost (manual review)."""
    return HospitalProfile(
        name="Manual Review Case", city="X", state="X",
        taxable_wage_per_hour=80, benefit_load_per_hour=25,
        all_in_agency_per_hour=70,  # below loaded staff
        agency_rate_confidence=0.92,
        agency_rate_source="hcris_nmrc",
    )


def low_confidence() -> HospitalProfile:
    """A hospital with low-confidence agency rate."""
    return HospitalProfile(
        name="Low Conf Hospital", city="X", state="X",
        taxable_wage_per_hour=40, benefit_load_per_hour=12,
        all_in_agency_per_hour=85,
        agency_rate_confidence=0.40,
        agency_rate_source="national_imputed",
    )


class TestPricingFormula(unittest.TestCase):
    """v2 §6.2 FICA_OFFSET_TARGET pricing math."""

    def test_default_calibration_constants(self):
        cal = Calibration()
        self.assertEqual(cal.pricing_mode, PricingMode.FICA_OFFSET_TARGET)
        self.assertEqual(cal.target_offset_pct, 0.40)
        self.assertEqual(cal.price_floor_monthly, 750)
        self.assertEqual(cal.price_ceiling_monthly, 2000)
        self.assertEqual(cal.term_months, 24)
        self.assertEqual(cal.annual_hours_rn, 1872)
        self.assertEqual(cal.monthly_hours_rn, 156)

    def test_fica_offset_target_at_target(self):
        """When suggested fee falls within floor/ceiling, it equals FICA / target_offset_pct."""
        result = price(kaiser_like(), CohortMix(eta=1.0), Calibration())
        # FICA savings / 0.40 should = monthly fee (under the 40% target)
        expected_fee = result.employer_fica_savings_per_rn_per_month / 0.40
        # Should hit target exactly (not floor or ceiling)
        if 750 <= expected_fee <= 2000:
            self.assertAlmostEqual(
                result.florence_monthly_fee_per_rn,
                expected_fee,
                places=2,
                msg="Fee should equal FICA / target_offset_pct when no clamping",
            )
            self.assertAlmostEqual(result.actual_fica_offset_pct, 0.40, places=3)

    def test_floor_binds_when_fica_too_low(self):
        cal = Calibration()
        p = HospitalProfile(
            name="t", city="x", state="x",
            taxable_wage_per_hour=22.0, benefit_load_per_hour=6.0,
            all_in_agency_per_hour=60.0,
            agency_rate_confidence=0.92,
        )
        r = price(p, CohortMix(eta=1.0), cal)
        # Wage $22 → annual $41K → FICA savings ~$3.2K/yr = $263/mo
        # Suggested = $263/0.5 = $526; clamped to $750 floor
        self.assertEqual(r.final_fee_constrained_by, "floor")
        self.assertEqual(r.florence_monthly_fee_per_rn, 750)

    def test_ceiling_binds_when_fica_too_high(self):
        cal = Calibration()
        # Need FICA × 2 > $2,000 → FICA > $1,000/mo → annual > $12K
        # Annual = wage × 1872. Wage > $12K / 1872 / .0765 ~ $84/hr
        p = HospitalProfile(
            name="t", city="x", state="x",
            taxable_wage_per_hour=95.0, benefit_load_per_hour=25.0,
            all_in_agency_per_hour=200.0,  # high premium so we test ceiling not floor
            agency_rate_confidence=0.92,
        )
        r = price(p, CohortMix(eta=1.0), cal)
        self.assertEqual(r.final_fee_constrained_by, "ceiling")
        self.assertEqual(r.florence_monthly_fee_per_rn, 2000)


class TestManualReview(unittest.TestCase):
    """v2 §10 manual-review logic."""

    def test_negative_premium_triggers_manual_review(self):
        r = price(negative_premium(), CohortMix(eta=1.0), Calibration())
        self.assertTrue(r.manual_review_flag)
        self.assertEqual(r.channel, Channel.NO_QUOTE)
        self.assertEqual(r.florence_monthly_fee_per_rn, 0)
        self.assertFalse(r.feasible)

    def test_low_confidence_falls_back_to_standard(self):
        cal = Calibration(use_standard_fee_for_low_confidence=True)
        r = price(low_confidence(), CohortMix(eta=1.0), cal)
        # Should NOT trigger manual review; should use STANDARD_FEE
        self.assertFalse(r.manual_review_flag)
        self.assertEqual(r.florence_monthly_fee_per_rn, cal.standard_monthly_fee)
        self.assertEqual(r.final_fee_constrained_by, "low_confidence_standard")

    def test_zero_agency_rate_triggers_manual_review(self):
        p = HospitalProfile(
            name="t", city="x", state="x",
            taxable_wage_per_hour=50.0, benefit_load_per_hour=15.0,
            all_in_agency_per_hour=0.0,
            agency_rate_confidence=0.92,
        )
        r = price(p, CohortMix(eta=1.0), Calibration())
        self.assertTrue(r.manual_review_flag)


class TestFICACalculation(unittest.TestCase):
    """v2 §5.6 employer FICA savings calculation."""

    def test_fica_below_ss_wage_base(self):
        cal = Calibration()
        p = kaiser_like()  # $66.85/hr × 1872 = $125K < $184.5K wage base
        annual_wage = p.taxable_wage_per_hour * cal.annual_hours_rn
        expected_annual_fica = (
            annual_wage * EMPLOYER_SS_RATE
            + annual_wage * EMPLOYER_MEDICARE_RATE
        )
        expected_monthly = expected_annual_fica / 12
        r = price(p, CohortMix(eta=1.0), cal)
        self.assertAlmostEqual(
            r.employer_fica_savings_per_rn_per_month, expected_monthly, places=2
        )

    def test_fica_above_ss_wage_base(self):
        """Above SS wage base, SS portion caps but Medicare keeps going."""
        cal = Calibration()
        p = HospitalProfile(
            name="t", city="x", state="x",
            taxable_wage_per_hour=120.0,  # $120 × 1872 = $224K > $184.5K cap
            benefit_load_per_hour=30, all_in_agency_per_hour=200.0,
            agency_rate_confidence=0.92,
        )
        annual = 120 * 1872
        expected = (
            EMPLOYER_SS_RATE * min(annual, cal.ss_wage_base)
            + EMPLOYER_MEDICARE_RATE * annual
        ) / 12
        r = price(p, CohortMix(eta=1.0), cal)
        self.assertAlmostEqual(
            r.employer_fica_savings_per_rn_per_month, expected, places=2
        )

    def test_eta_zero_yields_zero_fica(self):
        r = price(kaiser_like(), CohortMix(eta=0.0), Calibration())
        self.assertAlmostEqual(r.employer_fica_savings_per_rn_per_month, 0.0, places=2)


class TestRevenueSplit(unittest.TestCase):
    """v2 partner-markup handling — margin is ADDED ATOP Florence's protected core fee."""

    def test_direct_channel_zero_partner(self):
        cal = Calibration(direct_partner_markup_pct=0.0)
        r = price(kaiser_like(), CohortMix(eta=1.0), cal)
        self.assertEqual(r.partner_share, 0.0)
        self.assertEqual(r.partner_revenue_monthly, 0)
        # Florence's net always equals the protected core fee
        self.assertAlmostEqual(r.florence_net_monthly, r.florence_monthly_fee_per_rn, places=2)

    def test_partner_markup_20pct(self):
        cal = Calibration(direct_partner_markup_pct=0.20)  # 20% markup atop core (direct channel)
        r = price(kaiser_like(), CohortMix(eta=1.0), cal)
        self.assertAlmostEqual(r.partner_share, 0.20, places=4)
        # partner margin = core fee × markup; Florence net is unchanged (protected)
        self.assertAlmostEqual(
            r.partner_revenue_monthly,
            r.florence_monthly_fee_per_rn * 0.20,
            places=2,
        )
        self.assertAlmostEqual(r.florence_net_monthly, r.florence_monthly_fee_per_rn, places=2)


class TestImmigrationAddon(unittest.TestCase):
    """v2 §6.5 immigration transition add-on."""

    def test_addon_disabled_by_default(self):
        r = price(kaiser_like(), CohortMix(eta=1.0), Calibration())
        self.assertEqual(r.immigration_addon_monthly, 0)
        self.assertEqual(r.all_in_florence_fee_per_rn_month, r.florence_monthly_fee_per_rn)

    def test_addon_enabled_adds_208(self):
        cal = Calibration(immigration_addon_enabled=True)
        r = price(kaiser_like(), CohortMix(eta=1.0), cal)
        self.assertAlmostEqual(r.immigration_addon_monthly, 5000 / 24, places=2)
        self.assertAlmostEqual(
            r.all_in_florence_fee_per_rn_month,
            r.florence_monthly_fee_per_rn + (5000 / 24),
            places=2,
        )


class TestRollupConsistency(unittest.TestCase):
    """v2 §7 rollup math — additive sums must equal per-RN × RN need."""

    def test_term_florence_fee_equals_monthly_times_term(self):
        r = price(kaiser_like(), CohortMix(eta=1.0), Calibration())
        expected = r.florence_monthly_fee_per_rn * r.term_months
        self.assertAlmostEqual(r.term_florence_fee_per_rn, expected, places=2)

    def test_net_savings_formula(self):
        """v2 §6.6: Net = AgencyAvoided + FICA − Fee"""
        r = price(kaiser_like(), CohortMix(eta=1.0), Calibration())
        expected = (
            r.monthly_agency_premium_avoided_per_rn
            + r.employer_fica_savings_per_rn_per_month
            - r.florence_monthly_fee_per_rn
        )
        self.assertAlmostEqual(r.net_monthly_savings_per_rn, expected, places=2)

    def test_fica_adjusted_cost_formula(self):
        """v2 §1: FICA-Adjusted Effective Cost = Fee − FICA"""
        r = price(kaiser_like(), CohortMix(eta=1.0), Calibration())
        expected = (
            r.florence_monthly_fee_per_rn
            - r.employer_fica_savings_per_rn_per_month
        )
        self.assertAlmostEqual(r.fica_adjusted_effective_cost_per_rn_month, expected, places=2)


class TestComplianceStatement(unittest.TestCase):
    """v2 required compliance sentence must be present in every output."""

    def test_compliance_sentence_in_evidence_pack(self):
        r = price(kaiser_like(), CohortMix(eta=1.0), Calibration())
        pack = render_evidence_pack(r)
        # The exact wording must appear (per v2 §11). Collapse whitespace for the
        # substring check since textwrap may have inserted line breaks.
        flat = " ".join(pack.split())
        self.assertIn("Estimated employer-side FICA offset", flat)
        self.assertIn("validated by payroll, tax counsel, and immigration", flat)
        self.assertIn("nurse take-home benefit", flat)


if __name__ == "__main__":
    unittest.main(verbosity=2)
