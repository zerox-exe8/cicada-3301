# Kyro

> Built for our community — keeping your server safe, active, and effortlessly connected.

[![Python](https://img.shields.io/badge/Python-3.11+-3776AB?style=flat-square&logo=python&logoColor=white)](https://python.org)
[![discord.py](https://img.shields.io/badge/discord.py-2.4+-5865F2?style=flat-square&logo=discord&logoColor=white)](https://github.com/Rapptz/discord.py)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-Supabase-3ECF8E?style=flat-square&logo=supabase&logoColor=white)](https://supabase.com)
[![Architecture](https://img.shields.io/badge/UI-Components%20V2-FF73FA?style=flat-square)](https://discord.com)
[![Deployment](https://img.shields.io/badge/Deployment-Cloud%20Service-46E3B7?style=flat-square)](https://render.com)

---

## Overview

Kyro is an enterprise-grade, high-concurrency Discord bot architecture engineered for performance, reliability, and modern user experiences. Built for our community — keeping your server safe, active, and effortlessly connected.

Unlike traditional bots constrained by legacy Discord embeds and sluggish database queries, Kyro combines an asynchronous in-memory caching engine with native Discord Components V2 (Type 17 Container Cards and Type 14 Separators), providing sub-millisecond execution and seamless interface navigation across Desktop, Web, and Mobile.

---

## Key Architectural Highlights

### 1. Discord Components V2 Design System
- Replaces dated legacy embeds with native Discord Type 17 Containers and Type 14 Dividers.
- Features clean, structured cards with custom application emojis resolved dynamically from the Discord Developer Portal.
- Standardizes interaction deferrals to eliminate loading delays and API errors.

### 2. Autonomous Sentinel SRE Agent
- Built-in site reliability engineering agent that runs continuous health checks on the bot process.
- Non-blocking watchdog loop that monitors PostgreSQL pools, Lavalink voice streaming nodes, and Discord Gateway ping.
- Automated self-healing with circuit breaker protection to recover dropped connections without taking the bot offline.

### 3. Studio Audio Engine
- Dedicated Lavalink streaming node powered by Wavelink.
- Concurrency-locked voice connections to prevent gateway race conditions and handshake timeouts.
- Dynamic queue management, track sanitization, and seamless 24/7 stay mode.
- Hardened Lavalink transport: every node call is bounded by a timeout and the
  node REST API is health-probed, so a single unresponsive node can never freeze
  the music commands.
- Automatic failover across `LAVALINK_FALLBACK_URIS` when the primary node is unreachable.

### 4. Lavalink Node Deployment
- The Lavalink node runs as its **own Render Background Worker** (`render.lavalink.yaml`),
  separate from the bot's Web Service.
- `lavalink-node/application.yml` ships the node configuration (Lavalink v4.2+, the
  YouTube plugin, and the password read from `LAVALINK_PASSWORD`).
- A Background Worker never spins down, so active audio streams are never cut
  mid-song and there is no Render cold start after an outage.

### 4. Sub-Millisecond In-Memory Caching
- Critical runtime states (prefixes, developer authorizations, maintenance status, global blacklists, and module configs) are cached in memory upon boot.
- Read operations execute in less than 0.001ms directly from RAM.
- Write operations atomically update both the PostgreSQL database pool and the local memory cache.

---

## System Architecture

```text
                       +-----------------------------------------+
                       |           Discord Gateway API           |
                       +--------------------+--------------------+
                                            |
                                  (Interaction / Message)
                                            v
                       +-----------------------------------------+
                       |         Kyro Async Core Client          |
                       +--------------+-------------------+------+
                                      |                   |
                     (0ms Memory Read)|                   |(Atomic Write)
                                      v                   v
                       +-------------------------+  +-------------------------+
                       |  In-Memory Fast Caches  |  |  Supabase PostgreSQL    |
                       |  - Guild Prefixes       |  |  - Connection Pool      |
                       |  - System Maintenance   |  |  - Persistent Schemas   |
                       |  - Global Blacklists    |  |  - Customer Analytics   |
                       |  - Module Settings      |  |  - Audit Logs           |
                       +-------------------------+  +-------------------------+
                                      |
                                      v
                       +-----------------------------------------+
                       |    Components V2 REST Dispatcher        |
                       |    (Type 17 Container Layout Cards)     |
                       +-----------------------------------------+
```

---

## Modules Directory

Kyro provides a modular suite of tools built for our community — keeping your server safe, active, and effortlessly connected.

| Module | Description | Core Capabilities |
| :--- | :--- | :--- |
| **Antinuke** | High-velocity server protection and threat mitigation | Anti-ban, anti-kick, anti-role, bot addition guard, whitelisting |
| **Moderation** | Comprehensive community enforcement tools | Ban, kick, mute, timeout, warn, lock, purge, role management |
| **Music** | Studio audio streaming engine with 24/7 mode | Dedicated Lavalink node, queue, loop, autoplay, jump, volume |
| **Giveaway** | Interactive giveaways with Components V2 countdowns | Fair winner selection, reroll, requirements, persistent views |
| **Media** | Strict channel media content enforcement | Media-only channels, auto-deletion of text, domain whitelist |
| **Welcomer** | Dynamic member join and leave greetings | Card generators, autoroles, channel routing, custom formats |
| **Join to Create** | Autonomous temporary voice room management | Dynamic creation, permission controls, auto-cleanup on empty |
| **Ticket** | Private support ticket channels and transcripts | Category routing, claim system, interactive buttons, logs |
| **Audit Logs** | Real-time event tracking and moderation logs | Message edits/deletions, member updates, role and channel changes |
| **Premium** | SaaS subscription and tier management | Guild and user premium tiers, key generation and redemption |

---

## Project Structure

```text
Kyro/
|-- .env.example          # Environment variables template
|-- render.yaml           # Deployment blueprint (Discord bot Web Service)
|-- render.lavalink.yaml  # Deployment blueprint (Lavalink Background Worker)
|-- build.sh              # Bot build script
|-- build-lavalink.sh     # Lavalink node build script
|-- requirements.txt      # Python dependencies
|-- README.md             # Project documentation
|-- AGENTS.md             # Architectural guidelines and standards
|
|-- lavalink-node/        # Lavalink node deployment assets
|   |-- application.yml   # Lavalink v4 node configuration
|   `-- Dockerfile        # Lavalink node container image
|
|-- assets/               # Assets and custom application emojis
|   |-- avatar/           # Bot avatar presets
|   |-- banner/           # Bot banner presets
|   |-- emoji/            # Custom application emojis
|   |-- emoji2/           # Additional emoji assets
|   `-- music/            # Music controller assets
|
`-- src/
    |-- main.py           # Application entrypoint
    |
    |-- core/             # Core engine, bot client, and cache
    |   |-- bot.py        # KyroBot client implementation
    |   |-- config.py     # Environment configuration validator
    |   |-- context.py    # CustomContext with container dispatcher
    |   `-- server.py     # HTTP keep-alive health server
    |
    |-- sentinel/         # Autonomous SRE Sentinel Agent
    |   |-- agent.py      # Background watchdog and self-healing engine
    |   `-- models.py     # Incident, severity, and subsystem types
    |
    |-- database/         # Database persistence layer
    |   |-- base.py       # Abstract database interface
    |   `-- postgres.py   # asyncpg Supabase PostgreSQL pool and schema
    |
    |-- managers/         # Domain managers and memory caches
    |   |-- antinuke_manager.py
    |   |-- guild_manager.py
    |   |-- giveaway_manager.py
    |   |-- media_manager.py
    |   |-- log_manager.py
    |   `-- premium_manager.py
    |
    |-- utils/            # Design system and helpers
    |   |-- containers.py # Discord Components V2 container builder
    |   |-- emojis.py     # Application emoji registry
    |   `-- views.py      # Base interaction view utilities
    |
    `-- cogs/             # Modular feature packages
        |-- antinuke/     # Security and anti-abuse systems
        |-- developer/    # Developer diagnostic and sentinel consoles
        |-- general/      # Help console and utility commands
        |-- moderation/   # Moderation tools and media channels
        |-- music/        # Lavalink audio engine and player controls
        |-- ticket/       # Interactive ticket support system
        `-- utility/      # Giveaways, autoroles, and temp voice
```

---

## Getting Started

### 1. Prerequisites
- Python **3.11** or higher
- A PostgreSQL database instance (such as Supabase)
- A Discord Bot Application configured with Message Content, Server Members, and Presence Intents enabled in the [Discord Developer Portal](https://discord.com/developers/applications)

### 2. Installation
```bash
# Clone the repository
git clone https://github.com/zerox-exe8/cicada-3301.git
cd Kyro

# Create and activate a virtual environment
python -m venv venv

# Windows:
venv\Scripts\activate

# Linux / macOS:
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### 3. Environment Setup
Create a `.env` file based on `.env.example`:
```env
BOT_TOKEN=your_bot_token_here
DATABASE_URL=postgresql://user:password@host:port/database
DEVELOPER_IDS=your_discord_user_id
DEFAULT_PREFIX=?
ENVIRONMENT=PRODUCTION
PORT=8080
```

### 4. Running
```bash
python -m src.main
```

---

## 24/7 Cloud Deployment

Kyro includes a lightweight, non-blocking HTTP health check server running on port `8080` (endpoint: `/health`), enabling zero-downtime hosting on cloud providers such as Render, Railway, or VPS instances.

To deploy on Render:
1. Connect your repository to Render.
2. Select Web Service and apply `render.yaml`.
3. Configure the required environment variables in the Render dashboard.

### Lavalink Audio Node

The bot needs a Lavalink v4 node (4.2+ is mandatory: since March 2026 Discord
only accepts end-to-end encrypted voice, and Lavalink 4.2.0 was the first release
supporting it).

Deploy it as a **Background Worker** from the same repository:
1. Render dashboard → **New → Blueprint**.
2. Select this repository and pick `render.lavalink.yaml`.
3. Set the **same** `LAVALINK_PASSWORD` value here and on the bot service.
4. Point the bot at the node: `LAVALINK_URI=https://kyro-lavalink.onrender.com`.

The node's own `LAVALINK_SERVER_PORT` (default `2333`) is the port the bot
connects to. `LAVALINK_FALLBACK_URIS` accepts a comma separated list of extra
node URIs the bot fails over to when the primary is unreachable.

> A Background Worker is used on purpose: Render's *free web services* spin down
> after 15 minutes of inactivity, which kills every playing guild and makes the
> bot believe the node is dead.

---

## Credits

- **Application**: Kyro
- **Description**: Built for our community — keeping your server safe, active, and effortlessly connected.
- **Lead Architect**: `zerox.exe`
- **Framework**: `discord.py` (Components V2)
- **Database**: PostgreSQL with `asyncpg`
