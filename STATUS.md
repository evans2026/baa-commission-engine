TASK: Comprehensive schema, logic, and test fixes
STATUS: COMPLETE
VERIFY OUTPUT:
71 passed in 1.51s

COMPLETED ITEMS:

[✓] Schema fixes:
  - carrier_schemes: updated to use scheme_type, parameters_json, effective_from
  - profit_commission_schemes: updated to use parameters_json
  - baa_contract_versions: added scheme_id column
  - lpt_events: fixed to use effective_date (removed event_date, baa_id, program_id)
  - commission_ledger: added all audit columns

[✓] Calculator logic fixes:
  - get_carrier_scheme: queries carrier_schemes with correct fields
  - check_lpt_freeze: uses correct lpt_events schema
  - write_commission_record: includes all audit fields

[✓] Test fixes:
  - TestLPTFreeze: removed invalid columns (baa_id, program_id)
  - ULR divergence tests: already had proper assertions
  - Added TestCarrierSchemeLookup tests for scheme lookup

[✓] Seed data:
  - Added carrier_schemes entries for UY 2023 and 2024

[✓] Schema file updated:
  - 001_schema.sql matches database schema

NEXT TASK: None - all fixes complete
