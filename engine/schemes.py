"""
BAA Profit Commission Engine.
Modular, pluggable architecture for multiple profit commission scheme types.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any
from datetime import date


# =============================================================================
# Domain Exceptions
# =============================================================================

class ProfitCommissionError(Exception):
    """Base exception for profit commission errors."""
    pass


class MissingSchemeError(ProfitCommissionError):
    """Raised when no scheme is defined for a carrier/UY."""
    pass


class InvalidSchemeParametersError(ProfitCommissionError):
    """Raised when scheme parameters are invalid."""
    pass


class UnknownSchemeTypeError(ProfitCommissionError):
    """Raised when scheme type is not recognized."""
    pass


class CarrierSplitsError(ProfitCommissionError):
    """Raised when carrier splits are missing or invalid."""
    pass


class NoEarnedPremiumError(ProfitCommissionError):
    """Raised when there's no earned premium."""
    pass


class NoIBNRSnapshotError(ProfitCommissionError):
    """Raised when no IBNR snapshot is available."""
    pass


# =============================================================================
# Scheme Base Class and Subclasses
# =============================================================================

@dataclass
class CommissionContext:
    """Context passed to scheme compute_commission method."""
    earned_premium: float
    paid_claims: float
    ibnr: float
    prior_paid: float
    carrier_pct: float
    underwriting_year: int
    as_of_date: str
    development_month: int
    allow_negative_commission: bool = False


@dataclass
class CommissionResult:
    """Result from computing commission."""
    commission_rate: float
    gross_commission: float
    delta_payment: float
    floor_guard_applied: bool = False
    warnings: List[str] = field(default_factory=list)


class ProfitCommissionScheme(ABC):
    """Base class for all profit commission schemes."""
    
    SCHEME_TYPE: str = "base"
    
    @abstractmethod
    def compute_commission(self, context: CommissionContext, params: Dict) -> CommissionResult:
        """
        Compute commission for a given context.
        
        Args:
            context: CommissionContext with all inputs
            params: Scheme parameters from database
            
        Returns:
            CommissionResult with calculated values
        """
        raise NotImplementedError
    
    def validate_params(self, params: Dict) -> None:
        """Validate scheme parameters. Raise InvalidSchemeParametersError if invalid."""
        pass


class SlidingScaleScheme(ProfitCommissionScheme):
    """Sliding scale profit commission scheme."""
    
    SCHEME_TYPE = "sliding_scale"
    
    DEFAULT_BANDS = [
        (0.45, 0.27),
        (0.55, 0.23),
        (0.65, 0.18),
        (0.75, 0.10),
        (1.00, 0.00),
        (999, 0.00),
    ]
    
    def compute_commission(self, context: CommissionContext, params: Dict) -> CommissionResult:
        # Get bands from params or use default
        bands = params.get('bands', self.DEFAULT_BANDS)
        
        # Calculate ULR
        ulr = (context.paid_claims + context.ibnr) / context.earned_premium
        
        # Find commission rate from bands
        commission_rate = 0.0
        for lr_max, rate in bands:
            if ulr < lr_max:
                commission_rate = rate
                break
        
        # Calculate gross commission
        gross_commission = context.earned_premium * commission_rate
        carrier_gross = gross_commission * context.carrier_pct
        
        # Apply floor guard
        min_rate = params.get('min_commission_rate', 0.05)
        minimum_commission = context.earned_premium * min_rate * context.carrier_pct
        floor_guard_applied = False
        
        delta = carrier_gross - context.prior_paid
        
        # Handle negative commission based on allow_negative_commission flag
        if not context.allow_negative_commission and delta < 0:
            delta = 0
        
        # Apply floor guard if not allowing negatives or if still below minimum
        if not context.allow_negative_commission and context.prior_paid + delta < minimum_commission:
            delta = minimum_commission - context.prior_paid
            floor_guard_applied = True
        
        return CommissionResult(
            commission_rate=commission_rate,
            gross_commission=gross_commission,
            delta_payment=delta,
            floor_guard_applied=floor_guard_applied
        )


class FixedPlusVariableScheme(ProfitCommissionScheme):
    """Fixed + Variable profit commission scheme."""
    
    SCHEME_TYPE = "fixed_plus_variable"
    
    def validate_params(self, params: Dict) -> None:
        required = ['fixed_rate']
        for field in required:
            if field not in params:
                raise InvalidSchemeParametersError(f"Missing required parameter: {field}")
    
    def compute_commission(self, context: CommissionContext, params: Dict) -> CommissionResult:
        self.validate_params(params)
        
        # Get parameters
        fixed_rate = params.get('fixed_rate', 0.10)
        variable_rate = params.get('variable_rate', 0.15)
        profit_threshold = params.get('profit_threshold', 0.0)
        variable_cap = params.get('variable_cap', None)  # Optional cap
        
        # Calculate underwriting profit
        total_loss = context.paid_claims + context.ibnr
        underwriting_profit = context.earned_premium - total_loss
        profit_margin = underwriting_profit / context.earned_premium if context.earned_premium > 0 else 0
        
        # Fixed commission
        fixed_commission = context.earned_premium * fixed_rate * context.carrier_pct
        
        # Variable commission (profit share)
        variable_commission = 0.0
        if profit_margin > profit_threshold:
            # Profit above threshold is shared
            profit_above_threshold = (profit_margin - profit_threshold) * context.earned_premium
            variable_commission = profit_above_threshold * variable_rate * context.carrier_pct
        
        # Apply cap if specified
        if variable_cap is not None:
            variable_cap_amount = context.earned_premium * variable_cap * context.carrier_pct
            variable_commission = min(variable_commission, variable_cap_amount)
        
        gross_commission = fixed_commission + variable_commission
        
        # Apply floor guard
        min_rate = params.get('min_commission_rate', 0.05)
        minimum_commission = context.earned_premium * min_rate * context.carrier_pct
        floor_guard_applied = False
        
        delta = gross_commission - context.prior_paid
        if context.prior_paid + delta < minimum_commission:
            delta = minimum_commission - context.prior_paid
            floor_guard_applied = True
        
        return CommissionResult(
            commission_rate=(fixed_rate + variable_commission / context.earned_premium) if context.earned_premium > 0 else 0,
            gross_commission=fixed_commission + variable_commission,
            delta_payment=delta,
            floor_guard_applied=floor_guard_applied
        )


class CorridorProfitScheme(ProfitCommissionScheme):
    """Corridor-based profit share scheme."""
    
    SCHEME_TYPE = "corridor"
    
    def validate_params(self, params: Dict) -> None:
        required = ['corridor_min', 'corridor_max', 'rate_inside', 'rate_outside']
        for field in required:
            if field not in params:
                raise InvalidSchemeParametersError(f"Missing required parameter: {field}")
    
    def compute_commission(self, context: CommissionContext, params: Dict) -> CommissionResult:
        self.validate_params(params)
        
        # Get parameters
        corridor_min = params.get('corridor_min', 0.0)
        corridor_max = params.get('corridor_max', 0.0)
        rate_inside = params.get('rate_inside', 0.25)
        rate_outside = params.get('rate_outside', 0.0)
        
        # Calculate ULR
        ulr = (context.paid_claims + context.ibnr) / context.earned_premium
        
        # Determine if inside or outside corridor
        if corridor_min <= ulr <= corridor_max:
            commission_rate = rate_inside
        else:
            commission_rate = rate_outside
        
        gross_commission = context.earned_premium * commission_rate
        carrier_gross = gross_commission * context.carrier_pct
        
        # Apply floor guard
        min_rate = params.get('min_commission_rate', 0.05)
        minimum_commission = context.earned_premium * min_rate * context.carrier_pct
        floor_guard_applied = False
        
        delta = carrier_gross - context.prior_paid
        if context.prior_paid + delta < minimum_commission:
            delta = minimum_commission - context.prior_paid
            floor_guard_applied = True
        
        return CommissionResult(
            commission_rate=commission_rate,
            gross_commission=gross_commission,
            delta_payment=delta,
            floor_guard_applied=floor_guard_applied
        )


class CappedScaleScheme(ProfitCommissionScheme):
    """Capped sliding scale scheme."""
    
    SCHEME_TYPE = "capped_scale"
    
    def compute_commission(self, context: CommissionContext, params: Dict) -> CommissionResult:
        # Use sliding scale first
        sliding = SlidingScaleScheme()
        result = sliding.compute_commission(context, params)
        
        # Apply cap
        max_rate = params.get('max_commission_rate', 0.25)
        if result.commission_rate > max_rate:
            result.commission_rate = max_rate
            result.gross_commission = context.earned_premium * max_rate
            carrier_gross = result.gross_commission * context.carrier_pct
            
            min_rate = params.get('min_commission_rate', 0.05)
            minimum_commission = context.earned_premium * min_rate * context.carrier_pct
            delta = carrier_gross - context.prior_paid
            if context.prior_paid + delta < minimum_commission:
                delta = minimum_commission - context.prior_paid
                result.floor_guard_applied = True
            result.delta_payment = delta
        
        return result


# =============================================================================
# Scheme Registry
# =============================================================================

SCHEME_REGISTRY: Dict[str, type] = {
    "sliding_scale": SlidingScaleScheme,
    "fixed_plus_variable": FixedPlusVariableScheme,
    "corridor": CorridorProfitScheme,
    "capped_scale": CappedScaleScheme,
}


def get_scheme_class(scheme_type: str) -> type:
    """Get the scheme class for a given type."""
    if scheme_type not in SCHEME_REGISTRY:
        raise UnknownSchemeTypeError(f"Unknown scheme type: {scheme_type}")
    return SCHEME_REGISTRY[scheme_type]


def create_scheme(scheme_type: str) -> ProfitCommissionScheme:
    """Factory function to create a scheme instance."""
    return get_scheme_class(scheme_type)()


# =============================================================================
# Scheme Type Constants (for backward compatibility)
# =============================================================================

SCHEME_SLIDING_SCALE = "sliding_scale"
SCHEME_FIXED_PLUS_VARIABLE = "fixed_plus_variable"
SCHEME_CORRIDOR = "corridor"
SCHEME_CAPPED_SCALE = "capped_scale"
SCHEME_CARRIER_SPECIFIC = "carrier_specific_scale"


def get_scheme_rate(scheme_type: str, loss_ratio: float, 
                   carrier_id: Optional[str] = None,
                   scheme_params: Optional[Dict] = None) -> float:
    """
    Dispatch to the appropriate commission rate calculator based on scheme type.
    
    For backward compatibility with existing tests.
    """
    if scheme_params is None:
        scheme_params = {}
    
    scheme = create_scheme(scheme_type)
    ctx = CommissionContext(
        earned_premium=1.0,
        paid_claims=loss_ratio,
        ibnr=0,
        prior_paid=0,
        carrier_pct=1.0,
        underwriting_year=2024,
        as_of_date='2025-01-01',
        development_month=12,
    )
    result = scheme.compute_commission(ctx, scheme_params)
    return result.commission_rate
