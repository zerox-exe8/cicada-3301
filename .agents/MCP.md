# Recommended MCP Servers for Kyro Development

To assist AI coding agents working on the Kyro Discord Bot, the following Model Context Protocol (MCP) servers are recommended:

---

## 1. Discord Documentation & API Lookup
- **Name**: `discord-api-docs`
- **Purpose**: Provides live access to the official Discord Developer Documentation and `discord.py` API references.
- **Capabilities**:
  - Components V2 specifications (Type 17 Container, Type 14 Separator, Type 11 Media).
  - Voice Gateway v8 / v4 DAVE protocol state transitions.
  - Interaction response constraints and timeout guidelines.

---

## 2. GitHub MCP Server
- **Name**: `github`
- **Purpose**: Integrates with the remote GitHub repository for inspecting pull requests, commit trees, and CI workflow run logs.
- **Capabilities**:
  - Inspecting GitHub Actions CI runs (`ci.yml`).
  - Checking commit history and reviewing pull request diffs.
  - Tracking release branches and tags.

---

## 3. Read-Only PostgreSQL Database Inspector
- **Name**: `postgres-readonly`
- **Purpose**: Allows read-only schema inspection, table verification, and query optimization without risking accidental data mutation.
- **Capabilities**:
  - Inspecting active PostgreSQL schemas and table definitions (`guild_settings`, `system_developers`, `active_tickets`, etc.).
  - Verifying column migrations and indexes.
  - Checking connection pool latency and query performance metrics.
