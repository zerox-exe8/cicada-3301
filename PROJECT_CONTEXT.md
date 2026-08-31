# ⚡ Cicada 3301 Discord Bot — Comprehensive Technical Specification & AI System Context

> **Audience**: AI Coding Assistants (Claude / GPT), Lead System Architects, and Software Engineers.  
> **Purpose**: This document provides the complete, authoritative, and up-to-date architectural blueprint, database schemas, code conventions, and feature catalog of the **Cicada 3301** codebase.

---

## 1. 📋 System Overview & Identity

- **Bot Name**: Cicada 3301
- **Primary Prefix**: `?` (Configurable per-guild via `?prefix set`)
- **Default Rich Presence**: `?help • Developed by zerox.exe`
- **Lead Architect / Developer**: `zerox.exe`
- **Core Technology Stack**:
  - **Language & Runtime**: Python 3.11+
  - **Discord API Framework**: `discord.py` 2.4+ (Extended with Components V2 Layouts)
  - **Database Persistence**: Supabase (Cloud PostgreSQL) via `asyncpg` connection pool
  - **HTTP Server**: `aiohttp` Keep-Alive & Payment Webhook Server on port `8080`
  - **Payment Gateway**: Razorpay API (Automated checkout in `$USD` and `₹INR` with HMAC-SHA256 webhook fulfillment)
  - **Cloud Hosting Platform**: Render.com (Web Service with 24/7 background worker)

---

## 2. 🏛️ Core Architectural Pillars & Philosophy

### A. Hybrid 0ms In-Memory Caching (Zero-Lag Execution)
Cicada 3301 strictly enforces a **Cache-First Architecture**:
1. **Startup Warm-Up**: Upon connection (`setup_hook` in `src/core/bot.py`), all critical state tables (`guild_prefixes`, `developer_ids`, `blacklists`, `system_state`, `guild_logs`, `guild_premium`, `user_premium`) are preloaded into memory dictionaries.
2. **Instant Message Hot-Path Execution**: Message processing, prefix parsing, blacklist validation, maintenance guards, and premium entitlement checks resolve in memory at **`< 0.001ms`** without touching PostgreSQL.
3. **Atomic Dual-Writes**: Any configuration update (e.g. `?prefix set`, `?grantpremium`, `?revokepremium`, payment fulfillment) atomically updates PostgreSQL first, then instantly updates the in-memory cache dictionary.

### B. Discord Components V2 UI (Type 17 Containers)
Cicada 3301 completely rejects legacy, noisy Discord Embeds:
- All command feedback, tabbed dashboards, checkout cards, and error notices are built using native **Discord Components V2 (Type 17 Containers)** via `CicadaContainer` (`src/utils/containers.py`).
- Components include Text Displays (`type: 10`), Sections with Accessories (`type: 9`), Visual Separators (`type: 14`), and Action Rows (`type: 1`) for interactive buttons (`type: 2`, `style: 1` Blurple, `style: 2` Grey, `style: 3` Green, `style: 5` Link/URL).
- Dispatched via `send_container_response()` and edited interactively via `edit_container_response()` with fallback direct channel `PATCH` handling.

### C. Strict Custom Application Emoji Policy
- **Zero Standard Unicode Emoji Spam**: Generic unicode emojis (e.g. `🎁`, `⚡`, `💳`, `📊`, `🔑`, `✨`, `💎`, `🔴`, `🟢`) are never used in UI cards or embed text.
- **Dynamic Application Emoji Caching**: The bot automatically fetches and caches all custom Application Emojis uploaded to the Discord Developer Portal on startup (`self.bot.custom_emojis`). Fallbacks are styled markdown.

---

## 3. 🗄️ Database Schemas & Data Layer (Supabase PostgreSQL)

All 10 tables are defined and verified in `src/database/postgres.py`:

```sql
-- 1. Custom Per-Guild Prefixes
CREATE TABLE IF NOT EXISTS guild_prefixes (
    guild_id BIGINT PRIMARY KEY,
    prefix VARCHAR(10) NOT NULL,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 2. Developer & Bot Owners
CREATE TABLE IF NOT EXISTS developer_ids (
    user_id BIGINT PRIMARY KEY,
    added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 3. Global Blacklists (Users & Guilds)
CREATE TABLE IF NOT EXISTS blacklists (
    target_id BIGINT PRIMARY KEY,
    target_type VARCHAR(10) NOT NULL, -- 'user' or 'guild'
    reason TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 4. Global System State & Maintenance
CREATE TABLE IF NOT EXISTS system_state (
    key VARCHAR(50) PRIMARY KEY,
    value JSONB NOT NULL,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 5. Modular Audit Logging Channels
CREATE TABLE IF NOT EXISTS guild_logs (
    guild_id BIGINT PRIMARY KEY,
    all_channel_id BIGINT,
    mod_channel_id BIGINT,
    message_channel_id BIGINT,
    member_channel_id BIGINT,
    server_channel_id BIGINT,
    voice_channel_id BIGINT
);

-- 6. Premium Cryptographic License Keys
CREATE TABLE IF NOT EXISTS premium_keys (
    key VARCHAR(64) PRIMARY KEY,
    duration_days INT NOT NULL,           -- 0 = Lifetime
    target_type VARCHAR(20) DEFAULT 'guild', -- 'guild' or 'user'
    created_by BIGINT NOT NULL,
    is_used BOOLEAN DEFAULT FALSE,
    redeemed_by BIGINT,
    redeemed_target_id BIGINT,
    redeemed_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 7. Active Server Subscriptions (Guild Tier)
CREATE TABLE IF NOT EXISTS guild_premium (
    guild_id BIGINT PRIMARY KEY,
    tier VARCHAR(50) DEFAULT 'pro',
    activated_by BIGINT,
    key_used VARCHAR(64),
    expires_at TIMESTAMP,                 -- NULL = Lifetime
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 8. Active Personal VIP Subscriptions (User Tier)
CREATE TABLE IF NOT EXISTS user_premium (
    user_id BIGINT PRIMARY KEY,
    tier VARCHAR(50) DEFAULT 'pro',
    key_used VARCHAR(64),
    expires_at TIMESTAMP,                 -- NULL = Lifetime
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 9. Permanent Customer Intelligence & Repeat Buyers Analytics
CREATE TABLE IF NOT EXISTS premium_customers (
    target_id BIGINT PRIMARY KEY,
    target_type VARCHAR(20) DEFAULT 'user',
    total_redemptions INT DEFAULT 1,
    total_days_purchased INT DEFAULT 0,
    first_redeemed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_redeemed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 10. Automated Payment Transactions & Webhooks
CREATE TABLE IF NOT EXISTS payment_transactions (
    id SERIAL PRIMARY KEY,
    razorpay_order_id VARCHAR(64),
    razorpay_payment_id VARCHAR(64) UNIQUE,
    razorpay_payment_link_id VARCHAR(64),
    discord_user_id BIGINT NOT NULL,
    guild_id BIGINT,
    target_type VARCHAR(20) NOT NULL,      -- 'guild' or 'user'
    duration_days INT NOT NULL,
    plan_tier VARCHAR(50) DEFAULT 'pro',
    amount_smallest_unit INT NOT NULL,     -- Smallest currency unit (paise for INR, cents for USD)
    currency VARCHAR(10) DEFAULT 'INR',
    status VARCHAR(20) DEFAULT 'created',  -- created | paid | failed | refunded
    is_trial BOOLEAN DEFAULT FALSE,
    last_reminder_sent_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    paid_at TIMESTAMP
);
```

---

## 4. 💳 End-to-End Automated Payment & Monetization Architecture

Located in `src/core/pricing.py`, `src/cogs/premium/purchase.py`, `src/core/server.py`, and `src/managers/premium_manager.py`:

### A. Centralized Pricing Structure (`src/core/pricing.py`)
Provides transparent dual-currency display (`$USD` & `₹INR`) with standard settlement:
- **3-Day Free Trial**: `$0.00 / ₹0` (`3d` — 1-time claim per server, Administrator permission required).
- **1 Month Pro**: `$4.99 / ₹399` (`30d` — Recommended starting plan).
- **3 Months Pro**: `$11.99 / ₹999` (`90d` — Save 20%).
- **1 Year Pro**: `$39.99 / ₹3,299` (`365d` — Annual Enterprise Package).
- **Lifetime Pro**: `$69.99 / ₹5,799` (Permanent VIP Access, zero recurring fees).

### B. Interactive 3-Tab Checkout Console (`?buy`)
- **Tab 1 `[Overview & Guide]`**: Explains starting recommendations and lists exact Pro superpowers unlocked.
- **Tab 2 `[Plans & Checkout]`**: Displays dual-currency plan breakdown with 1-click Action Row purchase buttons.
- **Tab 3 `[Free vs Pro]`**: Clean side-by-side comparison of Free tier limits vs Pro superpowers.
- **Permission Guard**: The 3-Day Free Trial requires `Administrator` or `Manage Server` permissions so members cannot waste the server's one-time trial. Paid plans are open to all members (like Server Boosting / Community Gifting).

### C. Automated Razorpay Payment Link Generation
1. Clicking a plan button rate-limits abuse, contacts Razorpay API (`/v1/payment_links`), and embeds transaction metadata in `notes`.
2. Inserts a row into `payment_transactions` with `status='created'`.
3. Sends a direct **"Pay via Razorpay"** URL link button to the user's DM (with ephemeral channel fallback).

### D. Webhook Fulfillment & Concurrency Security (`POST /webhook/razorpay`)
1. **HMAC-SHA256 Signature Verification**: Verifies `X-Razorpay-Signature` against `RAZORPAY_WEBHOOK_SECRET`. Rejects unauthorized calls before database execution.
2. **Race-Condition-Free Atomic Update**: Uses atomic conditional SQL:
   ```sql
   UPDATE payment_transactions
   SET status = 'paid', razorpay_payment_id = $1, paid_at = CURRENT_TIMESTAMP
   WHERE (razorpay_payment_id = $1 OR razorpay_payment_link_id = $2) AND status != 'paid'
   RETURNING id, guild_id, discord_user_id, duration_days, target_type, amount_smallest_unit, currency;
   ```
   If 0 rows are returned, concurrent retries are discarded safely without duplicate grants.
3. **Database Cross-Validation**: Reads `duration_days` and `guild_id` from the secure database row rather than trusting client-side payload notes alone.
4. **Internal Grant Call**: Calls existing `await self.bot.premium_mgr.grant_premium()` (zero duplicate code).
5. **Instant Webhook Acknowledgment (<20ms)**: Returns HTTP 200 immediately, dispatching customer receipt DMs via non-blocking background tasks (`asyncio.create_task`) to prevent Razorpay webhook timeouts.
6. **Refund Reversal**: On `refund.processed` / `payment.refunded`, updates status to `refunded` and automatically revokes Pro tier via `revoke_premium()`.

### E. Proactive Renewal Reminders
- The hourly `expiry_sweeper` checks subscriptions expiring within **2–3 days (48–72 hours)**.
- If no reminder was sent in the current billing cycle, sends a `CicadaContainer` DM notice to the server owner prompting them to renew via `?buy`.

---

## 5. 📂 Codebase Directory Map

```
Cicada 3301/
├── .env / .env.example / render.yaml / requirements.txt / README.md / PROJECT_CONTEXT.md
├── assets/Cicada 3301 banner.jpeg
│
└── src/
    ├── main.py                  # Bootstrap: logging setup, signal handling, runs CicadaBot
    │
    ├── core/
    │   ├── bot.py               # Custom commands.Bot with setup_hook and dynamic cog loader
    │   ├── config.py            # Validates environment variables (BOT_TOKEN, RAZORPAY keys, etc.)
    │   ├── context.py           # CustomContext with send_success, send_error, send_container
    │   ├── pricing.py           # Centralized dual-currency plan definitions ($USD / ₹INR)
    │   └── server.py            # aiohttp server (Port 8080: /health & /webhook/razorpay)
    │
    ├── database/
    │   ├── base.py              # Abstract database interface
    │   └── postgres.py          # asyncpg Supabase connection pool & all 10 table schemas
    │
    ├── managers/
    │   ├── blacklist_manager.py # In-memory blacklist cache for users & servers
    │   ├── guild_manager.py     # In-memory prefix cache & command disabling
    │   ├── log_manager.py       # In-memory logging channel mappings
    │   ├── permission_manager.py# In-memory developer IDs check
    │   ├── premium_manager.py   # Subscriptions, keys, customer analytics, sweeper, reminders
    │   └── system_manager.py    # Global maintenance mode & global command toggles
    │
    ├── utils/
    │   ├── containers.py        # CicadaContainer (Type 17), send/edit container response
    │   ├── decorators.py        # @require_guild_premium, @require_user_premium
    │   ├── emojis.py            # Dynamic custom Application Emoji resolver
    │   ├── embeds.py            # Legacy embed helpers
    │   ├── logger.py            # Central colorlog & rotating file logger
    │   └── views.py             # Discord UI Views
    │
    ├── errors/
    │   ├── exceptions.py        # Custom domain exceptions
    │   └── handler.py           # Global on_command_error listener & error containers
    │
    ├── events/
    │   ├── command_handler.py   # Prefix resolution, blacklist & maintenance checks
    │   ├── guild_events.py      # on_guild_join / on_guild_remove logging
    │   └── ready.py             # on_ready synchronization & rich presence
    │
    └── cogs/
        ├── admin/
        │   ├── prefix.py        # ?prefix, ?prefix set, ?prefix reset
        │   └── sync.py          # ?sync [guild/global]
        │
        ├── general/
        │   ├── help.py          # ?help with dropdown category navigation
        │   └── ping.py          # ?ping with gateway and database latency
        │
        ├── logging/
        │   ├── config.py        # ?setlogs, ?logchannel
        │   └── events.py        # Real-time event listeners (joins, leaves, message deletes)
        │
        └── premium/
            ├── license.py       # ?keys, ?premium, ?redeem, ?grantpremium, ?revokepremium, ?customers, ?clearkeys, ?generatekey
            └── purchase.py      # ?buy, tabbed checkout console, 3-day trial activation
```

---

## 6. 📜 Complete Commands Catalog

| Command | Category | Permissions | Description |
| :--- | :--- | :--- | :--- |
| `?buy` | Premium | Everyone | Interactive 3-tab checkout console for Server Pro plans ($USD/₹INR/Trial) |
| `?premium` | Premium | Everyone | Dual-Status card (Server Plan + Personal VIP Status) |
| `?redeem <key>` | Premium | Admin / Owner | Redeem license key with anti-brute-force protection |
| `?generatekey <dur> [type]`| Premium | Developer Only | Generate cryptographic key (`30d`, `1y`, `lifetime`) |
| `?keys` | Premium | Developer Only | Interactive Tabbed Console (**Active**, **Available**, **History**) |
| `?customers` | Premium | Developer Only | Customer lifetime analytics & repeat buyers report |
| `?clearkeys [used/all]` | Premium | Developer Only | Purge old keys with automated JSON backup export |
| `?grantpremium <target> [dur]` | Premium | Developer Only | Directly grant premium with smart auto-detection & stacking |
| `?revokepremium <target>` | Premium | Developer Only | Directly revoke premium with smart cache auto-detection |
| `?help [command]` | General | Everyone | Interactive Components V2 Help Menu with category select |
| `?ping` | General | Everyone | Real-time Gateway latency and Supabase Database ping |
| `?prefix` | Admin | Everyone | View active server prefix |
| `?prefix set <prefix>` | Admin | Administrator | Update custom command prefix for server |
| `?prefix reset` | Admin | Administrator | Reset server prefix to default `?` |
| `?sync [guild/global]` | Admin | Developer Only | Sync application slash commands with Discord API |
| `?play <query>` | Music | Everyone | Play 320kbps CD Master / YouTube audio in voice channel |
| `?pause` / `?resume` | Music | Everyone | Pause or resume current track playback |
| `?skip` | Music | Everyone | Skip current track to next in queue |
| `?stop` | Music | Everyone | Stop playback, clear queue and disconnect from voice |
| `?queue` | Music | Everyone | View upcoming server playlist in Type 17 Container card |
| `?nowplaying` | Music | Everyone | Display now playing card with interactive button controls |
| `?loop [off/track/queue]` | Music | Everyone | Toggle repeating track or playlist |
| `?shuffle` | Music | Everyone | Randomize upcoming playlist order |
| `?clear` | Music | Everyone | Clear all upcoming songs from queue |
| `?remove <pos>` | Music | Everyone | Remove a specific track from queue by position |
| `?volume <0-150>` | Music | Everyone | Adjust stream playback volume |

---

## 7. 🗺️ Master Roadmap (Next Modules To Build)

1. **Module 1: Advanced Moderation & Case System** (`src/cogs/moderation/`):
   - `?ban`, `?unban`, `?kick`, `?timeout` / `?mute`, `?untimeout`, `?purge` / `?clear`.
   - Comprehensive Warn & Infraction Case Files (`?warn`, `?warnings`, `?delwarn`, `?cases`).
   - DM infraction notices & automated mod-log publishing.
2. **Module 2: Dynamic Temporary Voice Rooms (VoiceMaster)** (`src/cogs/voice/`):
   - `➕ Join to Create` automated dynamic voice channel spawning.
   - Zero-clutter auto-deletion when empty.
   - Interactive in-voice Components V2 control card (Lock, Unlock, Hide, Limit, Rename, Transfer).
3. **Module 3: Enterprise Support Tickets & HTML Transcripts** (`src/cogs/tickets/`):
   - Multi-category 1-click ticket panels with custom dropdowns.
   - Auto-generated, standalone HTML web transcripts saved to cloud storage.
4. **Module 4: Autonomous AutoMod & Threat Interceptor** (`src/cogs/automod/`):
   - Anti-Spam (token-bucket rate limiting), Anti-Invite, Anti-Link, Anti-GhostPing.
   - Anti-Raid Panic Lock and mass-join quarantine triggers.
5. **Module 5: Workflow Automation Engine** (`src/cogs/automation/`):
   - Temporary / Paid role gating with expiration countdowns.
   - Scheduled auto-messages and recurring server campaigns.

---

## 8. 🚨 Strict Code Rules for Collaborators & AI

1. **Zero Standard Unicode Emojis**: Never use standard emojis (`🎁`, `⚡`, `💳`, etc.). Use custom Application Emojis from `self.bot.custom_emojis` or clean markdown formatting.
2. **Components V2 Only**: Build user-facing cards with `CicadaContainer` (`src.utils.containers`). Do not use old `discord.Embed`.
3. **Never Query DB in Message Hot-Paths**: Always use in-memory caches (`guild_mgr`, `premium_mgr`, `sys_mgr`, `blacklist_mgr`, `perm_mgr`).
4. **Zero Dummy/Mock Data**: All features must integrate with real database tables and production APIs.
5. **Clean Git Commit Policy**: Always stage and commit files cleanly with conventional commit prefixes (`feat:`, `fix:`, `refactor:`, `docs:`).
