# Kyro Discord Bot — Architectural Rules & Developer Directives

## 🚨 PERMANENT HARD RULE: ZERO OLD EMBEDS (COMPONENTS V2 ONLY)

1. **OLD EMBEDS ARE PERMANENTLY REMOVED & FORBIDDEN**:
   - Never use traditional `discord.Embed`, `embed=...`, or `.to_embed()` in any response, event, notification, or command.
   - Traditional embeds are completely abolished across the entire Kyro codebase.
   - Every single visual card, command feedback, error/warning notice, welcome/leave greeting, moderation log, and music player MUST strictly use **Discord Components V2 (Type 17 Containers)** via `KyroContainer` and `send_container_response()` from `src.utils.containers`.

2. **COMPONENTS V2 PROTOCOL CONSTRAINTS**:
   - All payloads use flag `32768` (`IS_COMPONENTS_V2`).
   - Discord API strictly disables the traditional top-level `content` and `embeds` fields when flag `32768` is active.
   - Any outer text, header, or user mention must be dispatched as a top-level `TextDisplay` component (`type: 10`) inside the `components` list.
   - Allowed mentions must maintain `{"parse": ["users"], "replied_user": True}` so legitimate user mentions ping properly, while suppressing `@everyone`, `@here`, and role mass-pings.

3. **GIT PUSH RESTRICTION**:
   - Never run `git push` unless the user explicitly requests it in chat (e.g. "push kar de"). Local commits are created automatically, but remote push requires explicit user approval.
