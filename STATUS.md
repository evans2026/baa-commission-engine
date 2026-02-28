TASK: Apply fixes from fixes.md
STATUS: COMPLETE
VERIFY OUTPUT:
All 11 tests pass
- 7 sliding scale tests
- 4 calculation tests

FIXES APPLIED:
1. Carrier Split Vintage (Critical): get_carrier_splits now filters by effective_from <= as_of_date, validates sum to ~1.0
2. Return Premium (Major): get_earned_premium now includes return_premium as negative, filters by as_of_date
3. IBNR As-Of Semantics (Major): get_ibnr now filters by as_of_date <= eval_date, uses latest snapshot as-of eval_date
4. Carrier Split Vintage in Ledger (Major): Added carrier_split_effective_from and carrier_split_pct columns to commission_ledger
5. Development Month (Moderate): Uses development_month from IBNR snapshot instead of passed parameter
6. Added fixes.md to .gitignore

NOTES:
All fixes applied to engine/models.py and engine/calculator.py. Database schema updated with new columns. All tests pass.
