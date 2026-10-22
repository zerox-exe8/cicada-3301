# ⚡ Kyro — Next-Gen Enterprise Discord Bot

> **An enterprise-grade, high-concurrency Discord bot architecture featuring Studio Audio Streaming, AI Meeting Transcription, Autonomous Sentinel SRE Self-Healing, Antinuke Security, and Discord Components V2 UI.**

[![Python](https://img.shields.io/badge/Python-3.10%20%7C%203.11+-3776AB?style=flat-square&logo=python&logoColor=white)](https://python.org)
[![discord.py](https://img.shields.io/badge/discord.py-2.4+-5865F2?style=flat-square&logo=discord&logoColor=white)](https://github.com/Rapptz/discord.py)
[![PostgreSQL](https://img.shields.io/badge/Database-PostgreSQL%20%2F%20Supabase-3ECF8E?style=flat-square&logo=supabase&logoColor=white)](https://supabase.com)
[![UI](https://img.shields.io/badge/UI-Discord%20Components%20V2-FF73FA?style=flat-square)](https://discord.com)
[![License](https://img.shields.io/badge/License-MIT-blue.svg?style=flat-square)](LICENSE)

---

## 📖 Table of Contents
1. [Key Features](#-key-features)
2. [Prerequisites](#-prerequisites)
3. [Quick 5-Minute Setup Guide](#-quick-5-minute-setup-guide)
   - [Step 1: Discord Developer Portal & Bot Token](#step-1-discord-developer-portal--bot-token)
   - [Step 2: Free PostgreSQL Cloud Database](#step-2-free-postgresql-cloud-database)
   - [Step 3: Clone and Setup Repository](#step-3-clone-and-setup-repository)
   - [Step 4: Install Dependencies](#step-4-install-dependencies)
   - [Step 5: Configure Environment Variables (.env)](#step-5-configure-environment-variables-env)
   - [Step 6: Run the Bot](#step-6-run-the-bot)
4. [Environment Configuration Cheatsheet](#-environment-configuration-cheatsheet)
5. [Music & Audio Configuration](#-music--audio-configuration)
6. [24/7 Cloud Deployment Guide](#-247-cloud-deployment-guide)
7. [Troubleshooting & Common Errors (FAQ)](#-troubleshooting--common-errors-faq)
8. [Available Modules & Commands](#-available-modules--commands)
9. [Project Architecture](#-project-architecture)

---

## ✨ Key Features

- 🎵 **Studio Audio Engine**: High-fidelity YouTube and Spotify audio streaming with smart queueing, loop modes, volume controls, shuffle, autoplay, and 24/7 stay mode.
- 🎙️ **Live Voice Recording & AI Meeting Transcriber**: Multi-speaker voice channel transcription using Groq Whisper and automated meeting summarization via Google Gemini AI.
- 🛡️ **Antinuke & Anti-Raid Security**: Real-time defense against malicious bot additions, mass-bans, mass-kicks, channel deletions, and unauthorized role changes with an automated whitelist engine.
- ⚖️ **Advanced Moderation & Purging**: Powerful moderation suite (ban, kick, timeout, warn) and intelligent bulk message purge (all, bot-only, or human-only) with auto-clearing confirmation cards.
- 🎫 **Support Tickets & Claims**: Multi-category ticket system with interactive buttons, modal forms, staff claiming, and automatic HTML/text transcripts.
- 🤖 **Autonomous Sentinel SRE Agent**: Built-in site reliability engineering agent that runs continuous health checks, recovers zombie voice connections, and prevents memory leaks without taking the bot offline.
- 💎 **Discord Components V2 Design System**: Clean, modern UI cards using Discord native Type 17 Containers and Type 14 Dividers. No dated, clunky embeds.
- ⚡ **Asynchronous Repository Pattern**: Decoupled database queries using `asyncpg` connection pooling and sub-millisecond in-memory caching.

---

## 📋 Prerequisites

Before installing, ensure you have:
1. **Python 3.10, 3.11, or newer** installed ([Download Python](https://www.python.org/downloads/)).
   > *Make sure to check "Add Python to PATH" during installation on Windows.*
2. **Git** installed ([Download Git](https://git-scm.com/downloads)).
3. **FFmpeg** (installed automatically via `static-ffmpeg` package, or system-wide via package manager).
4. A **Discord Bot Application** from the [Discord Developer Portal](https://discord.com/developers/applications).
5. A **PostgreSQL Database** (Free instance on [Supabase](https://supabase.com) or [Neon.tech](https://neon.tech)).

---

## 🚀 Quick 5-Minute Setup Guide

### Step 1: Discord Developer Portal & Bot Token

1. Go to the [Discord Developer Portal](https://discord.com/developers/applications) and sign in.
2. Click **"New Application"**, enter a name (e.g. `MyKyroBot`), and click **Create**.
3. Go to the **"Bot"** tab on the left sidebar:
   - Click **"Reset Token"** (or **"Add Bot"** if first time) and copy your **Bot Token**. *(Keep this private!)*
4. Scroll down to **"Privileged Gateway Intents"** and **TURN ON ALL THREE**:
   - ✅ **Presence Intent**
   - ✅ **Server Members Intent**
   - ✅ **Message Content Intent** *(CRITICAL: The bot cannot read prefix commands without this)*
   - Click **"Save Changes"**.
5. Go to **OAuth2** → **URL Generator**:
   - Under **Scopes**, select: `bot` and `applications.commands`.
   - Under **Bot Permissions**, select: `Administrator` (or select `Manage Roles`, `Manage Channels`, `Kick Members`, `Ban Members`, `Send Messages`, `Embed Links`, `Attach Files`, `Connect`, `Speak`).
   - Copy the generated URL at the bottom, paste it into your browser, and invite the bot to your server.

---

### Step 2: Free PostgreSQL Cloud Database

Kyro uses PostgreSQL for lightning-fast persistence. You can create a free database in 2 minutes:

#### Option A: Supabase (Recommended)
1. Sign up for free at [supabase.com](https://supabase.com).
2. Click **"New Project"**, select a name, database password, and your nearest region.
3. Once created, click the **Connect** button at the top header (or go to **Project Settings** → **Database**).
4. Under **Connection string**, select the **URI** tab.
5. Choose **"Transaction"** pooler (port `6543`) or **"Session"** (port `5432`).
6. Copy the connection string:
   ```text
   postgresql://postgres.[YOUR-PROJECT-REF]:[YOUR-PASSWORD]@aws-0-[REGION].pooler.supabase.com:6543/postgres
   ```
   *(Replace `[YOUR-PASSWORD]` with the database password you chose).*

#### Option B: Neon.tech
1. Sign up at [neon.tech](https://neon.tech) and create a project.
2. Copy the provided connection URI string.

---

### Step 3: Clone and Setup Repository

Open your terminal (PowerShell, Command Prompt, or Linux/macOS Terminal):

```bash
# 1. Clone the repository
git clone https://github.com/zerox-exe8/cicada-3301.git
cd cicada-3301

# 2. Create a virtual environment
# Windows:
python -m venv venv
venv\Scripts\activate

# Linux / macOS:
python3 -m venv venv
source venv/bin/activate
```

---

### Step 4: Install Dependencies

With your virtual environment activated, install all required packages:

```bash
pip install -r requirements.txt
```

> **Note**: Kyro bundles the necessary `opus.dll` and `libopus.so` binaries along with `static-ffmpeg`, so audio streaming will work out-of-the-box without manual audio driver compiling.

---

### Step 5: Configure Environment Variables (`.env`)

1. Copy the example template to create your `.env` file:
   ```bash
   # Windows (PowerShell):
   copy .env.example .env

   # Linux / macOS:
   cp .env.example .env
   ```

2. Open the `.env` file in your favorite text editor (VS Code, Notepad, Nano) and update the values:

```env
# Discord Credentials
BOT_TOKEN=YOUR_DISCORD_BOT_TOKEN_HERE
CLIENT_ID=YOUR_APPLICATION_CLIENT_ID_HERE
DEVELOPER_IDS=YOUR_DISCORD_USER_ID_HERE

# PostgreSQL Database (from Step 2)
DATABASE_URL=postgresql://postgres.xxx:password@aws-0-region.pooler.supabase.com:6543/postgres

# Bot Defaults
BOT_PREFIX=?
ENVIRONMENT=production
PORT=8080
SYNC_COMMANDS_ON_STARTUP=true

# Optional: Google Gemini API (For AI Meeting Summaries & Sentinel RCA)
# Free Key: https://aistudio.google.com/app/apikey
GEMINI_API_KEY=

# Optional: Groq Whisper API (For Ultra-Fast Meeting Voice Transcription)
# Free Key: https://console.groq.com/keys
GROQ_API_KEY=
```

---

### Step 6: Run the Bot

Launch the bot using Python:

```bash
python main.py
# or
python -m src.main
```

You should see logs indicating:
- ✅ Database connected successfully & tables migrated.
- ✅ ServiceRegistry & Repository caches loaded.
- ✅ Sentinel SRE Watchdog active.
- ✅ Discord Gateway login successful: `Logged in as Kyro#1234`.

---

## ⚙️ Environment Configuration Cheatsheet

| Variable | Required? | Default | Description |
| :--- | :---: | :---: | :--- |
| `BOT_TOKEN` | **Yes** | — | Your Discord Bot Token from Discord Developer Portal. |
| `DATABASE_URL` | **Yes** | — | PostgreSQL connection URI (e.g. Supabase, Neon, or local PostgreSQL). |
| `CLIENT_ID` | Optional | `0` | Your Discord Application ID (used for OAuth invite links). |
| `DEVELOPER_IDS` | Recommended | — | Comma-separated Discord User IDs who have developer bypass & admin rights. |
| `BOT_PREFIX` | Optional | `?` | Default command prefix (can also be customized per server via `,prefix`). |
| `ENVIRONMENT` | Optional | `production` | Set to `development` or `production`. |
| `SYNC_COMMANDS_ON_STARTUP` | Optional | `true` | Automatically synchronizes slash (`/`) commands with Discord upon startup. |
| `GEMINI_API_KEY` | Optional | — | Google Gemini API key for automated AI meeting notes and Sentinel diagnostic analysis. |
| `GROQ_API_KEY` | Optional | — | Groq Cloud API key for lightning-fast voice transcription (Whisper). |
| `SPOTIFY_CLIENT_ID` | Optional | — | Spotify Developer Client ID for Spotify playlist/track playback. |
| `SPOTIFY_CLIENT_SECRET` | Optional | — | Spotify Developer Client Secret. |
| `LAVALINK_URI` | Optional | `http://lava2.kasawa.pro:2334` | Primary Lavalink v4.2+ audio node URI. |
| `LAVALINK_PASSWORD` | Optional | `youshallnotpass` | Lavalink node authentication password. |
| `LAVALINK_AUTO_DISCOVER` | Optional | `true` | Automatically discovers a working public Lavalink node if primary goes down. |
| `PORT` | Optional | `8080` | Local port for the internal HTTP health keep-alive server. |

---

## 🎵 Music & Audio Configuration

Kyro comes equipped with an ultra-resilient audio architecture:
- **YouTube & Spotify**: Play tracks directly using queries, YouTube URLs, or Spotify tracks/playlists/albums.
- **Failover & Auto-Discovery**: If your configured Lavalink node ever goes down, Kyro automatically searches a verified directory of healthy public Lavalink nodes and switches over seamlessly.
- **Queue Clearing**: Use `,clear`, `,cq`, `,clearqueue`, or `,queue clear` to empty upcoming tracks without interrupting the currently playing song.
- **24/7 Voice Channel**: Use `,stay` to keep the bot connected in your voice channel 24/7.

---

## 🌐 24/7 Cloud Deployment Guide

Kyro includes a built-in lightweight HTTP health server (`http://0.0.0.0:8080/health`), making it 100% compatible with modern free & paid cloud hosting platforms.

### Deploying on Render
1. Fork or push this repository to your GitHub account.
2. Sign in to [Render.com](https://render.com).
3. Click **New** → **Blueprint** and select your repository.
4. Render will detect `render.yaml` automatically and configure the bot service.
5. Add your `.env` variables in the Render Environment Dashboard.

### Deploying on a Linux VPS (Ubuntu / Debian)
To run the bot 24/7 in the background on your VPS using `systemd`:

1. Create a service file:
   ```bash
   sudo nano /etc/systemd/system/kyro.service
   ```
2. Paste the following configuration (adjust paths to your user):
   ```ini
   [Unit]
   Description=Kyro Discord Bot
   After=network.target

   [Service]
   Type=simple
   User=ubuntu
   WorkingDirectory=/home/ubuntu/cicada-3301
   ExecStart=/home/ubuntu/cicada-3301/venv/bin/python main.py
   Restart=always
   RestartSec=10

   [Install]
   WantedBy=multi-user.target
   ```
3. Enable and start the service:
   ```bash
   sudo systemctl daemon-reload
   sudo systemctl enable kyro
   sudo systemctl start kyro
   ```
4. View live logs:
   ```bash
   journalctl -u kyro -f
   ```

---

## 🛠️ Troubleshooting & Common Errors (FAQ)

### 1. `discord.errors.PrivilegedIntentsRequired`
- **Cause**: One or more Privileged Gateway Intents are disabled in your Discord Developer Portal.
- **Fix**: Open [Discord Developer Portal](https://discord.com/developers/applications) → select your application → **Bot** tab → enable **Message Content Intent**, **Server Members Intent**, and **Presence Intent** → Save Changes.

### 2. Bot connects but doesn't respond to prefix commands (e.g. `?help` or `,play`)
- **Fix**: Ensure `Message Content Intent` is enabled in Developer Portal. Also make sure the bot has `Send Messages` and `Embed Links` permissions in the channel.

### 3. `asyncpg.exceptions.InvalidPasswordError` or connection timeout
- **Cause**: Incorrect `DATABASE_URL` credentials or network firewall blocking port 5432/6543.
- **Fix**: In Supabase, verify your database password and ensure you use the **Transaction Pooler** connection string (port `6543`), which supports IPv4 networks reliably.

### 4. Slash (`/`) commands not appearing in Discord
- **Cause**: Discord can take up to an hour to register global slash commands for new bots, or commands were not synced.
- **Fix**: Set `SYNC_COMMANDS_ON_STARTUP=true` in your `.env` file, restart the bot, and allow a few minutes for Discord to propagate application commands.

### 5. `FFmpeg was not found` or audio fails to play
- **Fix**: Kyro bundles `static-ffmpeg` in `requirements.txt`. If your operating system still cannot find FFmpeg:
  - **Windows**: Run `winget install Gyan.FFmpeg` in PowerShell.
  - **Linux (Ubuntu/Debian)**: Run `sudo apt update && sudo apt install -y ffmpeg`.

---

## 🎮 Available Modules & Commands

Kyro supports both **Prefix Commands** (default `?` or `,`) and **Slash Commands** (`/`):

### 🎵 Music Commands
| Command | Aliases | Description |
| :--- | :--- | :--- |
| `/play <query>` | `,p` | Play a song or playlist from YouTube/Spotify |
| `/pause` | `,pause` | Pause current track playback |
| `/resume` | `,resume` | Resume playback |
| `/skip` | `,s` | Skip to the next track in queue |
| `/stop` | `,stop` | Stop playback, clear queue, and leave voice channel |
| `/queue [page]` | `,q` | Display upcoming song queue (use `,queue clear` to empty) |
| `/clear` | `,clearqueue`, `,cq` | Clear all upcoming songs from queue |
| `/nowplaying` | `,np`, `,now` | Display detailed player card with interactive buttons |
| `/loop [mode]` | `,loop` | Toggle repeat mode: `off`, `track`, or `queue` |
| `/shuffle` | `,shuffle` | Randomize the upcoming song queue |
| `/volume <0-200>`| `,vol` | Adjust music playback volume |
| `/stay` | `,247` | Toggle 24/7 stay mode in voice channel |
| `/jump <index>` | `,skipto` | Jump directly to a specific track in queue |

### 🎙️ Meeting & AI Voice Commands
| Command | Description |
| :--- | :--- |
| `/meeting start` | Join voice channel and start live multi-speaker transcription |
| `/meeting stop` | End meeting recording, compile transcript, and generate AI summary |
| `/meeting status` | Check active recording duration, audio packets, and active speakers |

### 🛡️ Moderation & Utility Commands
| Command | Description |
| :--- | :--- |
| `/purge <count>` | Bulk delete messages in channel (aliases: `,clean`, `,prune`) |
| `/purge bot <count>` | Bulk delete only messages sent by bots |
| `/purge human <count>` | Bulk delete only messages sent by real users |
| `/ban <member> [reason]` | Ban a user from the server |
| `/kick <member> [reason]` | Kick a user from the server |
| `/timeout <member> <duration>` | Timeout a user for a specified duration |
| `/ticket setup` | Deploy an interactive support ticket creation panel |
| `/antinuke enable` | Turn on automated high-speed anti-raid protection |
| `/prefix <new_prefix>` | Customize bot prefix for your server |

---

## 🏗️ Project Architecture

```text
Kyro/
├── main.py                  # Root launcher entrypoint (python main.py)
├── .env.example             # Comprehensive environment configuration template
├── requirements.txt         # Production dependencies
├── render.yaml              # 24/7 Web service blueprint
│
├── src/
│   ├── main.py              # Application lifecycle, signal handlers & watchdog
│   │
│   ├── core/                # Core engine & services
│   │   ├── bot.py           # KyroBot client (ServiceRegistry integrated)
│   │   ├── services.py      # Dependency injection & domain concurrency locks
│   │   ├── config.py        # Environment variables validator
│   │   └── server.py        # HTTP health check keep-alive server
│   │
│   ├── repositories/        # Asynchronous SQL Data Access Layer
│   │   ├── base.py          # Abstract enterprise BaseRepository
│   │   ├── guild_repo.py    # Guild settings, prefixes & module toggles
│   │   ├── system_repo.py   # Developers, blacklists & system state
│   │   ├── ticket_repo.py   # Support ticket panels & transcripts
│   │   └── meeting_repo.py  # AI meeting sessions & transcripts
│   │
│   ├── sentinel/            # Autonomous SRE Sentinel Engine
│   │   ├── agent.py         # Voice session healer, RAM watcher & pool monitor
│   │   └── models.py        # Incident severity types
│   │
│   ├── cogs/                # Modular Discord Feature Packages
│   │   ├── music/           # Studio audio engine & queue controller
│   │   ├── meeting/         # Voice recording & Gemini AI summaries
│   │   ├── moderation/      # Moderation, purge & media channels
│   │   ├── antinuke/        # Anti-raid & server security
│   │   ├── ticket/          # Support panels & button interactions
│   │   └── utility/         # Autoroles, giveaways & temp voice
│   │
│   └── utils/               # Design system & visual containers
│       └── containers.py    # Discord Components V2 Container Cards
```

---

## 📄 License & Credits

- **Author**: `zerox.exe`
- **Application**: Kyro
- **Framework**: `discord.py` (Components V2)
- **License**: MIT License

---

<p align="center">
  <b>Built with ❤️ for Discord Communities. Keep your server safe, active, and effortlessly connected.</b>
</p>
