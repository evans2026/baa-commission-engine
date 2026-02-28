import pytest
from engine.calculator import get_commission_rate, MIN_COMMISSION_RATE, SLIDING_SCALE

class TestSlidingScale:
    def test_lowest_band(self):
        assert get_commission_rate(0.30) == 0.27
    def test_second_band(self):
        assert get_commission_rate(0.50) == 0.23
    def test_third_band(self):
        assert get_commission_rate(0.60) == 0.18
    def test_fourth_band(self):
        assert get_commission_rate(0.70) == 0.10
    def test_zero_commission(self):
        assert get_commission_rate(0.80) == 0.00
    def test_loss_scenario(self):
        assert get_commission_rate(1.20) == 0.00
    def test_zero_loss_ratio(self):
        assert get_commission_rate(0.00) == 0.27

class TestTrueUpNoDb:
    def test_basic_calculation_runs(self):
        from engine.calculator import run_trueup
        result = run_trueup(2023, 24, '2025-01-01', write_to_db=False)
        assert result.earned_premium > 0
        assert result.ultimate_loss_ratio >= 0
        assert 0.0 <= result.commission_rate <= 0.27

    def test_carrier_allocations_sum_to_gross(self):
        from engine.calculator import run_trueup
        result = run_trueup(2023, 24, '2025-01-01', write_to_db=False)
        total = sum(a['carrier_gross_commission'] for a in result.carrier_allocations)
        assert abs(total - result.gross_commission) < 0.01

    def test_ulr_formula_correct(self):
        from engine.calculator import run_trueup
        result = run_trueup(2023, 24, '2025-01-01', write_to_db=False)
        expected = (result.paid_claims + result.ibnr_carrier) / result.earned_premium
        assert abs(result.ultimate_loss_ratio - expected) < 0.000001

    def test_all_three_underwriting_years(self):
        from engine.calculator import run_trueup
        for uy in [2022, 2023, 2024]:
            result = run_trueup(uy, 12, f'{uy+1}-01-01', write_to_db=False)
            assert result.earned_premium > 0
