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
