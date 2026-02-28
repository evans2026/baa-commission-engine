# TASKS.md — BAA Commission Engine
## Execution Task List for opencode

> **You are already inside the baa_app container.**
> Working directory is `/app`. Postgres is at hostname `db`.
> Python and all packages are already installed.
> Tell opencode: *"Read AGENTS.md then complete Task [N]"*
> One task per session. Wait for STATUS.md before proceeding.

---

## PHASE 1 — Verify Environment
*Confirm everything inside the container is working correctly.*

---

### TASK 1 — Verify the environment

**What to do:**
Run these checks and print each result clearly labelled.

```bash
python3 --version
python3 -c "import psycopg2; import dotenv; import faker; import pandas; print('All packages OK')"
cat /app/.env
```

Then test the database connection:
```python
python3 -c "
import os
from dotenv import load_dotenv
import psycopg2
load_dotenv('/app/.env')
conn = psycopg2.connect(
    host='db',
    port=os.getenv('POSTGRES_PORT', 5432),
    dbname=os.getenv('POSTGRES_DB'),
    user=os.getenv('POSTGRES_USER'),
    password=os.getenv('POSTGRES_PASSWORD')
)
print('Database connection: OK')
conn.close()
"
```

**Do not install or change anything in this task.**

**VERIFY:**
```bash
echo "Task 1 complete"
```

**STOP after this task.**

---

## PHASE 2 — Database Schema
*Goal: All six core tables created with correct structure.*

---

### TASK 2 — Write and apply the core schema

**What to do:**
Create `/app/db/migrations/001_schema.sql` with this content:

```sql
-- ============================================================
-- BAA Commission Engine — Core Schema
-- Version: 001
-- All tables are append-only by design.
-- Records are never updated or deleted — only inserted.
-- Four temporal dimensions on every transactional table:
--   txn_date         : when the underlying event occurred
--   underwriting_year: UY cohort lock (year policy was bound)
--   as_of_date       : actuarial snapshot date (for IBNR rows)
--   system_timestamp : when this row was written to the DB
-- ============================================================

CREATE TABLE IF NOT EXISTS uy_cohorts (
    id                  SERIAL PRIMARY KEY,
    underwriting_year   INTEGER NOT NULL UNIQUE,
    period_start        DATE NOT NULL,
    period_end          DATE NOT NULL,
    status              VARCHAR(20) NOT NULL DEFAULT 'open'
                            CHECK (status IN ('open', 'run_off', 'closed')),
    system_timestamp    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS policies (
    id                  SERIAL PRIMARY KEY,
    policy_ref          VARCHAR(50) NOT NULL UNIQUE,
    underwriting_year   INTEGER NOT NULL REFERENCES uy_cohorts(underwriting_year),
    effective_date      DATE NOT NULL,
    expiry_date         DATE NOT NULL,
    gross_premium       NUMERIC(15,2) NOT NULL,
    system_timestamp    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS transactions (
    id                  SERIAL PRIMARY KEY,
    policy_ref          VARCHAR(50) NOT NULL REFERENCES policies(policy_ref),
    underwriting_year   INTEGER NOT NULL REFERENCES uy_cohorts(underwriting_year),
    txn_type            VARCHAR(30) NOT NULL
                            CHECK (txn_type IN (
                                'premium', 'return_premium',
                                'claim_paid', 'claim_reserve_movement'
                            )),
    txn_date            DATE NOT NULL,
    amount              NUMERIC(15,2) NOT NULL,
    system_timestamp    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS ibnr_snapshots (
    id                  SERIAL PRIMARY KEY,
    underwriting_year   INTEGER NOT NULL REFERENCES uy_cohorts(underwriting_year),
    as_of_date          DATE NOT NULL,
    ibnr_amount         NUMERIC(15,2) NOT NULL,
    source              VARCHAR(20) NOT NULL
                            CHECK (source IN ('carrier_official', 'mgu_internal')),
    development_month   INTEGER NOT NULL,
    system_timestamp    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS carrier_splits (
    id                  SERIAL PRIMARY KEY,
    underwriting_year   INTEGER NOT NULL REFERENCES uy_cohorts(underwriting_year),
    carrier_id          VARCHAR(50) NOT NULL,
    carrier_name        VARCHAR(100) NOT NULL,
    participation_pct   NUMERIC(5,4) NOT NULL
                            CHECK (participation_pct > 0 AND participation_pct <= 1),
    effective_from      DATE NOT NULL,
    system_timestamp    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS commission_ledger (
    id                  SERIAL PRIMARY KEY,
    underwriting_year   INTEGER NOT NULL REFERENCES uy_cohorts(underwriting_year),
    carrier_id          VARCHAR(50) NOT NULL,
    development_month   INTEGER NOT NULL,
    as_of_date          DATE NOT NULL,
    earned_premium      NUMERIC(15,2) NOT NULL,
    paid_claims         NUMERIC(15,2) NOT NULL,
    ibnr_amount         NUMERIC(15,2) NOT NULL,
    ultimate_loss_ratio NUMERIC(8,6) NOT NULL,
    commission_rate     NUMERIC(5,4) NOT NULL,
    gross_commission    NUMERIC(15,2) NOT NULL,
    prior_paid_total    NUMERIC(15,2) NOT NULL DEFAULT 0,
    delta_payment       NUMERIC(15,2) NOT NULL,
    floor_guard_applied BOOLEAN NOT NULL DEFAULT FALSE,
    calc_type           VARCHAR(30) NOT NULL
                            CHECK (calc_type IN ('provisional', 'true_up', 'final')),
    system_timestamp    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_transactions_uy
    ON transactions(underwriting_year, txn_date);
CREATE INDEX IF NOT EXISTS idx_ibnr_uy_asof
    ON ibnr_snapshots(underwriting_year, as_of_date, source);
CREATE INDEX IF NOT EXISTS idx_carrier_splits_uy
    ON carrier_splits(underwriting_year, carrier_id);
CREATE INDEX IF NOT EXISTS idx_commission_ledger_uy_carrier
    ON commission_ledger(underwriting_year, carrier_id, development_month);
```

Apply it:
```bash
python3 -c "
import os
from dotenv import load_dotenv
import psycopg2
load_dotenv('/app/.env')
conn = psycopg2.connect(
    host='db', port=os.getenv('POSTGRES_PORT', 5432),
    dbname=os.getenv('POSTGRES_DB'), user=os.getenv('POSTGRES_USER'),
    password=os.getenv('POSTGRES_PASSWORD')
)
with open('/app/db/migrations/001_schema.sql') as f:
    conn.cursor().execute(f.read())
conn.commit()
conn.close()
print('Schema applied OK')
"
```

**VERIFY:**
```python
python3 -c "
import os
from dotenv import load_dotenv
import psycopg2
load_dotenv('/app/.env')
conn = psycopg2.connect(
    host='db', port=os.getenv('POSTGRES_PORT', 5432),
    dbname=os.getenv('POSTGRES_DB'), user=os.getenv('POSTGRES_USER'),
    password=os.getenv('POSTGRES_PASSWORD')
)
cur = conn.cursor()
cur.execute(\"SELECT COUNT(*) FROM information_schema.tables WHERE table_schema='public'\")
count = cur.fetchone()[0]
print(f'Tables in database: {count}')
conn.close()
"
```

Expected: `Tables in database: 6`

**STOP after this task.**

---

### TASK 3 — Generate and load seed data

**What to do:**
Create `/app/data/seed/generate_seed.py`:

```python
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
```

Run it:
```bash
python3 /app/data/seed/generate_seed.py
```

**VERIFY:**
```python
python3 -c "
import os
from dotenv import load_dotenv
import psycopg2
load_dotenv('/app/.env')
conn = psycopg2.connect(host='db', port=os.getenv('POSTGRES_PORT',5432),
    dbname=os.getenv('POSTGRES_DB'), user=os.getenv('POSTGRES_USER'),
    password=os.getenv('POSTGRES_PASSWORD'))
cur = conn.cursor()
for tbl in ['policies','transactions','ibnr_snapshots','carrier_splits']:
    cur.execute(f'SELECT COUNT(*) FROM {tbl}')
    print(f'{tbl}: {cur.fetchone()[0]}')
conn.close()
"
```

Expected: policies=30, transactions≥30, ibnr_snapshots=24, carrier_splits=7

**STOP after this task.**

---

## PHASE 3 — Calculation Engine
*Goal: A runnable Python module producing correct true-up output.*

---

### TASK 4 — Write the database connection module

**What to do:**
Create `/app/engine/models.py`:

```python
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
```

**VERIFY:**
```python
python3 -c "
from engine.models import get_connection, get_earned_premium
conn = get_connection()
ep = get_earned_premium(conn, 2023)
print(f'UY 2023 earned premium: {ep:,.2f}')
conn.close()
print('models.py OK')
"
```

Expected: a non-zero number and `models.py OK`

**STOP after this task.**

---

### TASK 5 — Write the calculation engine

**What to do:**
Create `/app/engine/calculator.py`:

```python
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
        earned_premium = get_earned_premium(conn, underwriting_year)
        if earned_premium == 0:
            raise ValueError(f'No earned premium for UY {underwriting_year}')

        paid_claims = get_paid_claims(conn, underwriting_year, as_of_date)
        carrier_snap = get_ibnr(conn, underwriting_year, development_month, 'carrier_official')
        mgu_snap = get_ibnr(conn, underwriting_year, development_month, 'mgu_internal')
        ibnr_carrier = float(carrier_snap['ibnr_amount'])
        ibnr_mgu = float(mgu_snap['ibnr_amount'])

        # Staleness check
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

        carrier_splits = get_carrier_splits(conn, underwriting_year)
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
                    'development_month': development_month,
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
                })

        return TrueUpResult(
            underwriting_year=underwriting_year,
            development_month=development_month,
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
```

**VERIFY:**
```python
python3 -c "
from engine.calculator import run_trueup, get_commission_rate
assert get_commission_rate(0.40) == 0.27
assert get_commission_rate(0.60) == 0.18
assert get_commission_rate(0.95) == 0.00
print('Sliding scale: OK')
result = run_trueup(2023, 24, '2025-01-01', write_to_db=False)
print(f'UY 2023 @ 24mo:')
print(f'  Earned Premium:  {result.earned_premium:>12,.2f}')
print(f'  ULR:             {result.ultimate_loss_ratio:>12.2%}')
print(f'  Commission Rate: {result.commission_rate:>12.2%}')
print(f'  Gross Comm:      {result.gross_commission:>12,.2f}')
print(f'  Carriers:        {len(result.carrier_allocations)}')
for w in result.warnings: print(f'  [WARN] {w}')
print('calculator.py OK')
"
```

Expected: assertions pass, numbers printed, `calculator.py OK`

**STOP after this task.**

---

### TASK 6 — Write the run script

**What to do:**
Create `/app/scripts/run_trueup.py`:

```python
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
```

**VERIFY:**
```bash
python3 /app/scripts/run_trueup.py --uy 2023 --dev-age 24 --as-of 2025-01-01 --dry-run
```

Expected: formatted report with premium, ULR, commission rate, carrier table.

**STOP after this task.**

---

## PHASE 4 — Tests & Git

---

### TASK 7 — Write and run the test suite

**What to do:**
Create `/app/tests/conftest.py`:
```python
from dotenv import load_dotenv
load_dotenv('/app/.env')
```

Create `/app/tests/test_calculator.py`:
```python
import pytest
from engine.calculator import get_commission_rate, MIN_COMMISSION_RATE, SLIDING_SCALE

class TestSlidingScale:
    def test_lowest_band(self):
        assert get_commission_rate(0.30) == 0.27
    def test_second_band(self):
        assert get_commission_rate(0.50) == 0.23
    def test_third_band(self):
        assert get_commission_rate(0.60) == 0.18
    def test_fourth_band(self):
        assert get_commission_rate(0.70) == 0.10
    def test_zero_commission(self):
        assert get_commission_rate(0.80) == 0.00
    def test_loss_scenario(self):
        assert get_commission_rate(1.20) == 0.00
    def test_zero_loss_ratio(self):
        assert get_commission_rate(0.00) == 0.27

class TestTrueUpNoDb:
    def test_basic_calculation_runs(self):
        from engine.calculator import run_trueup
        result = run_trueup(2023, 24, '2025-01-01', write_to_db=False)
        assert result.earned_premium > 0
        assert result.ultimate_loss_ratio >= 0
        assert 0.0 <= result.commission_rate <= 0.27

    def test_carrier_allocations_sum_to_gross(self):
        from engine.calculator import run_trueup
        result = run_trueup(2023, 24, '2025-01-01', write_to_db=False)
        total = sum(a['carrier_gross_commission'] for a in result.carrier_allocations)
        assert abs(total - result.gross_commission) < 0.01

    def test_ulr_formula_correct(self):
        from engine.calculator import run_trueup
        result = run_trueup(2023, 24, '2025-01-01', write_to_db=False)
        expected = (result.paid_claims + result.ibnr_carrier) / result.earned_premium
        assert abs(result.ultimate_loss_ratio - expected) < 0.000001

    def test_all_three_underwriting_years(self):
        from engine.calculator import run_trueup
        for uy in [2022, 2023, 2024]:
            result = run_trueup(uy, 12, f'{uy+1}-01-01', write_to_db=False)
            assert result.earned_premium > 0
```

Run the tests:
```bash
cd /app && python3 -m pytest tests/ -v
```

**VERIFY:**
```bash
python3 -m pytest tests/ -v --tb=short 2>&1 | tail -20
```

Expected: all tests pass, no failures.

**STOP after this task.**

---

### TASK 8 — Initialise Git

**What to do:**
```bash
cd /app
git init
git config user.email "sahinovicevan@gmail.com"
git config user.name "BAA Engine"
```

Verify `.env` is not staged before committing:
```bash
git status | grep ".env"
```

If `.env` appears — stop. Fix `.gitignore` first. Do not commit.

If `.env` does not appear:
```bash
git add .
git commit -m "feat: BAA commission engine — initial working PoC

- PostgreSQL schema: 6 append-only tables, 4 temporal dimensions
- Sliding scale commission with band-crossing and floor guard logic
- Carrier split persistence through syndicate exits
- IBNR-aware true-up loop with stale data detection
- Dual-track actuarial projection (carrier vs MGU)
- Seed data: UY 2022/2023/2024 with synthetic policies and claims
- pytest suite: sliding scale, ULR formula, carrier allocation"
```

**VERIFY:**
```bash
git log --oneline | head -3
git status
```

Expected: one clean commit, working tree clean.

**STOP after this task.**
Project is portfolio-ready. Push to GitHub and add the URL to your CV.

---

## COMPLETION CHECKLIST

- [ ] Task 1: Environment verified — Python, packages, DB connection all OK
- [ ] Task 2: Schema applied — 6 tables in database
- [ ] Task 3: Seed data loaded — 30 policies, 24 IBNR snapshots
- [ ] Task 4: models.py working — DB queries return real data
- [ ] Task 5: calculator.py working — sliding scale and ULR correct
- [ ] Task 6: run script working — formatted report prints cleanly
- [ ] Task 7: All tests pass
- [ ] Task 8: Clean git commit, .env never committed

