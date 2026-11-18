# Kyro Engineering Rules & Code Quality Standards

These rules are non-negotiable standards for all modifications to the Kyro codebase.

---

## 1. Zero Bloat & Laser Focus
- Implement **only** what was explicitly requested by the user.
- Do not create speculative helper methods, dummy commands, unused imports, or unused abstraction layers.
- Apply the **smallest correct diff** fixed at the root cause.
- Before modifying a shared function or model, grep and verify all call sites across the codebase.

## 2. No Local Bot Runs
- **NEVER execute `python main.py`** or any script that attempts to log in to Discord gateway with production credentials.
- The bot is hosted live on a remote production server. Running locally causes immediate gateway session collision, socket termination, and user-facing downtime.
- Verify behavior using unit/mock tests, syntax compilation, and static analysis only.

## 3. Verify Gate Before Concluding Turn
Every turn that edits code must execute and pass the **VERIFY GATE**:
```powershell
$env:PATH = "$env:APPDATA\Python\Python313\Scripts;$env:PATH"
python -m compileall -q src tests
python -m ruff check src tests
python -m pyflakes src
python -m pytest -q
python -m bandit -r src -c pyproject.toml
```
`py_compile` alone is forbidden as a verification gate because it misses NameErrors, unbound variables, and invalid imports.

## 4. Tracked Background Tasks (`create_tracked_task`)
- Never invoke `asyncio.create_task(...)` for fire-and-forget operations without storing a strong reference. Python's garbage collector can destroy unreferenced tasks mid-execution.
- Always use `create_tracked_task(coro, name=...)` from `src.utils.tasks`.
- Unhandled background task exceptions must be logged automatically.

## 5. Bounded Memory Caches
- Never introduce unbounded dictionaries or lists that grow infinitely with user queries, translation requests, or search history.
- Every cache must implement an eviction policy (LRU / FIFO with max capacity limit, e.g., 1000–2000 entries) and time-to-live (TTL).

## 6. Deprecated APIs & Exceptions
- Never use `datetime.utcnow()`. Use `datetime.now(timezone.utc)` or `discord.utils.utcnow()`.
- Never use `asyncio.get_event_loop()`. Use `asyncio.get_running_loop()`.
- Never write bare `except: pass` or `except Exception: pass`. Always log with appropriate severity (`logger.debug` for expected transient notices, `logger.warning` / `logger.error` with `exc_info=True` for faults) or catch specific exceptions (`except (discord.NotFound, discord.Forbidden): pass # best-effort cleanup`).
