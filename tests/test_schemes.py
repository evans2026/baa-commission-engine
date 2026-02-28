import pytest
from datetime import date, timedelta
from engine.calculator import run_trueup
from engine.schemes import (
    ProfitCommissionScheme, SlidingScaleScheme, FixedPlusVariableScheme,
    CorridorProfitScheme, CappedScaleScheme, create_scheme, get_scheme_class,
    CommissionContext, CommissionResult,
    ProfitCommissionError, MissingSchemeError, InvalidSchemeParametersError,
    UnknownSchemeTypeError, SCHEME_REGISTRY
)


class TestSchemeRegistry:
    """Tests for the scheme registry and factory."""

    def test_get_scheme_class_sliding_scale(self):
        cls = get_scheme_class('sliding_scale')
        assert cls == SlidingScaleScheme

    def test_get_scheme_class_fixed_plus_variable(self):
        cls = get_scheme_class('fixed_plus_variable')
        assert cls == FixedPlusVariableScheme

    def test_get_scheme_class_corridor(self):
        cls = get_scheme_class('corridor')
        assert cls == CorridorProfitScheme

    def test_get_scheme_class_unknown_raises(self):
        with pytest.raises(UnknownSchemeTypeError):
            get_scheme_class('unknown_type')

    def test_create_scheme_returns_instance(self):
        scheme = create_scheme('sliding_scale')
        assert isinstance(scheme, SlidingScaleScheme)


class TestSlidingScaleScheme:
    """Tests for SlidingScaleScheme."""

    def test_low_loss_ratio_high_commission(self):
        scheme = SlidingScaleScheme()
        ctx = self._make_context(earned_premium=1000000, paid_claims=100000, ibnr=50000)
        result = scheme.compute_commission(ctx, {'min_commission_rate': 0.05})
        assert result.commission_rate == 0.27

    def test_mid_loss_ratio_mid_commission(self):
        scheme = SlidingScaleScheme()
        ctx = self._make_context(earned_premium=1000000, paid_claims=400000, ibnr=200000)
        result = scheme.compute_commission(ctx, {'min_commission_rate': 0.05})
        assert result.commission_rate == 0.18

    def test_high_loss_ratio_zero_commission(self):
        scheme = SlidingScaleScheme()
        ctx = self._make_context(earned_premium=1000000, paid_claims=800000, ibnr=300000)
        result = scheme.compute_commission(ctx, {'min_commission_rate': 0.05})
        assert result.commission_rate == 0.0

    def test_floor_guard_applied(self):
        scheme = SlidingScaleScheme()
        # Very high loss ratio = 0% commission, but floor guard should apply
        ctx = self._make_context(earned_premium=100000, paid_claims=100000, ibnr=50000, prior_paid=0)
        result = scheme.compute_commission(ctx, {'min_commission_rate': 0.05})
        # Floor should apply: min 5% of 100000 * 1.0 = 5000
        assert result.floor_guard_applied == True
        assert result.delta_payment >= 5000

    def _make_context(self, earned_premium=100000, paid_claims=10000, ibnr=5000, prior_paid=0, carrier_pct=1.0):
        return CommissionContext(
            earned_premium=earned_premium,
            paid_claims=paid_claims,
            ibnr=ibnr,
            prior_paid=prior_paid,
            carrier_pct=carrier_pct,
            underwriting_year=2024,
            as_of_date='2025-01-01',
            development_month=12,
        )


class TestFixedPlusVariableScheme:
    """Tests for FixedPlusVariableScheme."""

    def test_profit_below_threshold(self):
        """When profit is below threshold, only fixed rate applies."""
        scheme = FixedPlusVariableScheme()
        # Loss: premium=100000, claims=110000, ibnr=10000 => profit = -20000
        ctx = self._make_context(earned_premium=100000, paid_claims=100000, ibnr=10000)
        result = scheme.compute_commission(ctx, {
            'fixed_rate': 0.10,
            'variable_rate': 0.20,
            'profit_threshold': 0.0,
            'min_commission_rate': 0.05
        })
        # Only fixed: 10% of 100000 = 10000
        assert result.gross_commission == 10000.0

    def test_profit_above_threshold(self):
        """When profit is above threshold, fixed + variable applies."""
        scheme = FixedPlusVariableScheme()
        # Profit: premium=100000, claims=50000, ibnr=10000 => profit = 40000
        ctx = self._make_context(earned_premium=100000, paid_claims=50000, ibnr=10000)
        result = scheme.compute_commission(ctx, {
            'fixed_rate': 0.10,
            'variable_rate': 0.20,
            'profit_threshold': 0.0,
            'min_commission_rate': 0.05
        })
        # Fixed: 10% = 10000
        # Variable: 20% of profit (40000) = 8000
        # Total: 18000
        assert result.gross_commission == 18000.0

    def test_profit_with_threshold_above_zero(self):
        """Variable only applies when profit margin > threshold."""
        scheme = FixedPlusVariableScheme()
        # Profit margin = 10%, threshold = 5%
        ctx = self._make_context(earned_premium=100000, paid_claims=85000, ibnr=5000)
        result = scheme.compute_commission(ctx, {
            'fixed_rate': 0.10,
            'variable_rate': 0.20,
            'profit_threshold': 0.05,
            'min_commission_rate': 0.05
        })
        # Fixed: 10000
        # Variable: 20% of (10%-5%)*100000 = 20% of 5000 = 1000
        # Total: 11000
        assert result.gross_commission == 11000.0

    def test_variable_cap_applied(self):
        """Variable component is capped when specified."""
        scheme = FixedPlusVariableScheme()
        # Large profit would give high variable, but capped
        ctx = self._make_context(earned_premium=100000, paid_claims=0, ibnr=0)
        result = scheme.compute_commission(ctx, {
            'fixed_rate': 0.10,
            'variable_rate': 0.50,
            'profit_threshold': 0.0,
            'variable_cap': 0.05,  # Cap at 5%
            'min_commission_rate': 0.05
        })
        # Fixed: 10000
        # Variable uncapped would be 50000, but capped at 5000
        # Total: 15000
        assert result.gross_commission == 15000.0

    def test_missing_required_param_raises(self):
        """Missing required parameter raises error."""
        scheme = FixedPlusVariableScheme()
        ctx = self._make_context()
        with pytest.raises(InvalidSchemeParametersError):
            scheme.compute_commission(ctx, {})  # missing fixed_rate

    def _make_context(self, earned_premium=100000, paid_claims=10000, ibnr=5000, prior_paid=0, carrier_pct=1.0):
        return CommissionContext(
            earned_premium=earned_premium,
            paid_claims=paid_claims,
            ibnr=ibnr,
            prior_paid=prior_paid,
            carrier_pct=carrier_pct,
            underwriting_year=2024,
            as_of_date='2025-01-01',
            development_month=12,
        )


class TestCorridorProfitScheme:
    """Tests for CorridorProfitScheme."""

    def test_inside_corridor(self):
        """ULR inside corridor gets rate_inside."""
        scheme = CorridorProfitScheme()
        ctx = self._make_context(earned_premium=100000, paid_claims=20000, ibnr=5000)
        result = scheme.compute_commission(ctx, {
            'corridor_min': 0.20,
            'corridor_max': 0.30,
            'rate_inside': 0.25,
            'rate_outside': 0.10,
            'min_commission_rate': 0.05
        })
        # ULR = 25000/100000 = 0.25, inside corridor
        assert result.commission_rate == 0.25

    def test_outside_corridor_below(self):
        """ULR below corridor gets rate_outside."""
        scheme = CorridorProfitScheme()
        ctx = self._make_context(earned_premium=100000, paid_claims=10000, ibnr=5000)
        result = scheme.compute_commission(ctx, {
            'corridor_min': 0.20,
            'corridor_max': 0.30,
            'rate_inside': 0.25,
            'rate_outside': 0.10,
            'min_commission_rate': 0.05
        })
        # ULR = 15000/100000 = 0.15, below corridor
        assert result.commission_rate == 0.10

    def test_outside_corridor_above(self):
        """ULR above corridor gets rate_outside."""
        scheme = CorridorProfitScheme()
        ctx = self._make_context(earned_premium=100000, paid_claims=35000, ibnr=5000)
        result = scheme.compute_commission(ctx, {
            'corridor_min': 0.20,
            'corridor_max': 0.30,
            'rate_inside': 0.25,
            'rate_outside': 0.10,
            'min_commission_rate': 0.05
        })
        # ULR = 40000/100000 = 0.40, above corridor
        assert result.commission_rate == 0.10

    def _make_context(self, earned_premium=100000, paid_claims=10000, ibnr=5000, prior_paid=0, carrier_pct=1.0):
        return CommissionContext(
            earned_premium=earned_premium,
            paid_claims=paid_claims,
            ibnr=ibnr,
            prior_paid=prior_paid,
            carrier_pct=carrier_pct,
            underwriting_year=2024,
            as_of_date='2025-01-01',
            development_month=12,
        )


class TestCappedScaleScheme:
    """Tests for CappedScaleScheme."""

    def test_below_cap(self):
        """Commission below cap uses sliding scale rate."""
        scheme = CappedScaleScheme()
        ctx = self._make_context(earned_premium=100000, paid_claims=10000, ibnr=5000)
        result = scheme.compute_commission(ctx, {
            'max_commission_rate': 0.20,
            'min_commission_rate': 0.05
        })
        # ULR = 15%, sliding scale gives 27%, capped at 20%
        assert result.commission_rate == 0.20

    def test_above_cap(self):
        """Commission above cap is capped."""
        scheme = CappedScaleScheme()
        ctx = self._make_context(earned_premium=100000, paid_claims=1000, ibnr=0)
        result = scheme.compute_commission(ctx, {
            'max_commission_rate': 0.20,
            'min_commission_rate': 0.05
        })
        # ULR = 1%, sliding scale gives 27%, capped at 20%
        assert result.commission_rate == 0.20

    def _make_context(self, earned_premium=100000, paid_claims=10000, ibnr=5000, prior_paid=0, carrier_pct=1.0):
        return CommissionContext(
            earned_premium=earned_premium,
            paid_claims=paid_claims,
            ibnr=ibnr,
            prior_paid=prior_paid,
            carrier_pct=carrier_pct,
            underwriting_year=2024,
            as_of_date='2025-01-01',
            development_month=12,
        )


class TestCalculatorIntegration:
    """Integration tests for the calculator with database."""

    def test_run_trueup_2023_mixed_schemes(self):
        """Test that different carriers use their assigned schemes."""
        result = run_trueup(2023, 24, '2025-01-01', write_to_db=False)
        
        # 2023 has: CAR_A sliding, CAR_B fixed+var, CAR_C sliding
        assert len(result.carrier_allocations) == 3
        
        car_a = [a for a in result.carrier_allocations if a['carrier_id'] == 'CAR_A'][0]
        car_b = [a for a in result.carrier_allocations if a['carrier_id'] == 'CAR_B'][0]
        
        assert car_a['scheme_type'] == 'sliding_scale'
        assert car_b['scheme_type'] == 'fixed_plus_variable'

    def test_run_trueup_2024_all_fixed_plus_variable(self):
        """Test 2024 uses fixed+variable for all carriers (use dev=12 which has IBNR)."""
        result = run_trueup(2024, 12, '2025-01-01', write_to_db=False)
        
        # 2024 has: CAR_A fixed+var, CAR_C fixed+var
        for alloc in result.carrier_allocations:
            assert alloc['scheme_type'] == 'fixed_plus_variable'

    def test_run_trueup_2022_all_sliding_scale(self):
        """Test 2022 uses sliding scale for all carriers."""
        result = run_trueup(2022, 24, '2025-01-01', write_to_db=False)
        
        for alloc in result.carrier_allocations:
            assert alloc['scheme_type'] == 'sliding_scale'


class TestErrorHandling:
    """Tests for domain error handling."""

    def test_unknown_scheme_type_raises(self):
        with pytest.raises(UnknownSchemeTypeError):
            get_scheme_class('invalid_scheme')
    
    def test_create_invalid_scheme_raises(self):
        with pytest.raises(UnknownSchemeTypeError):
            create_scheme('does_not_exist')
