---
name: kyro-verify
description: Comprehensive verification workflow for Kyro Discord Bot. Use to run bytecode compilation, ruff lint checks, pytest test suites, and bandit security scans.
---

# Kyro Verification Skill

This skill documents how to execute, interpret, and resolve results from the Kyro Verification Gate.

## 1. Verify Gate Commands

Run the full verify gate in PowerShell:
```powershell
$env:PATH = "$env:APPDATA\Python\Python313\Scripts;$env:PATH"
python -m compileall -q src tests
python -m ruff check src tests
python -m pyflakes src
python -m pytest -q
python -m bandit -r src -c pyproject.toml
```

## 2. Common Failure Interpretations & Fixes

### A. Ruff `F821` (Undefined name)
- **Cause**: Variable or import used without being imported or defined in current scope (e.g. `Config`, `container`, `wavelink`).
- **Fix**: Check module imports at top of file or add proper typed initialization.

### B. Python `compileall` Syntax / Indentation Errors
- **Cause**: Stray indentation, unclosed brackets, or invalid syntax.
- **Fix**: Review git diff of touched lines and align indentation (4 spaces, no tabs).

### C. Bandit `B110` (`try ... except: pass`)
- **Cause**: Bare exception blocks swallowing errors silently.
- **Fix**: Replace with `logger.debug` for harmless expected conditions, `logger.warning(..., exc_info=True)` for failures, or narrow exceptions like `except (discord.NotFound, discord.Forbidden): pass # best-effort cleanup`.

### D. Pytest Failures
- **Import smoke failures**: Check `tests/test_import_smoke.py` output to identify the exact module that failed to import and the missing dependency or NameError.
- **Secret scanner failures**: Check `tests/test_secret_scanner.py` to identify unmasked tokens or hardcoded passwords.
