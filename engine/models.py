"""
Database connection and core query functions.
All queries use parameterised inputs.
Connects to Postgres at hostname 'db' (the Docker service name).
"""
import os
import psycopg2
import psycopg2.extras
from dotenv import load_dotenv

load_dotenv('/app/.env')

def get_connection():
    return psycopg2.connect(
        host='db',
        port=os.getenv('POSTGRES_PORT', 5432),
        dbname=os.getenv('POSTGRES_DB'),
        user=os.getenv('POSTGRES_USER'),
        password=os.getenv('POSTGRES_PASSWORD'),
        cursor_factory=psycopg2.extras.RealDictCursor
    )

def get_earned_premium(conn, underwriting_year):
    with conn.cursor() as cur:
        cur.execute("""
            SELECT COALESCE(SUM(amount), 0) as total
            FROM transactions
            WHERE underwriting_year = %s AND txn_type = 'premium'
        """, (underwriting_year,))
        return float(cur.fetchone()['total'])

def get_paid_claims(conn, underwriting_year, as_of_date):
    with conn.cursor() as cur:
        cur.execute("""
            SELECT COALESCE(SUM(amount), 0) as total
            FROM transactions
            WHERE underwriting_year = %s
              AND txn_type = 'claim_paid'
              AND txn_date <= %s
        """, (underwriting_year, as_of_date))
        return float(cur.fetchone()['total'])

def get_ibnr(conn, underwriting_year, development_month, source='carrier_official'):
    with conn.cursor() as cur:
        cur.execute("""
            SELECT ibnr_amount, as_of_date
            FROM ibnr_snapshots
            WHERE underwriting_year = %s
              AND development_month = %s
              AND source = %s
            ORDER BY system_timestamp DESC LIMIT 1
        """, (underwriting_year, development_month, source))
        row = cur.fetchone()
        if row is None:
            raise ValueError(f'No IBNR found for UY={underwriting_year} dev={development_month} source={source}')
        return dict(row)

def get_carrier_splits(conn, underwriting_year):
    with conn.cursor() as cur:
        cur.execute("""
            SELECT carrier_id, carrier_name, participation_pct
            FROM carrier_splits
            WHERE underwriting_year = %s
            ORDER BY participation_pct DESC
        """, (underwriting_year,))
        return [dict(r) for r in cur.fetchall()]

def get_prior_commission_paid(conn, underwriting_year, carrier_id):
    with conn.cursor() as cur:
        cur.execute("""
            SELECT COALESCE(SUM(delta_payment), 0) as total
            FROM commission_ledger
            WHERE underwriting_year = %s AND carrier_id = %s
        """, (underwriting_year, carrier_id))
        return float(cur.fetchone()['total'])

def write_commission_record(conn, record):
    with conn.cursor() as cur:
        cur.execute("""
            INSERT INTO commission_ledger (
                underwriting_year, carrier_id, development_month,
                as_of_date, earned_premium, paid_claims, ibnr_amount,
                ultimate_loss_ratio, commission_rate, gross_commission,
                prior_paid_total, delta_payment, floor_guard_applied, calc_type
            ) VALUES (
                %(underwriting_year)s, %(carrier_id)s, %(development_month)s,
                %(as_of_date)s, %(earned_premium)s, %(paid_claims)s, %(ibnr_amount)s,
                %(ultimate_loss_ratio)s, %(commission_rate)s, %(gross_commission)s,
                %(prior_paid_total)s, %(delta_payment)s, %(floor_guard_applied)s,
                %(calc_type)s
            )
        """, record)
    conn.commit()
