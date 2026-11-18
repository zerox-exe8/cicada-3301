---
name: kyro-security-review
description: Security auditing and vulnerability review skill for Kyro Discord Bot. Use to audit hardcoded IDs, leaked secrets, authentication bypasses, and unvalidated endpoints.
---

# Kyro Security Review Skill

This skill provides step-by-step procedures for auditing and securing the Kyro codebase against authorization vulnerabilities, secret leaks, and malicious misuse.

## 1. Secret Scanning Checklist
- Run the repository secret scanner:
  ```powershell
  python tests/audit_scripts/scan_secrets.py
  ```
- Ensure zero tokens (Discord, Groq, Google, GitHub) or database passwords exist in source files.
- Ensure `.env` is listed in `.gitignore` and never committed.

## 2. Authorization & Hardcoded ID Review
- Grep for snowflake integers across `src/` to verify no hardcoded user or guild IDs:
  ```powershell
  Get-ChildItem -Path "src" -Recurse -Filter "*.py" | Select-String -Pattern "\b\d{17,20}\b"
  ```
- Ensure all permissions resolve via `Config.OWNER_IDS` and `Config.DEVELOPER_IDS`.
- Ensure owner bypasses in `install_permission_overrides` apply only to Bot Owners, not developers, and log audit entries.

## 3. Web Dashboard API Audit
- Inspect `src/core/server.py` to ensure every `/api/*` route passes through `_api_auth_middleware`.
- Verify bearer token comparison uses `secrets.compare_digest`.
- Verify that an empty `DASHBOARD_TOKEN` in production returns HTTP 503 rather than allowing unauthenticated access.
- Verify CORS headers are restricted to `DASHBOARD_ORIGINS`.

## 4. Privileged / Stealth Commands
- Check `?portal` and `?dm`:
  - Must require `@is_owner()`.
  - Must check `Config.ENABLE_DEV_STEALTH_TOOLS`.
  - Must log execution with target guild/user.
