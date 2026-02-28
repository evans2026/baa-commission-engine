# BAA Long-Tail Commission Engine
### Proof of Concept — Specialty Insurance / MGU Finance Operations

---

## What This Is

A working proof-of-concept that solves one of the most technically complex
problems in specialty insurance back-office operations: calculating profit
commission under a Binding Authority Agreement (BAA) across a multi-year
claims run-off period.

Built in Python and PostgreSQL, containerised with Docker, from scratch —
to demonstrate that the problem is fully understood and fully solvable.

---

## The Problem

When a Managing General Underwriter (MGU) binds a policy under a BAA with
a carrier, a profit commission is owed if the book of business performs well.
Simple enough on paper. In practice it is anything but.

A policy bound in 2023 might not generate its final claim until 2029. The
commission cannot be calculated once and forgotten — it must be recalculated
at every development age (12, 24, 36, 48, 60+ months) as real claims emerge
and actuarial reserves are updated. Each recalculation must be net-settled
against every prior payment to produce a single defensible cash movement —
per carrier, per underwriting year — with a complete audit trail.

The specific failure modes this solves:

**Cohort contamination** — a claim paid today belongs to the underwriting
year the policy was bound, not the calendar year the payment happened. Every
transaction is locked to its originating underwriting year at the point of
ingestion and can never cross-contaminate another cohort.

**Sliding scale band-crossing** — the commission rate itself changes as the
loss ratio moves through contractual bands. If a new development period causes
the loss ratio to cross a band boundary, the entire prior commission history
for that cohort must be retroactively recalculated, not just the incremental
period. Most systems get this wrong.

**Carrier split persistence** — each BAA involves multiple carriers at fixed
co-insurance percentages. When a carrier exits the syndicate, they remain
responsible for their share of all prior underwriting year true-ups. The
system stores historical split data permanently and always queries the correct
vintage for any given calculation.

**IBNR staleness** — Incurred But Not Reported reserves are produced by
carrier actuaries on their own schedule. The system detects when IBNR data is
stale relative to the evaluation date and flags the divergence between the
carrier's official reserves and the MGU's internal projection.

**Clawback floor guard** — when losses develop badly, carriers can reclaim
overpaid commission. The system enforces the contractual minimum commission
floor, ensuring no clawback can reduce the MGU's total received commission
below the guaranteed minimum.

**Audit reproducibility** — every calculation is stored with four temporal
dimensions (transaction date, underwriting year, actuarial as-of date, system
write timestamp). Any historical calculation can be reproduced identically on
any future date.

---

## Architecture

```
baa-commission-engine/
├── db/
│   └── migrations/
│       └── 001_schema.sql      # Six append-only PostgreSQL tables
├── engine/
│   ├── models.py               # Database connection and parameterised queries
│   └── calculator.py           # Core true-up calculation engine
├── data/
│   └── seed/
│       └── generate_seed.py    # Synthetic data: 3 UYs, policies, claims, IBNR
├── scripts/
│   └── run_trueup.py           # CLI runner — produces formatted true-up report
├── tests/
│   └── test_calculator.py      # pytest suite covering all edge cases
├── Dockerfile                  # Python 3.12 app container
└── docker-compose.yml          # PostgreSQL 16 + app, user-mapped volumes
```

### The Six Core Tables

| Table | Purpose |
|---|---|
| `uy_cohorts` | One row per underwriting year — the cohort anchor |
| `policies` | Every policy, locked to its underwriting year at insert |
| `transactions` | All premium and claim movements, append-only |
| `ibnr_snapshots` | Actuarial IBNR estimates at each evaluation date |
| `carrier_splits` | Historical syndicate participation — never deleted |
| `commission_ledger` | Every calculation and payment — immutable audit trail |

### The Four Temporal Dimensions

Every transactional row carries four date fields. Conflating any two of them
is where long-tail commission systems break and produce unreproducible results.

| Field | What It Represents |
|---|---|
| `txn_date` | When the underlying event occurred |
| `underwriting_year` | The UY cohort lock — permanent, set at policy bind |
| `as_of_date` | The actuarial snapshot date the IBNR was produced for |
| `system_timestamp` | When this row was written to the database |

---

## Running It

### Prerequisites
- Docker and Docker Compose installed
- That's it

### Start the containers
```bash
git clone https://github.com/evans2026/baa-commission-engine.git
cd baa-commission-engine
cp .env.example .env
docker compose up -d --build
```

### Get a shell in the app container
```bash
docker exec -it baa_app bash
```

### Apply the schema and load seed data
```bash
python3 data/seed/generate_seed.py
```

### Run a true-up calculation
```bash
python3 scripts/run_trueup.py --uy 2023 --dev-age 24 --as-of 2025-01-01 --dry-run
```

Example output:
```
============================================================
  BAA TRUE-UP  //  UY 2023  //  24mo  //  2025-01-01
============================================================

  Earned Premium:           2,847,320.00
  Paid Claims:                412,180.00
  IBNR (carrier):             318,500.00
  IBNR (MGU):                 290,200.00
  Ultimate Loss Ratio:             25.72%
  Commission Rate:                 27.00%
  Gross Commission:            768,776.40

  Carrier              Share        Gross   Prior Paid        Delta
  ----------------------------------------------------------------
  CAR_A                 50.0%   384,388.20         0.00   384,388.20
  CAR_B                 30.0%   230,632.92         0.00   230,632.92
  CAR_C                 20.0%   153,755.28         0.00   153,755.28

  DRY RUN — no DB write
============================================================
```

### Run the test suite
```bash
python3 -m pytest tests/ -v
```

---

## The Sliding Scale

Commission rate is determined by which loss ratio band the calculation falls in.
If development causes the loss ratio to cross a band boundary, the full commission
history for that underwriting year cohort is retroactively recalculated.

| Loss Ratio | Commission Rate |
|---|---|
| < 45% | 27% |
| 45% – 55% | 23% |
| 55% – 65% | 18% |
| 65% – 75% | 10% |
| > 75% | 0% |
| Contractual floor | 5% minimum |

---

## Why This Exists

I worked in MGU operations in specialty insurance. The commission calculation
problem described here is real, is widespread, and is routinely handled with
spreadsheets and manual reconciliation that break down over multi-year run-off
periods — especially when carrier syndicates change, IBNR assumptions shift,
or loss ratios cross band boundaries mid-development.

This project demonstrates that the problem has a clean, auditable, fully
automated solution — and that I can build it.

---

## Tech Stack

| Component | Technology |
|---|---|
| Database | PostgreSQL 16 |
| Language | Python 3.12 |
| Containers | Docker + Docker Compose |
| Testing | pytest |
| Data generation | Faker + custom seed scripts |

100% free and open source.

---

## Supported Scheme Types

The engine supports multiple profit commission scheme types via a pluggable architecture:

### 1. Sliding Scale
Traditional tiered commission based on loss ratio bands.

### 2. Fixed + Variable
Base commission plus profit share above a threshold.

### 3. Corridor
Commission rate changes inside/outside a loss ratio corridor.

### 4. Capped Scale
Sliding scale with maximum commission cap.

---

## Domain Errors

All errors are domain-specific for precise error handling:

- `ProfitCommissionError` - Base exception
- `CarrierSplitsError` - Missing or invalid carrier splits
- `NoIBNRSnapshotError` - Missing IBNR data
- `NoEarnedPremiumError` - No earned premium available
- `UnknownSchemeTypeError` - Unrecognized scheme type

---

## Clawback Model

**Option B (No Negative Deltas)** is implemented:
- Negative commission deltas are not permitted
- Delta is clamped to max(delta, 0) before floor guard
- Floor guard guarantees minimum commission (5% of earned premium)

---

## Audit Model

- **As-of semantics**: All calculations filter data by as_of_date
- **System timestamp**: All records include system_timestamp for audit
- **Vintage selection**: Carrier splits use effective_from to select correct historical split
- **Reproducibility**: Re-running same true-up with same inputs produces zero delta
