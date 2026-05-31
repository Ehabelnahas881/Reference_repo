# FMU Error Fix TODO (from approved plan)

## Steps:
- [x] Step 0: Analyzed files (FMU.py, test.py), created plan, got confirmation.
- [x] Step 1: Backup original FMU.py → FMU.py.backup
- [x] Step 2: Fix FMU.py (indentation, pandas .loc assignments, variable scoping, DB error handling, logic bugs, redundancies).
- [ ] Step 3: Update test.py with basic tests.
- [ ] Step 4: Test run: activate fmu_env & python FMU.py (verify no errors, DB inserts).
- [ ] Step 5: Run pytest test.py.
- [ ] Step 6: Update TODO.md as complete → attempt_completion.

**Status**: Plan approved. Next: backups & edits.
