TASK: Apply fixes from fixes.md (Updated)
STATUS: COMPLETE
VERIFY OUTPUT:
30 tests passed in 0.69s

FIXES APPLIED:
1. Carrier Split Vintage (Critical): 
   - get_carrier_splits filters by effective_from <= as_of_date
   - Validates participation_pct sums to 1.0 ± 0.0001
   - Returns effective_from field

2. Return Premium Fix (Major):
   - get_earned_premium nets premium (+) against return_premium (-)
   - Filters transactions by txn_date <= as_of_date

3. IBNR As-Of Logic (Major):
   - get_ibnr filters by as_of_date <= eval_date
   - Returns development_month from snapshot
   - Stale warning when IBNR > 90 days old

4. Ledger Enhancements:
   - Added carrier_split_effective_from and carrier_split_pct columns
   - Populated in run_trueup

5. Development Month Consistency:
   - Uses development_month from IBNR snapshot

6. As-Of Filtering:
   - get_paid_claims filters by txn_date <= as_of_date
   - get_earned_premium filters by txn_date <= as_of_date

7. Test Suite Updates:
   - Added 19 new tests covering all functionality
   - Carrier split vintage tests
   - Return premium tests
   - IBNR as-of tests
   - Floor guard tests
   - ULR divergence tests
   - Ledger write tests

8. Code Quality:
   - Added docstrings to all functions
   - Added type hints to all functions
   - No dead code

NOTES:
All fixes from fixes.md applied. Full test coverage achieved (30 tests).
