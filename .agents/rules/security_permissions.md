# Kyro Security & Permissions Standards

These security mandates protect Kyro from credential leaks, privilege escalation, and unauthorized access.

---

## 1. Zero Hardcoded User IDs
- **NEVER** hardcode Discord user IDs in source code.
- All bot owner and developer permissions must resolve dynamically through `Config.OWNER_IDS` and `Config.DEVELOPER_IDS` parsed from environment variables, supplemented by the Discord application team/owner cache and the database `system_developers` table.
- Log only the count of configured IDs upon startup—never print or write the user IDs themselves to logs or chat.

## 2. Permission Overrides & Privilege Boundaries
- Global permission bypasses (`install_permission_overrides`) are restricted **strictly to Bot Owners**.
- Developers have access only to developer tooling (`src/cogs/developer/`), never automatic administrative bypass over server moderation or antinuke systems.
- Every invocation of an owner bypass must emit an INFO audit log detailing `(guild_id, command_name, user_id)`.

## 3. Web Dashboard API & CORS Protection
- All `/api/*` endpoints on `src/core/server.py` require Bearer token authentication via `Authorization: Bearer <DASHBOARD_TOKEN>`.
- Token comparison must use constant-time `secrets.compare_digest` to prevent timing attacks.
- If `DASHBOARD_TOKEN` is unset or empty in production, the API must be disabled (return HTTP 503) rather than left exposed.
- CORS must restrict `Access-Control-Allow-Origin` to origins listed in `DASHBOARD_ORIGINS`, never `*`.
- Health endpoints (`/health`) must never leak sensitive metrics such as server counts, user counts, or database topology.

## 4. Stealth Tools Gating
- Commands that perform privileged actions without clear public indication (such as `?portal` or `?dm`) must be restricted to Bot Owners and gated behind the `ENABLE_DEV_STEALTH_TOOLS=true` environment flag.
- DMs dispatched by developers must explicitly identify themselves in the footer (`Sent by a Kyro developer via Kyro Core Network`).
- Every execution of stealth commands must be recorded in security audit logs.

## 5. Secret Protection & Scanning
- Never commit credentials, tokens, webhook URLs, API keys, or database passwords.
- All secrets must be verified against `tests/test_secret_scanner.py` and `tests/audit_scripts/scan_secrets.py`.
- Automated CI must execute `bandit` and `pip-audit` to detect code vulnerabilities and supply-chain supply risks.
