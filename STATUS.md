TASK: Apply AGENT_TASKS_PROFIT_COMMISSION.md requirements
STATUS: COMPLETE
VERIFY OUTPUT:
60 tests passed in 0.98s

CHANGES IMPLEMENTED:
1. Scheme Architecture (ProfitCommissionScheme base class):
   - Base class with abstract compute_commission method
   - SlidingScaleScheme, FixedPlusVariableScheme, CorridorProfitScheme, CappedScaleScheme
   - Factory function create_scheme() and registry

2. Fixed + Variable Scheme Implementation:
   - Fixed base commission + variable profit share
   - Profit threshold support
   - Variable cap support
   - Full test coverage

3. Per-Carrier Scheme Selection:
   - New carrier_schemes table
   - Each carrier can have different scheme in same UY
   - Data-driven scheme selection by effective_from

4. Domain Error Handling:
   - ProfitCommissionError base class
   - MissingSchemeError, InvalidSchemeParametersError, UnknownSchemeTypeError
   - CarrierSplitsError, NoEarnedPremiumError, NoIBNRSnapshotError
   - All error conditions tested

5. Test Suite (60 tests):
   - Scheme registry tests
   - Sliding scale scheme tests (boundary, floor guard)
   - Fixed+variable scheme tests (profit below/above threshold, cap)
   - Corridor scheme tests (inside/outside corridor)
   - Capped scale tests
   - Integration tests (mixed schemes per UY)
   - Error handling tests

6. Gitignore:
   - Added AGENT_TASKS_PROFIT_COMMISSION.md

NOTES:
All requirements from AGENT_TASKS_PROFIT_COMMISSION.md implemented.
- Modular, pluggable architecture with scheme subclasses
- Sliding scale and Fixed+Variable fully implemented and tested
- Scheme selection is data-driven and versioned
- All failure paths raise domain errors
- 60 deterministic tests covering all functionality
