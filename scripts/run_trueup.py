"""
Run a true-up and print a formatted report.
Usage: python3 scripts/run_trueup.py --uy 2023 --dev-age 36 --as-of 2026-01-01
Add --dry-run to skip writing to the database.
"""
import argparse
from engine.calculator import run_trueup

parser = argparse.ArgumentParser()
parser.add_argument('--uy', type=int, required=True)
parser.add_argument('--dev-age', type=int, required=True)
parser.add_argument('--as-of', type=str, required=True)
parser.add_argument('--dry-run', action='store_true')
args = parser.parse_args()

print(f"\n{'='*60}")
print(f"  BAA TRUE-UP  //  UY {args.uy}  //  {args.dev_age}mo  //  {args.as_of}")
print(f"{'='*60}\n")

result = run_trueup(args.uy, args.dev_age, args.as_of, write_to_db=not args.dry_run)

print(f"  Earned Premium:      {result.earned_premium:>14,.2f}")
print(f"  Paid Claims:         {result.paid_claims:>14,.2f}")
print(f"  IBNR (carrier):      {result.ibnr_carrier:>14,.2f}")
print(f"  IBNR (MGU):          {result.ibnr_mgu:>14,.2f}")
print(f"  Ultimate Loss Ratio: {result.ultimate_loss_ratio:>14.2%}")
print(f"  Commission Rate:     {result.commission_rate:>14.2%}")
print(f"  Gross Commission:    {result.gross_commission:>14,.2f}")
print(f"\n  {'Carrier':<20} {'Share':>6} {'Gross':>12} {'Prior Paid':>12} {'Delta':>12}")
print(f"  {'-'*64}")
for a in result.carrier_allocations:
    print(f"  {a['carrier_id']:<20} {a['participation_pct']:>6.1%} "
          f"{a['carrier_gross_commission']:>12,.2f} "
          f"{a['prior_paid']:>12,.2f} "
          f"{a['delta_payment']:>12,.2f}")
if result.warnings:
    print(f"\n  WARNINGS")
    for w in result.warnings:
        print(f"  ⚠  {w}")
status = 'DRY RUN — no DB write' if args.dry_run else 'Written to commission_ledger'
print(f"\n  {status}")
print(f"{'='*60}\n")
