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

-- Core commission ledger with full audit trail
CREATE TABLE IF NOT EXISTS commission_ledger (
    id                       SERIAL PRIMARY KEY,
    underwriting_year        INTEGER NOT NULL REFERENCES uy_cohorts(underwriting_year),
    carrier_id               VARCHAR(50) NOT NULL,
    development_month        INTEGER NOT NULL,
    as_of_date               DATE NOT NULL,
    earned_premium           NUMERIC(15,2) NOT NULL,
    paid_claims              NUMERIC(15,2) NOT NULL,
    ibnr_amount             NUMERIC(15,2) NOT NULL,
    ultimate_loss_ratio     NUMERIC(8,6) NOT NULL,
    commission_rate          NUMERIC(5,4) NOT NULL,
    gross_commission         NUMERIC(15,2) NOT NULL,
    prior_paid_total        NUMERIC(15,2) NOT NULL DEFAULT 0,
    delta_payment           NUMERIC(15,2) NOT NULL,
    floor_guard_applied      BOOLEAN NOT NULL DEFAULT FALSE,
    calc_type                VARCHAR(30) NOT NULL
                            CHECK (calc_type IN ('provisional', 'true_up', 'final')),
    -- Audit metadata for vintage tracking
    carrier_split_effective_from DATE NOT NULL DEFAULT '2024-01-01',
    carrier_split_pct        NUMERIC(5,4) NOT NULL DEFAULT 0.5,
    -- Additional audit flags
    ibnr_stale_days         INTEGER NOT NULL DEFAULT 0,
    ulr_divergence_flag      BOOLEAN NOT NULL DEFAULT FALSE,
    scheme_type_used         VARCHAR(50),
    system_timestamp         TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ============================================================
-- Additional tables for multi-scheme support
-- ============================================================

-- Carriers table
CREATE TABLE IF NOT EXISTS carriers (
    id                  SERIAL PRIMARY KEY,
    carrier_id          VARCHAR(50) NOT NULL UNIQUE,
    carrier_name        VARCHAR(100) NOT NULL,
    system_timestamp    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Profit commission scheme definitions
CREATE TABLE IF NOT EXISTS profit_commission_schemes (
    scheme_id            SERIAL PRIMARY KEY,
    name                 VARCHAR(100) NOT NULL,
    scheme_type          VARCHAR(50) NOT NULL,
    params               JSONB DEFAULT '{}',
    system_timestamp    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Carrier-specific scheme assignments
CREATE TABLE IF NOT EXISTS carrier_schemes (
    id                       SERIAL PRIMARY KEY,
    underwriting_year        INTEGER NOT NULL REFERENCES uy_cohorts(underwriting_year),
    carrier_id               VARCHAR(50) NOT NULL,
    scheme_code              VARCHAR(50) NOT NULL,
    profit_commission_scheme_id INTEGER REFERENCES profit_commission_schemes(scheme_id),
    system_timestamp         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(underwriting_year, carrier_id, scheme_code)
);

-- BAA contract versions
CREATE TABLE IF NOT EXISTS baa_contract_versions (
    id                  SERIAL PRIMARY KEY,
    underwriting_year   INTEGER NOT NULL REFERENCES uy_cohorts(underwriting_year),
    version_number      INTEGER NOT NULL,
    effective_from      DATE NOT NULL,
    effective_to        DATE,
    description         TEXT,
    system_timestamp    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(underwriting_year, version_number)
);

-- LPT (Loss Portfolio Transfer) events
CREATE TABLE IF NOT EXISTS lpt_events (
    id                  SERIAL PRIMARY KEY,
    underwriting_year   INTEGER NOT NULL REFERENCES uy_cohorts(underwriting_year),
    carrier_id          VARCHAR(50) NOT NULL,
    event_date           DATE NOT NULL,
    freeze_commission   BOOLEAN NOT NULL DEFAULT TRUE,
    notes               TEXT,
    system_timestamp    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- FX rates for multi-currency support
CREATE TABLE IF NOT EXISTS fx_rates (
    id                  SERIAL PRIMARY KEY,
    currency            VARCHAR(3) NOT NULL,
    rate_date           DATE NOT NULL,
    rate_to_base        NUMERIC(12,6) NOT NULL,
    system_timestamp    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(currency, rate_date)
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_transactions_uy
    ON transactions(underwriting_year, txn_date);
CREATE INDEX IF NOT EXISTS idx_ibnr_uy_asof
    ON ibnr_snapshots(underwriting_year, as_of_date, source);
CREATE INDEX IF NOT EXISTS idx_carrier_splits_uy
    ON carrier_splits(underwriting_year, carrier_id);
CREATE INDEX IF NOT EXISTS idx_commission_ledger_uy_carrier
    ON commission_ledger(underwriting_year, carrier_id, development_month);
CREATE INDEX IF NOT EXISTS idx_lpt_events_uy
    ON lpt_events(underwriting_year, carrier_id);
CREATE INDEX IF NOT EXISTS idx_fx_rates_date
    ON fx_rates(currency, rate_date);
