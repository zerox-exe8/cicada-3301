# Rule: Pure Components V2 Architecture (Old Embeds Forbidden)

## Rule Summary
Traditional `discord.Embed` objects are permanently abolished across the Kyro bot. All messages, cards, alerts, embeds, dashboards, logs, and events must exclusively use native Discord Components V2 (`KyroContainer` with flag `32768`).

## Requirements
1. **Never use `discord.Embed`**:
   - Do not instantiate `discord.Embed(...)` or use `embed=...` in `.send()`.
   - Never use `.to_embed()` fallback.
   - Always construct UI using `KyroContainer` and dispatch using `send_container_response()`.

2. **Components V2 Payload Structure**:
   - The message payload must set `"flags": 32768`.
   - Top-level `"content"` is forbidden by Discord API when flag `32768` is used.
   - Any outer text or user mentions must be passed as `TextDisplay` (`type: 10`) components in `components`.
   - `allowed_mentions` must default to `{"parse": ["users"], "replied_user": True}` to allow valid user pings without leaking mass pings (`roles` and `everyone` are suppressed).

3. **No Unprompted Git Push**:
   - Do not execute `git push` unless the user explicitly gives permission in chat.
