"""
BAA Profit Commission Calculator.
Uses pluggable scheme architecture for multiple commission types.
"""
from datetime import date
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any
from engine.models import (
    get_connection, get_earned_premium, get_paid_claims,
    get_ibnr, get_carrier_splits, get_prior_commission_paid,
    write_commission_record
)
from engine.schemes import (
    ProfitCommissionScheme, create_scheme, CommissionContext, CommissionResult,
    ProfitCommissionError, MissingSchemeError, CarrierSplitsError,
    NoEarnedPremiumError, NoIBNRSnapshotError, UnknownSchemeTypeError,
    InvalidSchemeParametersError, SCHEME_REGISTRY
)

# Constants
MIN_COMMISSION_RATE = 0.05
IBNR_STALENESS_DAYS = 90
ULR_DIVERGENCE_THRESHOLD = 0.10


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


def get_carrier_scheme(conn, underwriting_year: int, carrier_id: str, as_of_date: str) -> tuple:
    """
    Get the scheme for a specific carrier in a given UY as of a date.
    
    Returns tuple of (scheme_type, scheme_params)
    
    Raises:
        MissingSchemeError: If no scheme is defined
    """
    with conn.cursor() as cur:
        cur.execute("""
            SELECT scheme_type, parameters_json
            FROM carrier_schemes
            WHERE underwriting_year = %s 
              AND carrier_id = %s
              AND effective_from <= %s
            ORDER BY effective_from DESC, system_timestamp DESC
            LIMIT 1
        """, (underwriting_year, carrier_id, as_of_date))
        row = cur.fetchone()
        
        if row is None:
            # Fallback to default scheme from contract_versions
            cur.execute("""
                SELECT pcs.scheme_type, pcs.parameters_json
                FROM baa_contract_versions bcv
                JOIN profit_commission_schemes pcs ON bcv.scheme_id = pcs.scheme_id
                WHERE bcv.underwriting_year = %s AND bcv.effective_from <= %s
                ORDER BY bcv.effective_from DESC LIMIT 1
            """, (underwriting_year, as_of_date))
            row = cur.fetchone()
            
            if row is None:
                # Use default sliding scale
                return ('sliding_scale', {'min_commission_rate': MIN_COMMISSION_RATE})
        
        scheme_type = row['scheme_type']
        scheme_params = dict(row['parameters_json']) if row['parameters_json'] else {}
        return (scheme_type, scheme_params)


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
               calc_type: str = 'true_up', write_to_db: bool = True) -> TrueUpResult:
    """
    Run a commission true-up calculation for a given underwriting year and as-of date.
    
    Uses pluggable scheme architecture - each carrier can have different scheme.
    
    Args:
        underwriting_year: The underwriting year (e.g., 2023)
        development_month: Development month to query IBNR for (e.g., 12, 24, 36)
        as_of_date: Evaluation date (YYYY-MM-DD)
        calc_type: Type of calculation ('provisional', 'true_up', 'final')
        write_to_db: Whether to write results to commission_ledger
    
    Returns:
        TrueUpResult with all calculation details
    
    Raises:
        ProfitCommissionError: On various error conditions
    """
    warnings: List[str] = []
    eval_date = date.fromisoformat(as_of_date)
    conn = get_connection()
    try:
        # Get earned premium
        earned_premium = get_earned_premium(conn, underwriting_year, as_of_date)
        if earned_premium == 0:
            raise NoEarnedPremiumError(f'No earned premium for UY {underwriting_year}')

        # Get paid claims
        paid_claims = get_paid_claims(conn, underwriting_year, as_of_date)
        
        # Get IBNR
        try:
            carrier_snap = get_ibnr(conn, underwriting_year, development_month, 'carrier_official', as_of_date)
        except ValueError:
            raise NoIBNRSnapshotError(f'No carrier IBNR for UY={underwriting_year} dev={development_month}')
        
        try:
            mgu_snap = get_ibnr(conn, underwriting_year, development_month, 'mgu_internal', as_of_date)
        except ValueError:
            mgu_snap = {'ibnr_amount': 0, 'as_of_date': as_of_date}
        
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

        # Get carrier splits
        carrier_splits = get_carrier_splits(conn, underwriting_year, as_of_date)
        if not carrier_splits:
            raise CarrierSplitsError(f'No carrier splits for UY {underwriting_year}')

        floor_guard_applied = False
        carrier_allocations: List[Dict[str, Any]] = []
        total_gross = 0.0
        scheme_type_used = None

        for carrier in carrier_splits:
            cid = carrier['carrier_id']
            pct = float(carrier['participation_pct'])
            
            # Check for LPT freeze
            if check_lpt_freeze(conn, cid, underwriting_year, as_of_date):
                warnings.append(f'WARNING: Commission frozen for {cid} due to LPT')
                carrier_allocations.append({
                    'carrier_id': cid,
                    'carrier_name': carrier['carrier_name'],
                    'participation_pct': pct,
                    'carrier_gross_commission': 0,
                    'prior_paid': 0,
                    'delta_payment': 0,
                    'frozen': True,
                    'scheme_type': 'lpt_frozen',
                })
                continue

            # Get carrier-specific scheme
            scheme_type, scheme_params = get_carrier_scheme(conn, underwriting_year, cid, as_of_date)
            scheme_type_used = scheme_type
            
            # Create scheme instance
            try:
                scheme = create_scheme(scheme_type)
            except UnknownSchemeTypeError as e:
                # Fallback to sliding scale
                scheme = create_scheme('sliding_scale')
                warnings.append(f'WARNING: Unknown scheme {scheme_type} for {cid}, using sliding scale')

            # Build context
            context = CommissionContext(
                earned_premium=earned_premium,
                paid_claims=paid_claims,
                ibnr=ibnr_carrier,
                prior_paid=get_prior_commission_paid(conn, underwriting_year, cid),
                carrier_pct=pct,
                underwriting_year=underwriting_year,
                as_of_date=as_of_date,
                development_month=actual_dev_month,
            )

            # Compute commission using scheme
            try:
                result = scheme.compute_commission(context, scheme_params)
            except InvalidSchemeParametersError as e:
                warnings.append(f'WARNING: Invalid params for {cid}: {e}, using defaults')
                scheme = create_scheme('sliding_scale')
                result = scheme.compute_commission(context, {'min_commission_rate': MIN_COMMISSION_RATE})

            if result.floor_guard_applied:
                floor_guard_applied = True
            
            total_gross += result.gross_commission * pct
            
            carrier_allocations.append({
                'carrier_id': cid,
                'carrier_name': carrier['carrier_name'],
                'participation_pct': pct,
                'carrier_gross_commission': result.gross_commission * pct,
                'prior_paid': context.prior_paid,
                'delta_payment': result.delta_payment,
                'scheme_type': scheme_type,
                'commission_rate': result.commission_rate,
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
                    'commission_rate': result.commission_rate,
                    'gross_commission': round(result.gross_commission * pct, 2),
                    'prior_paid_total': round(context.prior_paid, 2),
                    'delta_payment': round(result.delta_payment, 2),
                    'floor_guard_applied': result.floor_guard_applied,
                    'calc_type': calc_type,
                    'carrier_split_effective_from': carrier.get('effective_from'),
                    'carrier_split_pct': pct,
                })

        # Compute effective commission rate (total gross / earned premium)
        effective_rate = total_gross / earned_premium if earned_premium > 0 else 0.0

        return TrueUpResult(
            underwriting_year=underwriting_year,
            development_month=actual_dev_month,
            as_of_date=as_of_date,
            earned_premium=earned_premium,
            paid_claims=paid_claims,
            ibnr_carrier=ibnr_carrier,
            ibnr_mgu=ibnr_mgu,
            ultimate_loss_ratio=ulr,
            commission_rate=effective_rate,
            gross_commission=total_gross,
            carrier_allocations=carrier_allocations,
            warnings=warnings,
            floor_guard_applied=floor_guard_applied,
            scheme_type=scheme_type_used or 'sliding_scale',
        )
    finally:
        conn.close()


# Export for backward compatibility
def get_commission_rate(loss_ratio: float, scheme_params: Optional[Dict] = None) -> float:
    """Legacy function for backward compatibility."""
    from engine.schemes import SlidingScaleScheme
    scheme = SlidingScaleScheme()
    result = scheme.compute_commission(
        CommissionContext(
            earned_premium=1.0,
            paid_claims=loss_ratio,
            ibnr=0,
            prior_paid=0,
            carrier_pct=1.0,
            underwriting_year=2024,
            as_of_date='2025-01-01',
            development_month=12,
        ),
        scheme_params or {}
    )
    return result.commission_rate
