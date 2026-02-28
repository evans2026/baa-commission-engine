-- ============================================================
-- BAA Commission Engine — Schema Migration 003
-- Missing tables and commission_ledger extensions
-- Idempotent - safe to run multiple times
-- ============================================================

-- Create carriers table (if not exists)
CREATE TABLE IF NOT EXISTS carriers (
    id SERIAL PRIMARY KEY,
    carrier_id VARCHAR(50) NOT NULL UNIQUE,
    carrier_name VARCHAR(100) NOT NULL,
    system_timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Insert default carriers if not exists
INSERT INTO carriers (carrier_id, carrier_name) 
SELECT 'CAR_A', 'Atlas Specialty' WHERE NOT EXISTS (SELECT 1 FROM carriers WHERE carrier_id = 'CAR_A');
INSERT INTO carriers (carrier_id, carrier_name) 
SELECT 'CAR_B', 'Beacon Re' WHERE NOT EXISTS (SELECT 1 FROM carriers WHERE carrier_id = 'CAR_B');
INSERT INTO carriers (carrier_id, carrier_name) 
SELECT 'CAR_C', 'Crown Markets' WHERE NOT EXISTS (SELECT 1 FROM carriers WHERE carrier_id = 'CAR_C');

-- profit_commission_schemes table
CREATE TABLE IF NOT EXISTS profit_commission_schemes (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    scheme_type TEXT NOT NULL,
    params JSONB DEFAULT '{}',
    system_timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- carrier_schemes table
CREATE TABLE IF NOT EXISTS carrier_schemes (
    id SERIAL PRIMARY KEY,
    underwriting_year INTEGER NOT NULL REFERENCES uy_cohorts(underwriting_year),
    carrier_id VARCHAR(50) NOT NULL REFERENCES carriers(carrier_id),
    scheme_code TEXT NOT NULL,
    profit_commission_scheme_id INTEGER REFERENCES profit_commission_schemes(id),
    system_timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(underwriting_year, carrier_id, scheme_code)
);

-- baa_contract_versions table
CREATE TABLE IF NOT EXISTS baa_contract_versions (
    id SERIAL PRIMARY KEY,
    underwriting_year INTEGER NOT NULL REFERENCES uy_cohorts(underwriting_year),
    version_number INTEGER NOT NULL,
    effective_from DATE NOT NULL,
    effective_to DATE,
    description TEXT,
    system_timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(underwriting_year, version_number)
);

-- lpt_events table
CREATE TABLE IF NOT EXISTS lpt_events (
    id SERIAL PRIMARY KEY,
    underwriting_year INTEGER NOT NULL REFERENCES uy_cohorts(underwriting_year),
    carrier_id VARCHAR(50) NOT NULL REFERENCES carriers(carrier_id),
    event_date DATE NOT NULL,
    freeze_commission BOOLEAN NOT NULL DEFAULT TRUE,
    notes TEXT,
    system_timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Extend commission_ledger with required columns
ALTER TABLE commission_ledger 
ADD COLUMN IF NOT EXISTS carrier_split_effective_from DATE NOT NULL DEFAULT '2024-01-01',
ADD COLUMN IF NOT EXISTS carrier_split_pct NUMERIC(5,4) NOT NULL DEFAULT 0.5;

-- Create indexes
CREATE INDEX IF NOT EXISTS idx_carrier_schemes_uy ON carrier_schemes(underwriting_year);
CREATE INDEX IF NOT EXISTS idx_baa_contract_versions_uy ON baa_contract_versions(underwriting_year);
CREATE INDEX IF NOT EXISTS idx_lpt_events_uy ON lpt_events(underwriting_year, carrier_id);
