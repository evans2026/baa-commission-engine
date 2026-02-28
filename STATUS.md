TASK: Apply Mandatory Fix Specification
STATUS: COMPLETE
VERIFY OUTPUT:
67 tests passed in 1.19s

COMPLETED ITEMS:

[✓] Migration 003 adding missing tables (carrier_schemes, baa_contract_versions, profit_commission_schemes, lpt_events, carriers)

[✓] Migration extending commission_ledger (carrier_split_effective_from, carrier_split_pct)

[✓] Fixed commission_rate behavior - now computes effective_rate = total_gross / earned_premium

[✓] Normalized carrier split errors to CarrierSplitsError

[✓] Completed ULR divergence test with deterministic scenario

[✓] Chose clawback model (Option B - no negative deltas) and implemented consistently

[✓] Carrier split failure tests (missing splits, invalid sum)

[✓] IBNR failure tests (missing carrier IBNR, missing MGU IBNR)

[✓] Multi-scheme integration tests (CAR_A sliding, CAR_B corridor, CAR_C fixed+var)

[✓] Audit reproducibility test (re-run produces zero delta)

[✓] Deterministic seed data (random.seed(42))

[✓] Scheme seed data added

[✓] Full type hints in calculator.py, schemes.py, models.py

[✓] Domain-specific error handling (CarrierSplitsError, NoIBNRSnapshotError, etc.)

[✓] README updated with scheme types, domain errors, clawback model, audit model

NOTES:
- commission_rate now correctly shows effective rate (21.34%) not ULR (14.68%)
- All 67 tests passing
- Pluggable scheme architecture working
