"""
Seed data generator — creates 3 underwriting years of synthetic data.
Run from inside the container: python3 data/seed/generate_seed.py
"""
import os
import random
from datetime import date, timedelta
from dotenv import load_dotenv
import psycopg2

load_dotenv('/app/.env')
random.seed(42)

conn = psycopg2.connect(
    host='db',
    port=os.getenv('POSTGRES_PORT', 5432),
    dbname=os.getenv('POSTGRES_DB'),
    user=os.getenv('POSTGRES_USER'),
    password=os.getenv('POSTGRES_PASSWORD')
)
cur = conn.cursor()

# UY Cohorts
for uy, status in [(2022,'closed'),(2023,'run_off'),(2024,'open')]:
    cur.execute(
        "INSERT INTO uy_cohorts (underwriting_year,period_start,period_end,status) "
        "VALUES (%s,%s,%s,%s) ON CONFLICT DO NOTHING",
        (uy, f'{uy}-01-01', f'{uy}-12-31', status)
    )

# Carrier splits — CAR_B exits after 2023
splits = {
    2022: [('CAR_A','Atlas Specialty',0.6000),('CAR_B','Beacon Re',0.4000)],
    2023: [('CAR_A','Atlas Specialty',0.5000),('CAR_B','Beacon Re',0.3000),('CAR_C','Crown Markets',0.2000)],
    2024: [('CAR_A','Atlas Specialty',0.7000),('CAR_C','Crown Markets',0.3000)],
}
for uy, carriers in splits.items():
    for cid, cname, pct in carriers:
        cur.execute(
            "INSERT INTO carrier_splits (underwriting_year,carrier_id,carrier_name,participation_pct,effective_from) "
            "VALUES (%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING",
            (uy, cid, cname, pct, f'{uy}-01-01')
        )

# Carrier-specific scheme assignments
carrier_schemes = {
    2023: [
        ('CAR_A', 'sliding_scale', '{"min_commission_rate": 0.05}'),
        ('CAR_B', 'fixed_plus_variable', '{"fixed_rate": 0.10, "variable_rate": 0.05, "profit_threshold": 0.50}'),
        ('CAR_C', 'sliding_scale', '{"min_commission_rate": 0.05}'),
    ],
    2024: [
        ('CAR_A', 'fixed_plus_variable', '{"fixed_rate": 0.08, "variable_rate": 0.07, "profit_threshold": 0.45}'),
        ('CAR_C', 'fixed_plus_variable', '{"fixed_rate": 0.08, "variable_rate": 0.07, "profit_threshold": 0.45}'),
    ],
}
for uy, schemes in carrier_schemes.items():
    for cid, scheme_type, params in schemes:
        cur.execute(
            "INSERT INTO carrier_schemes (underwriting_year,carrier_id,effective_from,scheme_type,parameters_json) "
            "VALUES (%s,%s,%s,%s,%s)",
            (uy, cid, f'{uy}-01-01', scheme_type, params)
        )

# Policies and transactions
for uy in [2022, 2023, 2024]:
    for i in range(1, 11):
        ref = f'POL-{uy}-{i:03d}'
        eff = date(uy, random.randint(1,11), 1)
        exp = date(uy+1, eff.month, 1)
        premium = round(random.uniform(80_000, 600_000), 2)
        cur.execute(
            "INSERT INTO policies (policy_ref,underwriting_year,effective_date,expiry_date,gross_premium) "
            "VALUES (%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING",
            (ref, uy, eff, exp, premium)
        )
        cur.execute(
            "INSERT INTO transactions (policy_ref,underwriting_year,txn_type,txn_date,amount) "
            "VALUES (%s,%s,'premium',%s,%s)",
            (ref, uy, eff, premium)
        )
        if random.random() < 0.40:
            claim_amt = round(premium * random.uniform(0.2, 0.9), 2)
            claim_date = eff + timedelta(days=random.randint(90, 900))
            cur.execute(
                "INSERT INTO transactions (policy_ref,underwriting_year,txn_type,txn_date,amount) "
                "VALUES (%s,%s,'claim_paid',%s,%s)",
                (ref, uy, claim_date, claim_amt)
            )

# IBNR snapshots
for uy in [2022, 2023, 2024]:
    base = random.uniform(100_000, 500_000)
    for dev in [12, 24, 36, 48]:
        asof = date(uy + dev//12, 1, 1)
        decay = max(0.05, 1.0 - (dev/60))
        for source, mult in [('carrier_official', random.uniform(0.9,1.1)),
                              ('mgu_internal', random.uniform(0.8,1.2))]:
            cur.execute(
                "INSERT INTO ibnr_snapshots (underwriting_year,as_of_date,ibnr_amount,source,development_month) "
                "VALUES (%s,%s,%s,%s,%s)",
                (uy, asof, round(base*decay*mult, 2), source, dev)
            )

conn.commit()
conn.close()
print('Seed data loaded OK')
