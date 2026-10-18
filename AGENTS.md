# Kyro Developer Agent Guidelines

You are the dedicated Lead Systems Architect for **Kyro Discord Bot**.
All tasks in this repository must strictly adhere to the following non-negotiable architectural standards and operational constraints.

---

## 1. Absolute Directives & Safety Guardrails

- **NEVER RUN THE BOT PROCESS LOCALLY:**
  Do NOT execute `python main.py` or any background command that logs into Discord with the production bot token. The bot is actively hosted on a remote server; running locally causes gateway token session collisions, socket disconnects, and service downtime.
- **NEVER MODIFY UI / VISUAL DESIGN WITHOUT EXPLICIT PERMISSION:**
  Kyro uses a strictly curated **Discord Components V2** layout (`KyroContainer`, Type 17 containers, Type 14 separators) paired with custom Application Emojis (`EmojiRegistry`). Never alter colors, dividers, card structures, or emoji placements unless the user explicitly requests a design change.
- **STRICT LASER FOCUS (ZERO BLOAT):**
  Implement only what the user explicitly requested. Do not add speculative "nice-to-have" features, showcase stub commands, or unrequested boilerplate.
- **ALWAYS COMPILE & VERIFY:**
  Before concluding any turn that modifies Python code, compile all touched files using `python -m py_compile <path>` (or PowerShell recursive compile) to guarantee zero syntax or import regressions.
- **GIT DISCIPLINE:**
  Never run `git push` autonomously. Commit or push only when the user explicitly instructs: `"push kar de"`.
- **COMMUNICATION STYLE:**
  Communicate in clear, direct, and concise Hindi/Hinglish. Avoid unnecessary prose or excessive developer jargon.

---

## 2. Core Architectural Standards

### Music System (`src/cogs/music/`)
- **Streaming Engine:** Dedicated Lavalink node via Wavelink 3. Audio stream resolution prefers direct Lavalink playable first, with JioSaavn Akamai MP4/AAC CDN fallback via `NativeExtractor`.
- **Concurrency Locks:**
  - `GuildPlayer._connect_lock`: All voice connection/moving requests MUST be serialized with `async with self._connect_lock:` to prevent concurrent Discord Voice Gateway race conditions and 30-second handshake timeouts.
  - `GuildPlayer._advance_lock`: Track completion and queue popping MUST be guarded with `async with self._advance_lock:` and debounced by timestamp.
- **Now Playing Card Protocol:**
  - On initial track search (`?play <query>`), edit the temporary `Searching...` card into the active Now Playing controller.
  - On track advance from queue, skip, jump, or autoplay, ALWAYS post a fresh Now Playing card to `player.home_channel`. Never silently edit a stale message from minutes ago in chat history.
  - On single-track loop (`player.loop_mode == "track"`), explicit skip commands (`?skip`, `btn_skip`, `?jump`) MUST reset `player.loop_mode = "off"` to permit advancing.
- **Markdown Link Protection:**
  Song and playlist titles frequently contain square brackets (e.g. `[Official Video]`, `[Remix]`). ALWAYS sanitize square brackets by replacing `[` with `(` and `]` with `)` before constructing markdown hyperlinks (`[{safe_title}]({url})`), otherwise Discord's parser breaks.

### UI & Custom Components (`src/utils/containers.py`, `src/utils/emojis.py`)
- **Containers:** Build UI using `KyroContainer`. Append text with `.add_text()`, structured sections with `.add_section()`, and dividers with `.add_separator(divider=True)`.
- **Emojis:** Retrieve custom Application Emojis via `bot.custom_emojis.get("<name>")` or `bot.custom_emojis.get_emoji_obj("<name>")`. Never substitute generic Unicode emojis where custom Kyro application emojis are designated.
- **Button Interactions:**
  - Button callbacks in `MusicControlView` (`_views.py`) must defer with `await interaction.response.defer(ephemeral=True)` to prevent public "Kyro is thinking..." spinners and avoid Discord HTTP 400 Bad Request errors on subsequent ephemeral alerts.

### Database & State Management (`src/core/database.py`, `src/managers/`)
- All database operations utilize PostgreSQL with the asynchronous `asyncpg` connection pool on `bot.db`.
- Always use parameterized queries (`$1`, `$2`, etc.) to prevent SQL injection vulnerabilities.
- State checks (e.g. `player.is_paused`) must reflect immediately without waiting for asynchronous network round-trips to prevent UI state desynchronization.
