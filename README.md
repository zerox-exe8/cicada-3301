# ⚡ Cicada 3301 — Next-Generation Discord Infrastructure

<div align="center">
  <img src="./assets/Cicada 3301%20banner.jpeg" alt="Cicada 3301 Banner" width="100%" style="border-radius: 10px; margin-bottom: 20px;" />

  <h3>Enterprise Discord Management & Community Infrastructure</h3>
  <p>Engineered with Python 3.11+, Discord Components V2 Containers, 0ms In-Memory Caching, and Supabase PostgreSQL.</p>

  <p>
    <img src="https://img.shields.io/badge/Python-3.11+-3776AB?style=for-the-badge&logo=python&logoColor=white" />
    <img src="https://img.shields.io/badge/discord.py-2.4+-5865F2?style=for-the-badge&logo=discord&logoColor=white" />
    <img src="https://img.shields.io/badge/PostgreSQL-Supabase-3ECF8E?style=for-the-badge&logo=supabase&logoColor=white" />
    <img src="https://img.shields.io/badge/Deployment-Render%20Cloud-46E3B7?style=for-the-badge&logo=render&logoColor=white" />
    <img src="https://img.shields.io/badge/UI-Components%20V2%20(Type%2017)-FF73FA?style=for-the-badge" />
  </p>
</div>

---

## 📖 Overview

**Cicada 3301** is an enterprise-grade, high-concurrency Discord bot architecture engineered for performance, reliability, and clean aesthetics. 

Unlike traditional bots constrained by legacy Discord embeds and sluggish database queries, Cicada 3301 operates with a **0ms In-Memory Caching Architecture** coupled with **Discord Components V2 (Type 17 Containers)**, delivering sub-millisecond execution speeds and clean, modern UI cards across Desktop, Web, and Mobile.

---

## 🏛️ System Architecture

```text
                       ┌─────────────────────────────────────────┐
                       │           Discord Gateway API           │
                       └────────────────────┬────────────────────┘
                                            │
                                  (Interaction/Message)
                                            ▼
                       ┌─────────────────────────────────────────┐
                       │         Cicada 3301 Async Core Client         │
                       └──────────────┬───────────────────┬──────┘
                                      │                   │
                     (0ms Memory Read)│                   │(Atomic Write)
                                      ▼                   ▼
                       ┌─────────────────────────┐  ┌─────────────────────────┐
                       │  In-Memory Fast Caches  │  │  Supabase PostgreSQL    │
                       │  • Guild Prefixes       │  │  • Connection Pool      │
                       │  • Active Subscriptions │  │  • Persistent Schemas   │
                       │  • System Maintenance   │  │  • Customer Analytics   │
                       │  • Global Blacklists    │  │  • Audit Logs           │
                       └─────────────────────────┘  └─────────────────────────┘
                                      │
                                      ▼
                       ┌─────────────────────────────────────────┐
                       │    Components V2 REST Dispatcher        │
                       │    (Type 17 Container Layout Cards)     │
                       └─────────────────────────────────────────┘
```

### ⚡ 1. Hybrid 0ms In-Memory Caching
- Critical configurations (Guild Prefixes, Developer IDs, Maintenance State, Blacklists, and Subscriptions) are preloaded into memory upon startup.
- Message processing reads from RAM cache directly (`<0.001ms`), bypassing database round-trips entirely.
- Write operations atomically update both the PostgreSQL database pool and the in-memory cache.

### 🎨 2. Native Discord Components V2 Containers (Type 17)
- Replaces outdated, noisy Discord Embeds with native **Components V2 Containers**.
- Structured Text Displays, Section Rows, dynamic Separators, and integrated Action Rows.
- Zero standard unicode emoji spam — dynamically uses custom **Application Emojis** cached directly from the Discord Developer Portal.

### 🌐 3. 24/7 Cloud Resilience (Render Web Service)
- Integrated `aiohttp` HTTP health server running on port `8080`.
- Provides an active `/health` endpoint for continuous zero-downtime monitoring on Render.com, Railway, or VPS.

---

## 📂 Project Structure

```text
Cicada 3301/
├── .env                  # Secrets, Bot Token & Supabase Database URL
├── .env.example          # Environment configuration template
├── render.yaml           # 1-Click Render Cloud Deployment Blueprint
├── requirements.txt      # Python dependencies
├── README.md             # Bot overview & documentation
├── PROJECT_CONTEXT.md    # Exhaustive Technical Specification for AI & Developers
│
├── assets/               # Branding assets & custom application emojis
│   ├── Cicada 3301 banner.jpeg
│   ├── Cicada 3301 logo.jpeg
│   └── emoji2/
│
└── src/
    ├── main.py           # Application bootstrap & lifecycle manager
    │
    ├── core/             # Core Engine & HTTP Server
    │   ├── bot.py        # CicadaBot custom client with setup hooks
    │   ├── config.py     # Environment variable validator & constants
    │   ├── context.py    # CustomContext with container dispatcher methods
    │   └── server.py     # 24/7 aiohttp Keep-Alive Health Server
    │
    ├── database/         # Database Persistence Layer
    │   ├── base.py       # Abstract database protocol
    │   └── postgres.py   # asyncpg Supabase PostgreSQL pool & table schemas
    │
    ├── managers/         # Domain Logic & In-Memory Cache Engines
    │   ├── blacklist_manager.py   # Global user and guild blacklist filter
    │   ├── guild_manager.py       # Custom per-guild prefix caching
    │   ├── log_manager.py         # Multi-channel audit logging settings
    │   ├── permission_manager.py  # Bot owner & developer access control
    │   ├── premium_manager.py     # Subscriptions, keys, and customer analytics
    │   └── system_manager.py      # Global maintenance mode & command toggles
    │
    ├── utils/            # Shared Utilities & Design System
    │   ├── containers.py # Discord Components V2 builder & REST dispatcher
    │   ├── decorators.py # @require_guild_premium() and @require_user_premium()
    │   ├── emojis.py     # Dynamic Custom Application Emoji registry
    │   ├── embeds.py     # Fallback legacy embed utilities
    │   ├── logger.py     # Colored console logger
    │   └── views.py      # Base interaction view utilities
    │
    ├── errors/           # Centralized Error Handling
    │   ├── exceptions.py # Domain custom exceptions
    │   └── handler.py    # Global on_command_error listener & error UI cards
    │
    └── cogs/             # Modular Feature Packages (Ready for custom expansion)
```

---

## 🚀 Getting Started & Local Setup

### 1. Prerequisites
- Python **3.11** or higher
- A Supabase / PostgreSQL database instance
- A Discord Bot Application from [Discord Developer Portal](https://discord.com/developers/applications)

### 2. Installation
```bash
# Clone the repository
git clone <repository_url>
cd Cicada 3301

# Create and activate virtual environment
python -m venv venv
# On Windows:
venv\Scripts\activate
# On Linux/macOS:
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### 3. Environment Variables
Create `.env` based on `.env.example`:
```env
BOT_TOKEN=your_discord_bot_token_here
DATABASE_URL=postgresql://postgres.xxxx:password@aws-0-region.pooler.supabase.com:6543/postgres
DEVELOPER_IDS=1082437832087445604
DEFAULT_PREFIX=?
ENVIRONMENT=DEVELOPMENT
PORT=8080
```

### 4. Run the Bot
```bash
python -m src.main
```

---

## ☁️ 24/7 Cloud Deployment (Render.com)

1. Link your GitHub repository to [Render.com](https://render.com).
2. Create a **Web Service** using `render.yaml`.
3. Set Build Command: `pip install -r requirements.txt`.
4. Set Start Command: `python -m src.main`.
5. Add Environment Variables (`BOT_TOKEN`, `DATABASE_URL`, `DEVELOPER_IDS`, etc.).

Render will automatically deploy Cicada 3301 alongside its integrated Keep-Alive Web Server (`http://0.0.0.0:8080`) for continuous 24/7 operation.

---

## 🛡️ Credits & Lead Architect

- **Bot Name**: Cicada 3301
- **Lead Architect & Developer**: `zerox.exe`
- **Framework**: `discord.py` (Components V2 Extended)
- **Database**: `Supabase PostgreSQL` with `asyncpg`

---
<div align="center">
  <sub>Engineered for next-generation Discord communities.</sub>
</div>
