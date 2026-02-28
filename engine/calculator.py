"""
BAA Profit Commission Engine.
Supports multiple profit commission scheme types with full audit trail.
"""
from datetime import date
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any, Callable
from engine.models import (
    get_connection, get_earned_premium, get_paid_claims,
    get_ibnr, get_carrier_splits, get_prior_commission_paid,
    write_commission_record
)

# Default sliding scale
SLIDING_SCALE = [
    (0.45, 0.27),
    (0.55, 0.23),
    (0.65, 0.18),
    (0.75, 0.10),
    (1.00, 0.00),
    (999,  0.00),
]

MIN_COMMISSION_RATE = 0.05
IBNR_STALENESS_DAYS = 90
ULR_DIVERGENCE_THRESHOLD = 0.10

# Scheme type constants
SCHEME_SLIDING_SCALE = 'sliding_scale'
SCHEME_CORRIDOR = 'corridor'
SCHEME_FIXED_PLUS_VARIABLE = 'fixed_plus_variable'
SCHEME_CAPPED_SCALE = 'capped_scale'
SCHEME_CARRIER_SPECIFIC = 'carrier_specific_scale'


@dataclass
class TrueUpResult:
    """Result of a commission true-up calculation."""
    underwriting_year: int
    development_month: int
    as_of_date: str
    earned_premium: float
    paid_claims: float
    ibnr_carrier: float
    ibnr_mgu: float
    ultimate_loss_ratio: float
    commission_rate: float
    gross_commission: float
    carrier_allocations: List[Dict[str, Any]] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    floor_guard_applied: bool = False
    scheme_type: str = 'sliding_scale'


def get_commission_rate(loss_ratio: float, scheme_params: Optional[Dict] = None) -> float:
    """
    Get commission rate from sliding scale based on ultimate loss ratio.
    
    Args:
        loss_ratio: Ultimate loss ratio (claims + IBNR / earned premium)
        scheme_params: Optional scheme-specific parameters
    
    Returns:
        Commission rate from the appropriate sliding scale band
    """
    bands = SLIDING_SCALE
    if scheme_params and 'bands' in scheme_params:
        bands = scheme_params['bands']
    
    for lr_max, rate in bands:
        if loss_ratio < lr_max:
            return rate
    return 0.0


def get_corridor_rate(loss_ratio: float, scheme_params: Dict) -> float:
    """
    Calculate commission using corridor logic.
    
    0% commission between corridor bands, otherwise use rate_inside or rate_outside.
    """
    corridor_min = scheme_params.get('corridor_min', 0.0)
    corridor_max = scheme_params.get('corridor_max', 0.0)
    rate_inside = scheme_params.get('rate_inside', 0.25)
    rate_outside = scheme_params.get('rate_outside', 0.0)
    
    if corridor_min <= loss_ratio <= corridor_max:
        return rate_inside
    return rate_outside


def get_fixed_plus_variable_rate(loss_ratio: float, scheme_params: Dict) -> float:
    """
    Calculate commission using fixed + variable formula.
    
    rate = fixed_rate + (variable_rate if loss_ratio < threshold else 0)
    """
    fixed_rate = scheme_params.get('fixed_rate', 0.10)
    variable_rate = scheme_params.get('variable_rate', 0.15)
    threshold = scheme_params.get('loss_ratio_threshold', 0.60)
    
    return fixed_rate + (variable_rate if loss_ratio < threshold else 0)


def get_capped_scale_rate(loss_ratio: float, scheme_params: Dict) -> float:
    """
    Calculate commission using capped sliding scale.
    
    Applies sliding scale but caps at max_commission_pct.
    """
    rate = get_commission_rate(loss_ratio, scheme_params)
    max_rate = scheme_params.get('max_commission_pct', 0.25)
    return min(rate, max_rate)


def get_carrier_specific_rate(loss_ratio: float, carrier_id: str, scheme_params: Dict) -> float:
    """
    Calculate commission using carrier-specific sliding scale.
    
    Each carrier may have different commission bands.
    """
    scales = scheme_params.get('scales', {})
    carrier_bands = scales.get(carrier_id, SLIDING_SCALE)
    
    for lr_max, rate in carrier_bands:
        if loss_ratio < lr_max:
            return rate
    return 0.0


def get_scheme_rate(scheme_type: str, loss_ratio: float, 
                   carrier_id: Optional[str] = None,
                   scheme_params: Optional[Dict] = None) -> float:
    """
    Dispatch to the appropriate commission rate calculator based on scheme type.
    """
    if scheme_params is None:
        scheme_params = {}
    
    if scheme_type == SCHEME_SLIDING_SCALE:
        return get_commission_rate(loss_ratio, scheme_params)
    elif scheme_type == SCHEME_CORRIDOR:
        return get_corridor_rate(loss_ratio, scheme_params)
    elif scheme_type == SCHEME_FIXED_PLUS_VARIABLE:
        return get_fixed_plus_variable_rate(loss_ratio, scheme_params)
    elif scheme_type == SCHEME_CAPPED_SCALE:
        return get_capped_scale_rate(loss_ratio, scheme_params)
    elif scheme_type == SCHEME_CARRIER_SPECIFIC:
        return get_carrier_specific_rate(loss_ratio, carrier_id or 'CAR_A', scheme_params)
    else:
        # Default to sliding scale
        return get_commission_rate(loss_ratio, scheme_params)


def check_lpt_freeze(conn, carrier_id: str, underwriting_year: int, as_of_date: str) -> bool:
    """Check if carrier has an LPT event that freezes commission."""
    with conn.cursor() as cur:
        cur.execute("""
            SELECT 1 FROM lpt_events
            WHERE carrier_id = %s
              AND underwriting_year = %s
              AND effective_date <= %s
              AND freeze_commission = TRUE
            LIMIT 1
        """, (carrier_id, underwriting_year, as_of_date))
        return cur.fetchone() is not None


def run_trueup(underwriting_year: int, development_month: int, as_of_date: str,
               calc_type: str = 'true_up', write_to_db: bool = True,
               scheme_override: Optional[str] = None,
               system_as_of_timestamp: Optional[str] = None) -> TrueUpResult:
    """
    Run a commission true-up calculation for a given underwriting year and as-of date.
    
    Uses as-of semantics for:
    - Carrier splits (effective_from <= as_of_date)
    - Earned premium (txn_date <= as_of_date)
    - Paid claims (txn_date <= as_of_date)
    - IBNR (as_of_date <= eval_date)
    
    Validates carrier split sum = 1.0 ± 0.0001.
    Warns on stale IBNR and ULR divergence between carrier and MGU.
    Applies floor guard for minimum commission guarantee.
    Supports multiple scheme types.
    
    Args:
        underwriting_year: The underwriting year (e.g., 2023)
        development_month: Development month to query IBNR for (e.g., 12, 24, 36)
        as_of_date: Evaluation date (YYYY-MM-DD)
        calc_type: Type of calculation ('provisional', 'true_up', 'final')
        write_to_db: Whether to write results to commission_ledger
        scheme_override: Override scheme type for testing
        system_as_of_timestamp: Optional timestamp for historical replay
    
    Returns:
        TrueUpResult with all calculation details
    
    Raises:
        ValueError: If no earned premium, no carrier splits, or validation fails
    """
    warnings: List[str] = []
    eval_date = date.fromisoformat(as_of_date)
    conn = get_connection()
    try:
        # Get scheme parameters
        with conn.cursor() as cur:
            if scheme_override:
                cur.execute("""
                    SELECT scheme_type, parameters_json
                    FROM profit_commission_schemes
                    WHERE scheme_type = %s AND effective_from <= %s
                    ORDER BY effective_from DESC LIMIT 1
                """, (scheme_override, as_of_date))
            else:
                cur.execute("""
                    SELECT pcs.scheme_type, pcs.parameters_json
                    FROM baa_contract_versions bcv
                    JOIN profit_commission_schemes pcs ON bcv.scheme_id = pcs.scheme_id
                    WHERE bcv.underwriting_year = %s AND bcv.effective_from <= %s
                    ORDER BY bcv.effective_from DESC LIMIT 1
                """, (underwriting_year, as_of_date))
            row = cur.fetchone()
            if row:
                scheme_type = row['scheme_type']
                scheme_params = dict(row['parameters_json']) if row['parameters_json'] else {}
            else:
                scheme_type = SCHEME_SLIDING_SCALE
                scheme_params = {'min_commission_rate': MIN_COMMISSION_RATE}

        earned_premium = get_earned_premium(conn, underwriting_year, as_of_date)
        if earned_premium == 0:
            raise ValueError(f'No earned premium for UY {underwriting_year}')

        paid_claims = get_paid_claims(conn, underwriting_year, as_of_date)
        
        # Get IBNR with per-carrier support
        try:
            carrier_snap = get_ibnr(conn, underwriting_year, development_month, 'carrier_official', as_of_date)
        except ValueError:
            carrier_snap = {'ibnr_amount': 0, 'as_of_date': as_of_date, 'development_month': development_month}
            warnings.append('WARNING: No carrier IBNR found, using 0')
        
        try:
            mgu_snap = get_ibnr(conn, underwriting_year, development_month, 'mgu_internal', as_of_date)
        except ValueError:
            mgu_snap = {'ibnr_amount': 0, 'as_of_date': as_of_date, 'development_month': development_month}
            warnings.append('WARNING: No MGU IBNR found, using 0')
        
        ibnr_carrier = float(carrier_snap['ibnr_amount'])
        ibnr_mgu = float(mgu_snap['ibnr_amount'])
        actual_dev_month = carrier_snap.get('development_month', development_month)

        # Staleness check
        asof = date.fromisoformat(str(carrier_snap['as_of_date']))
        days_stale = (eval_date - asof).days
        if days_stale > IBNR_STALENESS_DAYS:
            warnings.append(f'WARNING: IBNR is {days_stale} days stale (threshold {IBNR_STALENESS_DAYS})')

        # Validate as_of_date <= eval_date
        if asof > eval_date:
            warnings.append(f'WARNING: IBNR as_of_date {asof} > eval_date {eval_date}')

        ulr = (paid_claims + ibnr_carrier) / earned_premium
        mgu_ulr = (paid_claims + ibnr_mgu) / earned_premium
        if abs(ulr - mgu_ulr) > ULR_DIVERGENCE_THRESHOLD:
            warnings.append(f'WARNING: Carrier ULR {ulr:.2%} vs MGU ULR {mgu_ulr:.2%} — divergence exceeds 10%')

        # Get commission rate using scheme engine
        commission_rate = get_scheme_rate(scheme_type, ulr, None, scheme_params)
        gross_commission = earned_premium * commission_rate
        minimum_commission = earned_premium * scheme_params.get('min_commission_rate', MIN_COMMISSION_RATE)

        # Get carrier splits
        carrier_splits = get_carrier_splits(conn, underwriting_year, as_of_date)
        if not carrier_splits:
            raise ValueError(f'No carrier splits for UY {underwriting_year}')

        # Check for negative commission settings
        allow_negative = scheme_params.get('allow_negative_commission', False)
        commission_floor_pct = scheme_params.get('commission_floor_pct', MIN_COMMISSION_RATE)
        commission_cap_pct = scheme_params.get('commission_cap_pct', 1.0)
        
        floor_guard_applied = False
        carrier_allocations: List[Dict[str, Any]] = []

        for carrier in carrier_splits:
            cid = carrier['carrier_id']
            
            # Check for LPT freeze
            if check_lpt_freeze(conn, cid, underwriting_year, as_of_date):
                warnings.append(f'WARNING: Commission frozen for {cid} due to LPT')
                carrier_allocations.append({
                    'carrier_id': cid,
                    'carrier_name': carrier['carrier_name'],
                    'participation_pct': float(carrier['participation_pct']),
                    'carrier_gross_commission': 0,
                    'prior_paid': 0,
                    'delta_payment': 0,
                    'frozen': True,
                })
                continue

            pct = float(carrier['participation_pct'])
            
            # Get carrier-specific rate if applicable
            if scheme_type == SCHEME_CARRIER_SPECIFIC:
                rate = get_scheme_rate(scheme_type, ulr, cid, scheme_params)
            else:
                rate = commission_rate
            
            carrier_gross = earned_premium * rate * pct
            prior_paid = get_prior_commission_paid(conn, underwriting_year, cid)
            delta = carrier_gross - prior_paid

            # Apply floor guard
            carrier_min = earned_premium * commission_floor_pct * pct
            if not allow_negative and prior_paid + delta < carrier_min:
                delta = carrier_min - prior_paid
                floor_guard_applied = True
                warnings.append(f'FLOOR GUARD applied for {cid} UY {underwriting_year}')

            # Apply cap
            carrier_cap = earned_premium * commission_cap_pct * pct
            if delta > carrier_cap:
                delta = carrier_cap
                warnings.append(f'CAP applied for {cid} UY {underwriting_year}')

            # Handle negative commission
            if not allow_negative and delta < 0:
                delta = 0
                warnings.append(f'NEGATIVE commission disallowed for {cid}')

            carrier_allocations.append({
                'carrier_id': cid,
                'carrier_name': carrier['carrier_name'],
                'participation_pct': pct,
                'carrier_gross_commission': carrier_gross,
                'prior_paid': prior_paid,
                'delta_payment': delta,
            })

            if write_to_db:
                write_commission_record(conn, {
                    'underwriting_year': underwriting_year,
                    'carrier_id': cid,
                    'development_month': actual_dev_month,
                    'as_of_date': as_of_date,
                    'earned_premium': round(earned_premium * pct, 2),
                    'paid_claims': round(paid_claims * pct, 2),
                    'ibnr_amount': round(ibnr_carrier * pct, 2),
                    'ultimate_loss_ratio': round(ulr, 6),
                    'commission_rate': rate,
                    'gross_commission': round(carrier_gross, 2),
                    'prior_paid_total': round(prior_paid, 2),
                    'delta_payment': round(delta, 2),
                    'floor_guard_applied': floor_guard_applied,
                    'calc_type': calc_type,
                    'carrier_split_effective_from': carrier.get('effective_from'),
                    'carrier_split_pct': pct,
                })

        return TrueUpResult(
            underwriting_year=underwriting_year,
            development_month=actual_dev_month,
            as_of_date=as_of_date,
            earned_premium=earned_premium,
            paid_claims=paid_claims,
            ibnr_carrier=ibnr_carrier,
            ibnr_mgu=ibnr_mgu,
            ultimate_loss_ratio=ulr,
            commission_rate=commission_rate,
            gross_commission=gross_commission,
            carrier_allocations=carrier_allocations,
            warnings=warnings,
            floor_guard_applied=floor_guard_applied,
            scheme_type=scheme_type,
        )
    finally:
        conn.close()
