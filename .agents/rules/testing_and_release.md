# Kyro Testing & Release Standards

Verification protocols required for every bug fix, feature addition, and code deployment.

---

## 1. Regression-First Rule
- For every bug fix, a dedicated regression test must be authored in `tests/` that:
  1. Reproduces and fails on the bug prior to the fix.
  2. Passes cleanly once the fix is applied.
- All tests must use mocks or local harnesses without opening external network connections or requiring real Discord/database credentials.

## 2. Import Smoke Test Integrity
- `tests/test_import_smoke.py` dynamically imports every module in `src/`.
- This test guarantees that no syntax errors, circular imports, missing third-party dependencies, or undefined variables (`NameError` / `UnboundLocalError`) exist in the codebase.
- This test MUST remain 100% green at all times.

## 3. Verify Gate Command Suite
Before concluding any task turn, execute the verify gate:
```powershell
$env:PATH = "$env:APPDATA\Python\Python313\Scripts;$env:PATH"
python -m compileall -q src tests
python -m ruff check src tests
python -m pyflakes src
python -m pytest -q
python -m bandit -r src -c pyproject.toml
```
Requirements for pass:
- 0 bytecode compilation errors.
- 0 Ruff `F821` (undefined name) errors and 0 lint failures on touched files.
- 100% pytest test suite passing.
- Bandit security scan passes with no high-severity vulnerabilities.

## 4. Git & Deployment Boundaries
- **NEVER** run `git push` or `git commit` autonomously.
- Keep all modifications staged or present in the active working tree.
- A commit or push is performed only when the user explicitly gives the command: `"push kar de"`.
