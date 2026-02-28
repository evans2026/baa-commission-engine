"""
BAA Profit Commission True-Up Calculator.
Sliding scale, floor guard, carrier split allocation, audit ledger write.
"""
from datetime import date
from dataclasses import dataclass, field
from typing import Optional
from engine.models import (
    get_connection, get_earned_premium, get_paid_claims,
    get_ibnr, get_carrier_splits, get_prior_commission_paid,
    write_commission_record
)

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

@dataclass
class TrueUpResult:
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
    carrier_allocations: list = field(default_factory=list)
    warnings: list = field(default_factory=list)
    floor_guard_applied: bool = False

def get_commission_rate(loss_ratio):
    for lr_max, rate in SLIDING_SCALE:
        if loss_ratio < lr_max:
            return rate
    return 0.0

def run_trueup(underwriting_year, development_month, as_of_date,
               calc_type='true_up', write_to_db=True):
    warnings = []
    eval_date = date.fromisoformat(as_of_date)
    conn = get_connection()
    try:
        earned_premium = get_earned_premium(conn, underwriting_year, as_of_date)
        if earned_premium == 0:
            raise ValueError(f'No earned premium for UY {underwriting_year}')

        paid_claims = get_paid_claims(conn, underwriting_year, as_of_date)
        carrier_snap = get_ibnr(conn, underwriting_year, development_month, 'carrier_official', as_of_date)
        mgu_snap = get_ibnr(conn, underwriting_year, development_month, 'mgu_internal', as_of_date)
        ibnr_carrier = float(carrier_snap['ibnr_amount'])
        ibnr_mgu = float(mgu_snap['ibnr_amount'])
        actual_dev_month = carrier_snap['development_month']

        asof = date.fromisoformat(str(carrier_snap['as_of_date']))
        days_stale = (eval_date - asof).days
        if days_stale > IBNR_STALENESS_DAYS:
            warnings.append(f'WARNING: IBNR is {days_stale} days stale (threshold {IBNR_STALENESS_DAYS})')

        ulr = (paid_claims + ibnr_carrier) / earned_premium
        mgu_ulr = (paid_claims + ibnr_mgu) / earned_premium
        if abs(ulr - mgu_ulr) > 0.10:
            warnings.append(f'WARNING: Carrier ULR {ulr:.2%} vs MGU ULR {mgu_ulr:.2%} — divergence exceeds 10%')

        commission_rate = get_commission_rate(ulr)
        gross_commission = earned_premium * commission_rate
        minimum_commission = earned_premium * MIN_COMMISSION_RATE

        carrier_splits = get_carrier_splits(conn, underwriting_year, as_of_date)
        if not carrier_splits:
            raise ValueError(f'No carrier splits for UY {underwriting_year}')

        floor_guard_applied = False
        carrier_allocations = []

        for carrier in carrier_splits:
            cid = carrier['carrier_id']
            pct = float(carrier['participation_pct'])
            carrier_gross = gross_commission * pct
            prior_paid = get_prior_commission_paid(conn, underwriting_year, cid)
            delta = carrier_gross - prior_paid

            carrier_min = minimum_commission * pct
            if prior_paid + delta < carrier_min:
                delta = carrier_min - prior_paid
                floor_guard_applied = True
                warnings.append(f'FLOOR GUARD applied for {cid} UY {underwriting_year}')

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
                    'commission_rate': commission_rate,
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
        )
    finally:
        conn.close()
