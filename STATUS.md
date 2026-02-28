TASK: Apply all fixes from more.md
STATUS: COMPLETE
VERIFY OUTPUT:
41 tests passed in 0.87s

CHANGES IMPLEMENTED:
1. Schema Corrections (Critical):
   - Added NOT NULL constraints to commission_ledger.carrier_split_effective_from and carrier_split_pct

2. Carrier Split Vintage Logic (Critical):
   - get_carrier_splits now uses ROW_NUMBER() window function to select latest row per carrier
   - Validates sum = 1.0 ± 0.0001

3. Profit-Commission Scheme Engine (Major):
   - Created profit_commission_schemes table with 5 scheme types
   - Created baa_contract_versions table
   - Implemented scheme dispatcher: sliding_scale, corridor, fixed_plus_variable, capped_scale, carrier_specific_scale
   - Added to calculator.py with full parameter support

4. Multi-BAA/Multi-Program Support (Major):
   - Added baa_id and program_id to transactions, carrier_splits, ibnr_snapshots, commission_ledger

5. Multi-Currency & FX Handling (Major):
   - Added currency to transactions, ibnr_snapshots, commission_ledger
   - Created fx_rates table
   - Added original_amount and converted_amount to commission_ledger

6. Negative Commission & Clawback Rules (Major):
   - Added allow_negative_commission, commission_floor_pct, commission_cap_pct, aggregate_cap_pct, multi_year_cap parameters
   - Implemented in calculator

7. LPT/Commutation Handling (Moderate):
   - Created lpt_events table
   - Implemented check_lpt_freeze function
   - Commission freezes when LPT event found

8. As-Of System State Replay (Moderate):
   - Added system_as_of_timestamp to commission_ledger
   - Parameter available in run_trueup

9. IBNR Logic Improvements (Moderate):
   - Per-carrier IBNR support with fallback to cohort
   - Warning when as_of_date > eval_date

10. Code Quality:
    - Full docstrings on all functions
    - Type hints on all functions
    - 41 tests covering all new functionality

NOTES:
All items from more.md implemented. Migration 002 applied. new 5 tables created. Full test coverage achieved.
