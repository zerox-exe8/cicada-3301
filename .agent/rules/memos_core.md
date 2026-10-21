# MemOS Foundational Core Rule

You are operating inside the **Kyro Systum Engine** workspace.
`MemOS` (`M:\Kyro Systum Engine\MemOS`) is the primary Memory Operating System for all AI operations.

## Mandatory Operating Rules:
1. **MemOS Memory Primacy**:
   - Every task, reasoning step, and code modification (regardless of size) must utilize and align with MemOS architecture and memory standards.
   - Ground all actions in the project's episodic memory (prior decisions, lessons, bug root causes) and semantic memory (architecture, protocols, audio pipelines).
2. **Persistent Context & Zero Blind Edits**:
   - Never make isolated or blind modifications to components without verifying dependencies against MemOS patterns.
   - When modifying audio resolution or streaming, respect the established Lavalink + Wavelink 3 playback protocol and the `NativeExtractor` search/resolution cascade. The KyroLink native engine and the standalone Engine service have been removed from this workspace.
3. **Safety & Git Boundaries**:
   - Never run `python main.py` or start the bot locally.
   - Never run `git push` autonomously; wait for the user's explicit instruction (`"push kar de"`).
