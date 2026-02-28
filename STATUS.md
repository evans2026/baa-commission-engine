TASK: Fix floor guard test isolation
STATUS: COMPLETE
VERIFY OUTPUT:
69 passed in 1.43s

NOTES:
- Fixed test_floor_guard_in_severe_loss to properly restore seed data after test
- Test now clears UY 2022 data, runs isolated test, then restores seed data
- All tests now pass regardless of execution order

NEXT TASK: None - work complete
