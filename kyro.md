# ⚡ Kyro Discord Bot — Master Architectural Blueprint & System Context (`kyro.md`)

> **Lead Architect / Developer**: `zerox.exe`  
> **Bot Name**: Kyro | **Primary Prefix**: `?` (Configurable per-guild)  
> **Audience**: AI Coding Assistants, Lead System Architects, and Software Engineers.  
> **Purpose**: Single authoritative source of truth for the entire Kyro codebase. Contains all architectural rules, developer directives, database schemas, and feature specifications.

---

## 🚨 1. PERMANENT HARD RULES (CRITICAL DIRECTIVES)

### A. Zero Old Embeds — 100% Discord Components V2 Mandatory
- **Old Embeds Are Permanently Abolished**: Traditional `discord.Embed`, `embed=...`, and `.to_embed()` are strictly forbidden across the entire Kyro codebase.
- **Components V2 Only**: Every visual card, command feedback, error/warning notice, welcome/leave greeting, moderation log, and music player MUST use native **Discord Components V2 (Type 17 Containers)** via `KyroContainer` and `send_container_response()` from `src.utils.containers`.
- **Components V2 REST Constraints**:
  - All payloads use flag `32768` (`IS_COMPONENTS_V2`).
  - Discord API strictly forbids top-level `"content"` and `"embeds"` fields when flag `32768` is active.
  - Any outer message text, header, or user mention must be passed as a top-level `TextDisplay` component (`type: 10`) inside the `components` array.
  - `allowed_mentions` must default to `{"parse": ["users"], "replied_user": True}` to allow valid user pings without leaking mass pings (`roles` and `everyone` are suppressed).

### B. Git Push Restriction
- **Never run `git push` automatically**: Do not execute `git push` unless the user explicitly requests it in chat (e.g. "push kar de"). Local commits (`git commit`) are created automatically, but remote push requires explicit user approval every time.

### C. Zero Unicode Emoji Spam
- Generic unicode emojis (`🎁`, `⚡`, `💳`, `📊`, `🔑`, `✨`, `💎`, `🔴`, `🟢`) are forbidden in bot response cards.
- Use dynamic Application Emojis from `self.bot.custom_emojis` or clean markdown formatting.

### D. Zero DB Queries in Message Hot-Paths
- Message processing, prefix resolution, blacklist checks, and permissions must resolve in memory (`< 0.001ms`) via cache managers.

---

## 2. 📋 System Overview & Identity

- **Bot Name**: Kyro
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

## 3. 🏛️ Core Architectural Pillars

### A. Hybrid 0ms In-Memory Caching (Zero-Lag Execution)
Kyro strictly enforces a **Cache-First Architecture**:
1. **Startup Warm-Up**: Upon connection (`setup_hook` in `src/core/bot.py`), all critical state tables (`guild_prefixes`, `developer_ids`, `blacklists`, `system_state`, `guild_logs`, `guild_premium`, `user_premium`) are preloaded into memory dictionaries.
2. **Instant Message Hot-Path Execution**: Message processing, prefix parsing, blacklist validation, maintenance guards, and premium entitlement checks resolve in memory at **`< 0.001ms`** without touching PostgreSQL.
3. **Atomic Dual-Writes**: Any configuration update (e.g. `?prefix set`, `?grantpremium`, `?revokepremium`, payment fulfillment) atomically updates PostgreSQL first, then instantly updates the in-memory cache dictionary.

### B. Discord Components V2 UI (Type 17 Containers)
- Components include Text Displays (`type: 10`), Sections with Accessories (`type: 9`), Visual Separators (`type: 14`), and Action Rows (`type: 1`) for interactive buttons (`type: 2`, `style: 1` Blurple, `style: 2` Grey, `style: 3` Green, `style: 5` Link/URL).
- Dispatched via `send_container_response()` and edited interactively via `edit_container_response()`.

---

## 4. 🗄️ Database Schemas & Data Layer (Supabase PostgreSQL)

All tables are defined and managed in `src/database/postgres.py`:

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
    amount_smallest_unit INT NOT NULL,
    currency VARCHAR(10) DEFAULT 'INR',
    status VARCHAR(20) DEFAULT 'created',  -- created | paid | failed | refunded
    is_trial BOOLEAN DEFAULT FALSE,
    last_reminder_sent_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    paid_at TIMESTAMP
);

-- 11. Server Auto-Events (Welcome, Leave, Boost)
CREATE TABLE IF NOT EXISTS guild_events (
    guild_id BIGINT NOT NULL,
    event_type VARCHAR(20) NOT NULL,      -- 'welcome' | 'leave' | 'boost'
    channel_id BIGINT,
    embed_name VARCHAR(100),
    message_content TEXT,
    is_enabled BOOLEAN DEFAULT TRUE,
    dm_enabled BOOLEAN DEFAULT FALSE,
    dm_embed_name VARCHAR(100),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (guild_id, event_type)
);

-- 12. Modular Custom Container Embed Templates
CREATE TABLE IF NOT EXISTS embed_templates (
    id SERIAL PRIMARY KEY,
    guild_id BIGINT NOT NULL,
    embed_name VARCHAR(100) NOT NULL,
    payload JSONB NOT NULL,
    created_by BIGINT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (guild_id, embed_name)
);
```

---

## 5. 💳 Monetization & Payment Architecture

- **Pricing Engine** (`src/core/pricing.py`):
  - **3-Day Free Trial**: `$0.00 / ₹0` (1-time claim per server, Administrator permission).
  - **1 Month Pro**: `$4.99 / ₹399` (`30d`).
  - **3 Months Pro**: `$11.99 / ₹999` (`90d` — Save 20%).
  - **1 Year Pro**: `$39.99 / ₹3,299` (`365d` — Enterprise).
  - **Lifetime Pro**: `$69.99 / ₹5,799` (VIP, zero recurring fees).
- **Checkout Console (`?buy`)**: 3-Tab interactive Components V2 card (`[Overview]`, `[Plans & Checkout]`, `[Free vs Pro]`).
- **Webhook Security**: Razorpay HMAC-SHA256 signature verification on `/webhook/razorpay`. Idempotent updates prevent race conditions and duplicate grants.

---

## 6. 📂 Codebase Directory Map

```
Kyro/
├── kyro.md                      # Single master reference document
├── .env / .env.example          # Environment secrets
├── requirements.txt / render.yaml # Dependencies & cloud deployment config
│
└── src/
    ├── main.py                  # Bot entrypoint & runner
    ├── core/
    │   ├── bot.py               # KyroBot subclass with cache warming & dynamic cogs
    │   ├── config.py            # Environment configuration
    │   ├── context.py           # CustomContext with send_container, send_success, etc.
    │   ├── pricing.py           # Dual-currency pricing tier catalog
    │   └── server.py            # Uptime healthcheck & Razorpay webhook listener
    │
    ├── database/
    │   ├── base.py              # Abstract database base
    │   └── postgres.py          # Supabase PostgreSQL asyncpg connection pool
    │
    ├── managers/
    │   ├── blacklist_manager.py # In-memory blacklist cache
    │   ├── event_manager.py     # Welcome, leave, boost configuration cache
    │   ├── guild_manager.py     # Prefix & command enablement cache
    │   ├── log_manager.py       # Modular logging channels cache
    │   ├── permission_manager.py# Developer IDs & owner checking
    │   ├── premium_manager.py   # Subscriptions, keys, customer intelligence
    │   └── system_manager.py    # Maintenance mode & global command toggles
    │
    ├── utils/
    │   ├── containers.py        # KyroContainer (Components V2), send_container_response
    │   ├── placeholders.py      # Universal variable replacement engine
    │   ├── emojis.py            # Dynamic custom application emoji resolver
    │   ├── logger.py            # Colorlog & rotating file logging
    │   └── views.py             # Reusable Discord UI Views
    │
    └── cogs/
        ├── admin/               # Prefix & command synchronization
        ├── developer/           # Portal, DM, Avatar, BotName, Status
        ├── games/               # Hack, Nitro, Mimic
        ├── general/             # BotInfo, Help, Invite, Ping, Profile
        ├── moderation/          # Ban, Kick, Lock, Mute, Purge, Warn, ModLog
        ├── music/               # Lossless player, queue, controls, playlist manager
        ├── premium/             # License keys & buy console
        ├── security/            # Anti-Spam, Anti-Raid, Anti-GhostPing
        ├── ticket/              # Ticket panels & transcript logging
        └── utility/             # Welcome/Leave events, Embed builder, AFK, Snipe
```

---

## 7. 📜 Key Commands Summary

| Command | Category | Permissions | Description |
| :--- | :--- | :--- | :--- |
| `?welcome set` | Utility | Manage Guild | Bind channel, outer text, and embed for welcome cards |
| `?welcome test` | Utility | Manage Guild | Test live welcome message and mention in channel |
| `?embed create <name>` | Utility | Manage Messages | Interactive builder for Components V2 container cards |
| `?embed show <name>` | Utility | Manage Messages | Preview saved container card |
| `?embed send <ch> <name>`| Utility | Manage Messages | Dispatch saved container card to channel |
| `?buy` | Premium | Everyone | Interactive 3-tab checkout console for Server Pro plans |
| `?premium` | Premium | Everyone | Dual-Status card (Server Plan + Personal VIP Status) |
| `?help` | General | Everyone | Interactive Components V2 Help Menu with dropdown navigation |
| `?invite` | General | Everyone | Official bot authorization links and support server |
| `?hack <user>` | Games | Everyone | Realistic cyber security breach alert card |
| `?lock [channel]` | Moderation | Manage Channels| Lock channel to prevent member messages |
| `?unlock [channel]` | Moderation | Manage Channels| Unlock channel to restore member chat |
| `?play <query>` | Music | Everyone | Stream lossless audio in voice channel |
| `?queue` | Music | Everyone | View upcoming server playlist in Components V2 card |
