-- ============================================================
-- BAA Commission Engine — Schema Update v002
-- New tables for multi-scheme, multi-currency, and LPT support
-- ============================================================

-- Profit Commission Schemes
CREATE TABLE IF NOT EXISTS profit_commission_schemes (
    scheme_id            SERIAL PRIMARY KEY,
    scheme_type          VARCHAR(50) NOT NULL
                        CHECK (scheme_type IN (
                            'sliding_scale', 'corridor', 'fixed_plus_variable',
                            'capped_scale', 'carrier_specific_scale'
                        )),
    parameters_json     JSONB NOT NULL DEFAULT '{}',
    effective_from       DATE NOT NULL,
    effective_to         DATE,
    system_timestamp     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- BAA Contract Versions (links UY to scheme)
CREATE TABLE IF NOT EXISTS baa_contract_versions (
    id                  SERIAL PRIMARY KEY,
    baa_id              VARCHAR(50) NOT NULL,
    program_id          VARCHAR(50) NOT NULL,
    underwriting_year   INTEGER NOT NULL,
    scheme_id           INTEGER NOT NULL REFERENCES profit_commission_schemes(scheme_id),
    effective_from      DATE NOT NULL,
    system_timestamp    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(baa_id, program_id, underwriting_year, effective_from)
);

-- FX Rates for multi-currency support
CREATE TABLE IF NOT EXISTS fx_rates (
    id                  SERIAL PRIMARY KEY,
    currency            VARCHAR(3) NOT NULL,
    rate_date           DATE NOT NULL,
    rate_to_base        NUMERIC(12,6) NOT NULL,
    system_timestamp    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(currency, rate_date)
);

-- LPT (Loss Portfolio Transfer) Events
CREATE TABLE IF NOT EXISTS lpt_events (
    id                  SERIAL PRIMARY KEY,
    carrier_id          VARCHAR(50) NOT NULL,
    baa_id              VARCHAR(50) NOT NULL,
    program_id          VARCHAR(50) NOT NULL,
    underwriting_year   INTEGER NOT NULL,
    effective_date      DATE NOT NULL,
    freeze_commission   BOOLEAN NOT NULL DEFAULT TRUE,
    system_timestamp    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Add baa_id and program_id to transactions
ALTER TABLE transactions 
ADD COLUMN IF NOT EXISTS baa_id VARCHAR(50) DEFAULT 'DEFAULT_BAA',
ADD COLUMN IF NOT EXISTS program_id VARCHAR(50) DEFAULT 'DEFAULT_PROGRAM',
ADD COLUMN IF NOT EXISTS currency VARCHAR(3) DEFAULT 'USD';

-- Add baa_id and program_id to carrier_splits
ALTER TABLE carrier_splits 
ADD COLUMN IF NOT EXISTS baa_id VARCHAR(50) DEFAULT 'DEFAULT_BAA',
ADD COLUMN IF NOT EXISTS program_id VARCHAR(50) DEFAULT 'DEFAULT_PROGRAM';

-- Add baa_id and program_id to ibnr_snapshots
ALTER TABLE ibnr_snapshots 
ADD COLUMN IF NOT EXISTS baa_id VARCHAR(50) DEFAULT 'DEFAULT_BAA',
ADD COLUMN IF NOT EXISTS program_id VARCHAR(50) DEFAULT 'DEFAULT_PROGRAM',
ADD COLUMN IF NOT EXISTS currency VARCHAR(3) DEFAULT 'USD',
ADD COLUMN IF NOT EXISTS carrier_id VARCHAR(50);

-- Add baa_id, program_id, currency to commission_ledger
ALTER TABLE commission_ledger 
ADD COLUMN IF NOT EXISTS baa_id VARCHAR(50) DEFAULT 'DEFAULT_BAA',
ADD COLUMN IF NOT EXISTS program_id VARCHAR(50) DEFAULT 'DEFAULT_PROGRAM',
ADD COLUMN IF NOT EXISTS currency VARCHAR(3) DEFAULT 'USD',
ADD COLUMN IF NOT EXISTS original_amount NUMERIC(15,2),
ADD COLUMN IF NOT EXISTS converted_amount NUMERIC(15,2);

-- Add system_as_of_timestamp to commission_ledger for replay
ALTER TABLE commission_ledger 
ADD COLUMN IF NOT EXISTS system_as_of_timestamp TIMESTAMPTZ;

-- Create indexes
CREATE INDEX IF NOT EXISTS idx_schemes_type ON profit_commission_schemes(scheme_type, effective_from);
CREATE INDEX IF NOT EXISTS idx_contract_versions_uy ON baa_contract_versions(baa_id, program_id, underwriting_year);
CREATE INDEX IF NOT EXISTS idx_fx_rates_date ON fx_rates(currency, rate_date);
CREATE INDEX IF NOT EXISTS idx_lpt_events_uy ON lpt_events(carrier_id, baa_id, program_id, underwriting_year);
CREATE INDEX IF NOT EXISTS idx_transactions_baa_program_uy ON transactions(baa_id, program_id, underwriting_year, txn_date);
CREATE INDEX IF NOT EXISTS idx_ibnr_carrier ON ibnr_snapshots(carrier_id, underwriting_year, development_month);
