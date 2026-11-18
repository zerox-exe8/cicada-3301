---
name: kyro-dev
description: Dedicated development skill for Kyro Discord Bot. Use whenever adding features, fixing bugs, or analyzing code in Kyro (Music, Moderation, Antinuke, Components V2, Database, or Core).
---

# Kyro Development Specialist Skill

This skill contains deep architectural runbooks, common debugging workflows, and implementation standards for developing and maintaining the **Kyro Discord Bot**.

---

## 1. Subsystem Architecture Map

```
Kyro/
├── src/
│   ├── core/                  # Bot base, config, context, health/dashboard server
│   │   ├── bot.py             # KyroBot (discord.ext.commands.AutoShardedBot)
│   │   ├── config.py          # Environment credentials, owner/dev IDs, flags
│   │   ├── context.py         # CustomContext with enhanced container reply helpers
│   │   └── server.py          # Bearer-authenticated health & dashboard API server
│   ├── database/              # PostgreSQL asyncpg database pool & abstractions
│   │   ├── base.py            # Database base interface
│   │   └── postgres.py        # Connection pooling, table migrations, query helpers
│   ├── repositories/          # Modular SQL data repositories
│   ├── utils/                 # Visual components, emojis & background tasks
│   │   ├── containers.py      # KyroContainer (Components V2, Type 17, Type 14 separators)
│   │   ├── emojis.py          # EmojiRegistry (Discord Application Emojis loader)
│   │   ├── tasks.py           # Tracked background tasks (create_tracked_task)
│   │   └── image_tools.py     # Safe bounded banner/image processor
│   ├── managers/              # Business logic & state managers (antinuke, translator, etc.)
│   └── cogs/                  # Modular discord cogs
│       ├── music/             # High-performance Wavelink 3 Lavalink music engine
│       │   ├── _player.py     # GuildPlayer lifecycle, concurrency locks, state
│       │   ├── _views.py      # MusicControlView interactive buttons
│       │   ├── _extractor.py  # NativeExtractor (JioSaavn CDN & Spotify metadata)
│       │   ├── _autoplay.py   # NativeSmartAutoplay algorithm
│       │   └── _commands/     # Modular music commands (play, queue, skip, controls...)
│       ├── moderation/        # Moderation commands (ban, kick, timeout, purge, warn...)
│       ├── antinuke/          # High-speed server protection & whitelist engines
│       ├── meeting/           # Voice meeting recording, DAVE MLS decryption & Gemini notes
│       ├── utility/           # Server utility, embeds, AFK & info commands
│       └── developer/         # Bot owner commands (eval, sql, sync, dm, portal...)
├── tests/                     # Unit, regression, and security smoke test suite
└── AGENTS.md                  # Project root safety & operational guidelines
```

---

## 2. Standard Development Workflows

### A. Music Command & Engine Workflows
1. **Always acquire `_connect_lock` for voice channel operations:**
   ```python
   async with player._connect_lock:
       # connect or move logic
   ```
2. **Sanitize Track Titles:**
   Never construct markdown links without replacing square brackets:
   ```python
   safe_title = (track.title or "Track").replace("[", "(").replace("]", ")")
   link = f"[{safe_title}]({track.url})" if track.url else safe_title
   ```
3. **Now Playing Card Dispatch:**
   - Only edit `message_to_edit` if explicitly provided (e.g. converting `Searching...` card).
   - On track changes from queue, skip, or autoplay, always send a new card via `send_container_response(player.home_channel, container, view=view)`.
4. **Interactive Button Deferrals:**
   All button handlers in `MusicControlView` must use:
   ```python
   if not interaction.response.is_done():
       await interaction.response.defer(ephemeral=True)
   ```

### B. Moderation Command Workflows
1. **Check Role Hierarchy First:**
   Ensure `ctx.author.top_role > target.top_role` and `ctx.guild.me.top_role > target.top_role`.
2. **Execute Action Before Database Logging:**
   Attempt the Discord API operation (e.g. timeout/ban) first; log to `modlogs` only if the action succeeds.
3. **Container Response:**
   Format success alerts using `KyroContainer` with the designated custom emoji and clean reason block.

### C. Antinuke Workflows
1. **Zero External Dependencies in Event Loop:**
   Antinuke checks must run entirely in-memory using cached whitelists and rate-limit buckets. Never await heavy network operations or unbounded queries before applying safety punishments.

---

## 3. Mandatory Pre-Completion Verification Checklist

Before reporting completion on any coding task:
1. **Full Verify Gate:**
   Execute the gate commands (never rely on `py_compile` alone):
   ```powershell
   $env:PATH = "$env:APPDATA\Python\Python313\Scripts;$env:PATH"
   python -m compileall -q src tests
   python -m ruff check src tests
   python -m pyflakes src
   python -m pytest -q
   python -m bandit -r src -c pyproject.toml
   ```
2. **Ponytail Safety Rule:**
   The `ponytail` skill/workflow never overrides security, verification, or regression-test rules.
3. **UI Integrity:**
   Ensure no Components V2 containers have broken separators, nested markdown brackets, or missing custom emojis.
4. **Safety Guarantee:**
   Confirm that the bot was NOT started locally and no token or secret was leaked or logged.
