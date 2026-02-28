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

def get_earned_premium(conn, underwriting_year, as_of_date=None):
    with conn.cursor() as cur:
        date_filter = ""
        params = [underwriting_year]
        if as_of_date:
            date_filter = "AND txn_date <= %s"
            params.append(as_of_date)
        cur.execute(f"""
            SELECT COALESCE(SUM(
                CASE
                    WHEN txn_type = 'premium' THEN amount
                    WHEN txn_type = 'return_premium' THEN -amount
                    ELSE 0
                END
            ), 0) as total
            FROM transactions
            WHERE underwriting_year = %s AND txn_type IN ('premium', 'return_premium') {date_filter}
        """, params)
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

def get_ibnr(conn, underwriting_year, development_month, source='carrier_official', eval_date=None):
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

def get_carrier_splits(conn, underwriting_year, as_of_date=None):
    with conn.cursor() as cur:
        if as_of_date:
            cur.execute("""
                SELECT carrier_id, carrier_name, participation_pct, effective_from, system_timestamp
                FROM carrier_splits
                WHERE underwriting_year = %s AND effective_from <= %s
                ORDER BY effective_from DESC, system_timestamp DESC
            """, (underwriting_year, as_of_date))
        else:
            cur.execute("""
                SELECT carrier_id, carrier_name, participation_pct, effective_from, system_timestamp
                FROM carrier_splits
                WHERE underwriting_year = %s
                ORDER BY effective_from DESC, system_timestamp DESC
            """, (underwriting_year,))
        rows = cur.fetchall()
        if not rows:
            raise ValueError(f'No carrier splits found for UY={underwriting_year} as_of={as_of_date}')
        splits = [dict(r) for r in rows]
        total_pct = sum(float(s['participation_pct']) for s in splits)
        if abs(total_pct - 1.0) > 0.01:
            raise ValueError(f'Carrier splits for UY={underwriting_year} as_of={as_of_date} sum to {total_pct}, expected ~1.0')
        return splits

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
