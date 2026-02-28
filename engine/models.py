"""
Database connection and core query functions.
All queries use parameterised inputs.
Connects to Postgres at hostname 'db' (the Docker service name).
"""
import os
from datetime import date
from typing import Optional, List, Dict, Any
import psycopg2
import psycopg2.extras
from dotenv import load_dotenv

load_dotenv('/app/.env')


def get_connection():
    """Get a database connection with RealDictCursor."""
    return psycopg2.connect(
        host='db',
        port=os.getenv('POSTGRES_PORT', 5432),
        dbname=os.getenv('POSTGRES_DB'),
        user=os.getenv('POSTGRES_USER'),
        password=os.getenv('POSTGRES_PASSWORD'),
        cursor_factory=psycopg2.extras.RealDictCursor
    )


def get_earned_premium(conn, underwriting_year: int, as_of_date: Optional[str] = None) -> float:
    """
    Calculate net earned premium for a given underwriting year.
    
    Nets premium (positive) against return_premium (negative).
    Filters transactions by txn_date <= as_of_date if provided.
    
    Args:
        conn: Database connection
        underwriting_year: The underwriting year to calculate for
        as_of_date: Optional cutoff date for transactions (YYYY-MM-DD)
    
    Returns:
        Net earned premium (premium - return_premium)
    """
    with conn.cursor() as cur:
        if as_of_date:
            cur.execute("""
                SELECT COALESCE(SUM(
                    CASE
                        WHEN txn_type = 'premium' THEN amount
                        WHEN txn_type = 'return_premium' THEN -amount
                        ELSE 0
                    END
                ), 0) as total
                FROM transactions
                WHERE underwriting_year = %s 
                  AND txn_type IN ('premium', 'return_premium')
                  AND txn_date <= %s
            """, (underwriting_year, as_of_date))
        else:
            cur.execute("""
                SELECT COALESCE(SUM(
                    CASE
                        WHEN txn_type = 'premium' THEN amount
                        WHEN txn_type = 'return_premium' THEN -amount
                        ELSE 0
                    END
                ), 0) as total
                FROM transactions
                WHERE underwriting_year = %s 
                  AND txn_type IN ('premium', 'return_premium')
            """, (underwriting_year,))
        return float(cur.fetchone()['total'])


def get_paid_claims(conn, underwriting_year: int, as_of_date: str) -> float:
    """
    Get total paid claims for a given underwriting year as of a specific date.
    
    Args:
        conn: Database connection
        underwriting_year: The underwriting year
        as_of_date: Cutoff date for claims (YYYY-MM-DD)
    
    Returns:
        Total paid claims
    """
    with conn.cursor() as cur:
        cur.execute("""
            SELECT COALESCE(SUM(amount), 0) as total
            FROM transactions
            WHERE underwriting_year = %s
              AND txn_type = 'claim_paid'
              AND txn_date <= %s
        """, (underwriting_year, as_of_date))
        return float(cur.fetchone()['total'])


def get_ibnr(conn, underwriting_year: int, development_month: int, 
             source: str = 'carrier_official', 
             eval_date: Optional[str] = None) -> Dict[str, Any]:
    """
    Get IBNR snapshot for a given underwriting year and development month.
    
    Filters snapshots where as_of_date <= eval_date to ensure proper as-of semantics.
    Orders by as_of_date DESC, system_timestamp DESC to get the latest valid snapshot.
    
    Args:
        conn: Database connection
        underwriting_year: The underwriting year
        development_month: The development month (12, 24, 36, etc.)
        source: 'carrier_official' or 'mgu_internal'
        eval_date: Evaluation date to filter snapshots (YYYY-MM-DD)
    
    Returns:
        Dict with ibnr_amount, as_of_date, development_month
    
    Raises:
        ValueError: If no IBNR snapshot found
    """
    with conn.cursor() as cur:
        if eval_date:
            cur.execute("""
                SELECT ibnr_amount, as_of_date, development_month
                FROM ibnr_snapshots
                WHERE underwriting_year = %s
                  AND development_month = %s
                  AND source = %s
                  AND as_of_date <= %s
                ORDER BY as_of_date DESC, system_timestamp DESC LIMIT 1
            """, (underwriting_year, development_month, source, eval_date))
        else:
            cur.execute("""
                SELECT ibnr_amount, as_of_date, development_month
                FROM ibnr_snapshots
                WHERE underwriting_year = %s
                  AND development_month = %s
                  AND source = %s
                ORDER BY as_of_date DESC, system_timestamp DESC LIMIT 1
            """, (underwriting_year, development_month, source))
        row = cur.fetchone()
        if row is None:
            raise ValueError(f'No IBNR found for UY={underwriting_year} dev={development_month} source={source} eval_date={eval_date}')
        return dict(row)


def get_carrier_splits(conn, underwriting_year: int, 
                      as_of_date: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    Get carrier splits for a given underwriting year as of a specific date.
    
    Uses window functions to select the latest row per carrier where 
    effective_from <= as_of_date. Validates that participation percentages 
    sum to 1.0 ± 0.0001.
    
    Args:
        conn: Database connection
        underwriting_year: The underwriting year
        as_of_date: Date to filter splits (YYYY-MM-DD)
    
    Returns:
        List of carrier split dicts with all fields
    
    Raises:
        ValueError: If no splits found or percentages don't sum to 1.0
    """
    with conn.cursor() as cur:
        if as_of_date:
            cur.execute("""
                SELECT carrier_id, carrier_name, participation_pct, effective_from, system_timestamp
                FROM (
                    SELECT carrier_id, carrier_name, participation_pct, effective_from, system_timestamp,
                           ROW_NUMBER() OVER (PARTITION BY carrier_id ORDER BY effective_from DESC, system_timestamp DESC) as rn
                    FROM carrier_splits
                    WHERE underwriting_year = %s AND effective_from <= %s
                ) ranked
                WHERE rn = 1
                ORDER BY carrier_id
            """, (underwriting_year, as_of_date))
        else:
            cur.execute("""
                SELECT carrier_id, carrier_name, participation_pct, effective_from, system_timestamp
                FROM (
                    SELECT carrier_id, carrier_name, participation_pct, effective_from, system_timestamp,
                           ROW_NUMBER() OVER (PARTITION BY carrier_id ORDER BY effective_from DESC, system_timestamp DESC) as rn
                    FROM carrier_splits
                    WHERE underwriting_year = %s
                ) ranked
                WHERE rn = 1
                ORDER BY carrier_id
            """, (underwriting_year,))
        rows = cur.fetchall()
        if not rows:
            raise ValueError(f'No carrier splits found for UY={underwriting_year} as_of={as_of_date}')
        splits = [dict(r) for r in rows]
        total_pct = sum(float(s['participation_pct']) for s in splits)
        if abs(total_pct - 1.0) > 0.0001:
            raise ValueError(f'Carrier splits for UY={underwriting_year} as_of={as_of_date} sum to {total_pct}, expected 1.0')
        return splits


def get_prior_commission_paid(conn, underwriting_year: int, carrier_id: str) -> float:
    """
    Get total prior commission paid for a carrier in an underwriting year.
    
    Args:
        conn: Database connection
        underwriting_year: The underwriting year
        carrier_id: The carrier identifier
    
    Returns:
        Sum of delta_payment from commission_ledger
    """
    with conn.cursor() as cur:
        cur.execute("""
            SELECT COALESCE(SUM(delta_payment), 0) as total
            FROM commission_ledger
            WHERE underwriting_year = %s AND carrier_id = %s
        """, (underwriting_year, carrier_id))
        return float(cur.fetchone()['total'])


def write_commission_record(conn, record: Dict[str, Any]) -> None:
    """
    Write a commission calculation record to the ledger.
    
    Args:
        conn: Database connection
        record: Dict containing all commission fields including
                carrier_split_effective_from and carrier_split_pct
    """
    with conn.cursor() as cur:
        cur.execute("""
            INSERT INTO commission_ledger (
                underwriting_year, carrier_id, development_month,
                as_of_date, earned_premium, paid_claims, ibnr_amount,
                ultimate_loss_ratio, commission_rate, gross_commission,
                prior_paid_total, delta_payment, floor_guard_applied, calc_type,
                carrier_split_effective_from, carrier_split_pct
            ) VALUES (
                %(underwriting_year)s, %(carrier_id)s, %(development_month)s,
                %(as_of_date)s, %(earned_premium)s, %(paid_claims)s, %(ibnr_amount)s,
                %(ultimate_loss_ratio)s, %(commission_rate)s, %(gross_commission)s,
                %(prior_paid_total)s, %(delta_payment)s, %(floor_guard_applied)s,
                %(calc_type)s, %(carrier_split_effective_from)s, %(carrier_split_pct)s
            )
        """, record)
    conn.commit()
