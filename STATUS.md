TASK: Upgrade to interview-ready PoC
STATUS: COMPLETE
VERIFY OUTPUT:
69 tests passed in 1.25s

COMPLETED ITEMS:

[✓] Schema-code alignment - all tables and columns present

[✓] Added audit metadata to commission_ledger (ibnr_stale_days, ulr_divergence_flag, scheme_type_used)

[✓] ULR divergence tests with proper assertions

[✓] Band-crossing regression test added

[✓] allow_negative_commission flag implemented (default: False - no negative deltas)

[✓] Four temporal axes documented in run_trueup docstring

[✓] CLI wrapper with commands:
    - trueup: Run commission true-up
    - ledger: Show ledger entries
    - ibnr: Show IBNR snapshots
    - schemes: Show profit commission schemes

NOTES:
- commission_rate now correctly shows effective rate
- CarrierSplitsError properly raised for split failures
- All 69 tests passing
- CLI fully functional
