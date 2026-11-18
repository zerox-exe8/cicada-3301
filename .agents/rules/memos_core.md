# MemOS Foundational Core Rule

You are operating inside the **Kyro Systum Engine** workspace.
`MemOS` (`../MemOS` or configured path) is the primary Memory Operating System for AI operations when present. If MemOS is not present or unavailable in the environment, the bot relies on its own root `AGENTS.md`, `AUDIT.md`, and dedicated `.agents/rules/` specifications.

## Mandatory Operating Rules:
1. **MemOS Memory Primacy**:
   - Every task, reasoning step, and code modification (regardless of size) must utilize and align with MemOS architecture and memory standards when present.
   - Ground all actions in the project's episodic memory (prior decisions, lessons, bug root causes) and semantic memory (architecture, protocols, audio pipelines).
   - If MemOS is not loaded, fallback directly to the verified repo policies in `AGENTS.md`, `AUDIT.md`, and `.agents/rules/`.
2. **Persistent Context & Zero Blind Edits**:
   - Never make isolated or blind modifications to components without verifying dependencies against project architectural patterns.
   - When modifying audio resolution or streaming, respect the established Lavalink + Wavelink 3 playback protocol and the `NativeExtractor` search/resolution cascade. The KyroLink native engine and standalone Engine service have been deprecated and removed from this workspace.
3. **Safety & Git Boundaries**:
   - Never run `python main.py` or start the bot locally.
   - Never run `git push` or `git commit` autonomously; wait for the user's explicit instruction (`"push kar de"`).
