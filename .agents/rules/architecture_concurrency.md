# Kyro Architecture & Concurrency Standards

Architectural invariants governing state consistency, voice gateway synchronization, and database operations.

---

## 1. Voice Connection & Concurrency Serialization
- **`GuildPlayer._connect_lock`**: Every voice connection, disconnection, or move operation (`connect_voice`, `move_to`) MUST be serialized with `async with self._connect_lock:`. This prevents concurrent Discord Voice Gateway handshakes, state desynchronization, and 30-second connection timeouts.
- **`GuildPlayer._advance_lock`**: Track completion, queue popping, and autoplay queuing MUST be serialized with `async with self._advance_lock:` and debounced by timestamp to eliminate double-advance race conditions.

## 2. Now Playing Card Lifecycle Protocol
- **Initial Search (`?play <query>`)**: Edit the initial temporary `Searching...` container directly into the active Now Playing controller.
- **Track Advance (Queue / Skip / Autoplay)**: ALWAYS dispatch a fresh Now Playing card to `player.home_channel`. Never silently edit a stale message located high up in earlier chat history.
- **Single-Track Loop Exemption**: If `player.loop_mode == "track"`, an explicit skip command (`?skip`, `btn_skip`, `?jump`) MUST automatically reset `player.loop_mode = "off"` to allow the queue to progress to the next track.

## 3. Database Execution & Non-Idempotent Operations
- `PostgresDatabase.execute(...)`: Retry logic is permitted ONLY during connection pool acquisition (`self.pool.acquire()`).
- Once a SQL query has been transmitted to the database wire, it must NEVER be retried automatically upon a timeout or disconnection. Automatic retries of non-idempotent statements (`INSERT`, `UPDATE`, `DELETE`) risk duplicate writes or corrupted state.
- Parameter placeholder transformation in `_convert_query` must be quote-aware so that literal question marks (`?`) inside strings or JSON blobs are preserved without being converted to positional parameter placeholders (`$1`, `$2`).

## 4. UI & Discord Components V2 Standards
- All bot interactions must utilize `KyroContainer` (Type 17 containers, Type 14 separators).
- Use custom Discord Application Emojis via `bot.custom_emojis.get("<name>")`. Never substitute arbitrary unicode emojis where application emojis are designated.
- Sanitize square brackets in media titles (`[` to `(`, `]` to `)`) before constructing Markdown hyperlinks (`[{safe_title}]({url})`).
- Button callbacks in `MusicControlView` must defer promptly using `await interaction.response.defer(ephemeral=True)` to prevent public thinking spinners and avoid HTTP 400 Bad Request responses on subsequent interaction alerts.
