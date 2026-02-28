#!/usr/bin/env python3
"""
BAA Commission Engine CLI

Commands:
    trueup    - Run a true-up calculation
    ledger    - Show commission ledger entries
    ibnr      - Show IBNR snapshots
    schemes   - Show profit commission schemes
"""
import argparse
import sys
import os
from dotenv import load_dotenv

# Add engine to path
sys.path.insert(0, '/app')

from engine.calculator import run_trueup
from engine.models import get_connection


def cmd_trueup(args):
    """Run a commission true-up."""
    result = run_trueup(
        args.uy,
        args.dev_age,
        args.as_of,
        write_to_db=not args.dry_run,
        allow_negative_commission=args.allow_negative
    )
    
    print(f"\n{'='*60}")
    print(f"  BAA TRUE-UP  //  UY {result.underwriting_year}  //  {result.development_month}mo  //  {result.as_of_date}")
    print(f"{'='*60}\n")
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


def cmd_ledger(args):
    """Show commission ledger entries."""
    load_dotenv('/app/.env')
    conn = get_connection()
    try:
        cur = conn.cursor()
        
        query = """
            SELECT underwriting_year, carrier_id, development_month, as_of_date,
                   earned_premium, paid_claims, ibnr_amount, ultimate_loss_ratio,
                   commission_rate, gross_commission, delta_payment, 
                   floor_guard_applied, calc_type, scheme_type_used,
                   ibnr_stale_days, ulr_divergence_flag
            FROM commission_ledger
        """
        params = []
        
        if args.uy:
            query += " WHERE underwriting_year = %s"
            params.append(args.uy)
        
        query += " ORDER BY id DESC"
        
        if args.limit:
            query += f" LIMIT {args.limit}"
        
        cur.execute(query, params)
        rows = cur.fetchall()
        
        if not rows:
            print("No ledger entries found.")
            return
        
        print(f"{'UY':>4} {'Carrier':<10} {'Dev':>4} {'AsOf':<12} {'Earned':>12} {'Claims':>12} {'ULR':>8} {'Rate':>6} {'Delta':>10}")
        print("-" * 100)
        for r in rows:
            print(f"{r[0]:>4} {r[1]:<10} {r[2]:>4} {str(r[3]):<12} {r[4]:>12,.2f} {r[5]:>12,.2f} {r[6]:>7.2%} {r[7]:>6.2%} {r[9]:>10,.2f}")
        
        print(f"\nTotal: {len(rows)} entries")
    finally:
        conn.close()


def cmd_ibnr(args):
    """Show IBNR snapshots."""
    load_dotenv('/app/.env')
    conn = get_connection()
    try:
        cur = conn.cursor()
        
        query = """
            SELECT underwriting_year, development_month, source, as_of_date, ibnr_amount
            FROM ibnr_snapshots
        """
        
        if args.uy:
            query += " WHERE underwriting_year = %s"
        
        query += " ORDER BY underwriting_year DESC, development_month DESC, source"
        
        cur.execute(query, args.uy if args.uy else None)
        rows = cur.fetchall()
        
        print(f"{'UY':>4} {'Dev':>4} {'Source':<20} {'AsOf':<12} {'IBNR Amount':>15}")
        print("-" * 60)
        for r in rows:
            print(f"{r[0]:>4} {r[1]:>4} {r[2]:<20} {str(r[3]):<12} {r[4]:>15,.2f}")
        
        print(f"\nTotal: {len(rows)} snapshots")
    finally:
        conn.close()


def cmd_schemes(args):
    """Show profit commission schemes."""
    load_dotenv('/app/.env')
    conn = get_connection()
    try:
        cur = conn.cursor()
        
        # Get scheme types - use column names
        cur.execute("SELECT scheme_id, scheme_type, parameters_json FROM profit_commission_schemes ORDER BY scheme_id")
        schemes = cur.fetchall()
        
        print("Profit Commission Schemes:")
        print(f"{'ID':>3} {'Scheme Type':<30} {'Parameters'}")
        print("-" * 80)
        for s in schemes:
            # Handle both tuple and dict formats
            if isinstance(s, dict):
                scheme_id = s['scheme_id']
                scheme_type = s['scheme_type']
                params = s['parameters_json']
            else:
                scheme_id, scheme_type, params = s
            print(f"{scheme_id:>3} {scheme_type:<30} {str(params)[:50]}")
        
        print("\nCarrier Schemes:")
        cur.execute("""
            SELECT underwriting_year, carrier_id, scheme_type, effective_from 
            FROM carrier_schemes 
            ORDER BY underwriting_year, carrier_id
        """)
        carrier_schemes = cur.fetchall()
        
        print(f"{'UY':>4} {'Carrier':<10} {'Scheme Type':<25} {'Effective From'}")
        print("-" * 55)
        for cs in carrier_schemes:
            if isinstance(cs, dict):
                print(f"{cs['underwriting_year']:>4} {cs['carrier_id']:<10} {cs['scheme_type']:<25} {cs['effective_from']}")
            else:
                print(f"{cs[0]:>4} {cs[1]:<10} {cs[2]:<25} {cs[3]}")
        
    finally:
        conn.close()


def main():
    parser = argparse.ArgumentParser(description='BAA Commission Engine CLI')
    subparsers = parser.add_subparsers(dest='command', help='Available commands')
    
    # trueup command
    trueup_parser = subparsers.add_parser('trueup', help='Run a commission true-up')
    trueup_parser.add_argument('--uy', type=int, required=True, help='Underwriting year')
    trueup_parser.add_argument('--dev-age', type=int, required=True, help='Development age in months')
    trueup_parser.add_argument('--as-of', type=str, required=True, help='As-of date (YYYY-MM-DD)')
    trueup_parser.add_argument('--dry-run', action='store_true', help='Do not write to database')
    trueup_parser.add_argument('--allow-negative', action='store_true', help='Allow negative commission deltas')
    
    # ledger command
    ledger_parser = subparsers.add_parser('ledger', help='Show commission ledger')
    ledger_parser.add_argument('--uy', type=int, help='Filter by underwriting year')
    ledger_parser.add_argument('--limit', type=int, default=20, help='Limit results')
    
    # ibnr command
    ibnr_parser = subparsers.add_parser('ibnr', help='Show IBNR snapshots')
    ibnr_parser.add_argument('--uy', type=int, help='Filter by underwriting year')
    
    # schemes command
    schemes_parser = subparsers.add_parser('schemes', help='Show profit commission schemes')
    
    args = parser.parse_args()
    
    if args.command == 'trueup':
        cmd_trueup(args)
    elif args.command == 'ledger':
        cmd_ledger(args)
    elif args.command == 'ibnr':
        cmd_ibnr(args)
    elif args.command == 'schemes':
        cmd_schemes(args)
    else:
        parser.print_help()


if __name__ == '__main__':
    main()
