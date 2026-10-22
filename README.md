# Kyro

A multi-purpose Discord bot built with Python (`discord.py`) and PostgreSQL. It includes music playback (YouTube and Spotify), voice meeting recording with AI transcription/summaries, moderation tools, ticket support, and anti-nuke protection. It also uses Discord's Components V2 layout (containers and dividers) rather than standard embeds.

[![Python](https://img.shields.io/badge/Python-3.10%20%7C%203.11+-3776AB?style=flat-square&logo=python&logoColor=white)](https://python.org)
[![discord.py](https://img.shields.io/badge/discord.py-2.4+-5865F2?style=flat-square&logo=discord&logoColor=white)](https://github.com/Rapptz/discord.py)
[![Database](https://img.shields.io/badge/Database-PostgreSQL%20%2F%20Supabase-3ECF8E?style=flat-square&logo=supabase&logoColor=white)](https://supabase.com)
[![License](https://img.shields.io/badge/License-MIT-blue.svg?style=flat-square)](LICENSE)

---

## Features

- **Music**: Plays tracks from YouTube and Spotify. Includes queue management, loop modes, volume control, shuffle, autoplay, and 24/7 stay mode.
- **Meeting Transcripts & AI Summaries**: Records voice channels, transcribes speakers using Groq Whisper, and generates clean meeting notes using Google Gemini.
- **Moderation & Purge**: Fast bulk message deletion (with filters for bots, humans, or all messages) and standard moderation commands (ban, kick, timeout, warn).
- **Anti-Nuke**: Real-time protection against unauthorized bot invites, mass bans, mass kicks, channel deletions, and role tampering.
- **Tickets**: Button-based ticket panels with modal forms, staff claiming, and automatic transcripts.
- **Reliability Watchdog**: Background monitor that recovers dropped voice connections, clears stale sessions, and prevents memory leaks.
- **Components V2 Interface**: Clean Discord container cards and section dividers instead of old-style embeds.

---

## Prerequisites

Before setting up, make sure you have:
1. **Python 3.10 or 3.11+** installed ([python.org](https://www.python.org/downloads/)).
   On Windows, check the box that says **"Add Python to PATH"** during setup.
2. **Git** installed ([git-scm.com](https://git-scm.com/downloads)).
3. **FFmpeg**: Bundled automatically via `static-ffmpeg`, but having system FFmpeg installed is recommended.
4. A **Discord Bot Token** from the [Discord Developer Portal](https://discord.com/developers/applications).
5. A **PostgreSQL Database** (Free instances from [Supabase](https://supabase.com) or [Neon.tech](https://neon.tech) work great).

---

## Setup Guide

### 1. Create Your Discord Bot

1. Open the [Discord Developer Portal](https://discord.com/developers/applications) and log in.
2. Click **New Application**, give your bot a name, and hit **Create**.
3. Go to the **Bot** tab on the left:
   - Click **Reset Token** and copy the token. Save it somewhere safe (you will need it for `.env`).
4. Scroll down to **Privileged Gateway Intents** and enable:
   - **Presence Intent**
   - **Server Members Intent**
   - **Message Content Intent** (Required for prefix commands to work)
   - Click **Save Changes**.
5. Go to **OAuth2** -> **URL Generator**:
   - Under **Scopes**, check: `bot` and `applications.commands`.
   - Under **Bot Permissions**, check: `Administrator` (or grant channel, role, message, and voice permissions manually).
   - Copy the link at the bottom and open it in your browser to invite the bot to your server.

---

### 2. Get a Free Database (Supabase)

Kyro uses PostgreSQL for persistent data. You can set one up in about 2 minutes on Supabase:

1. Sign up for free at [supabase.com](https://supabase.com) and click **New Project**.
2. Set a name and a strong database password, then pick a region close to you.
3. Once the project is ready, click **Connect** in the top bar (or go to **Project Settings** -> **Database**).
4. Under **Connection string**, select **URI**.
5. Switch to the **Transaction pooler** (port `6543`).
6. Copy the string. It looks like this:
   ```text
   postgresql://postgres.[PROJECT-REF]:[YOUR-PASSWORD]@aws-0-[REGION].pooler.supabase.com:6543/postgres
   ```
   Replace `[YOUR-PASSWORD]` with your actual database password.

---

### 3. Clone and Install

Open your terminal or command prompt:

```bash
# Clone the repository
git clone https://github.com/zerox-exe8/cicada-3301.git
cd cicada-3301

# Create and activate a virtual environment
# Windows:
python -m venv venv
venv\Scripts\activate

# Linux / macOS:
python3 -m venv venv
source venv/bin/activate

# Install requirements
pip install -r requirements.txt
```

---

### 4. Configure .env

Copy the example configuration file:

```bash
# Windows:
copy .env.example .env

# Linux / macOS:
cp .env.example .env
```

Open `.env` in any text editor and fill in your values:

```env
# Discord Bot Credentials
BOT_TOKEN=your_bot_token_here
CLIENT_ID=your_client_id_here
DEVELOPER_IDS=your_discord_user_id

# Database (Supabase / PostgreSQL)
DATABASE_URL=postgresql://postgres.xxx:password@aws-0-region.pooler.supabase.com:6543/postgres

# Bot Defaults
BOT_PREFIX=?
ENVIRONMENT=production
SYNC_COMMANDS_ON_STARTUP=true

# Optional: AI Meeting Summaries & Transcription
GEMINI_API_KEY=
GROQ_API_KEY=

# Optional: Spotify Integration
SPOTIFY_CLIENT_ID=
SPOTIFY_CLIENT_SECRET=
```

---

### 5. Start the Bot

Run the bot using:

```bash
python main.py
```

On startup, Kyro will:
- Connect to your PostgreSQL database and auto-create all necessary tables.
- Load cached settings and commands into memory.
- Connect to Discord and sync slash commands.

---

## Configuration Reference

| Variable | Required | Default | Description |
| :--- | :---: | :---: | :--- |
| `BOT_TOKEN` | Yes | - | Your bot token from Discord Developer Portal. |
| `DATABASE_URL` | Yes | - | PostgreSQL connection URI (Supabase, Neon, or local). |
| `CLIENT_ID` | No | `0` | Application ID used for generating invite links. |
| `DEVELOPER_IDS` | No | - | Comma-separated Discord User IDs with developer/bypass permissions. |
| `BOT_PREFIX` | No | `?` | Default text prefix. Servers can change this using `,prefix`. |
| `ENVIRONMENT` | No | `production` | Set to `development` or `production`. |
| `SYNC_COMMANDS_ON_STARTUP` | No | `true` | Automatically syncs slash (`/`) commands with Discord on launch. |
| `GEMINI_API_KEY` | No | - | Google Gemini API key for meeting summaries and issue analysis. |
| `GROQ_API_KEY` | No | - | Groq API key for speech-to-text meeting transcription (Whisper). |
| `SPOTIFY_CLIENT_ID` | No | - | Spotify Developer Client ID (for loading Spotify tracks/playlists). |
| `SPOTIFY_CLIENT_SECRET` | No | - | Spotify Developer Client Secret. |
| `LAVALINK_URI` | No | `http://lava2.kasawa.pro:2334` | Primary Lavalink node URI. |
| `LAVALINK_PASSWORD` | No | `youshallnotpass` | Lavalink node password. |
| `LAVALINK_AUTO_DISCOVER` | No | `true` | Auto-detects an active public Lavalink node if primary is down. |
| `PORT` | No | `8080` | Port for the internal HTTP health check server. |

---

## Music Setup & Lavalink

Kyro connects to Lavalink for audio processing.

- **Out of the box**: `LAVALINK_AUTO_DISCOVER=true` is enabled by default. If the default node goes down, the bot automatically finds and connects to an active community node so playback does not break.
- **Your Own Node**: If you prefer hosting your own Lavalink v4.2+ instance, set `LAVALINK_URI` and `LAVALINK_PASSWORD` in `.env`.
- **Spotify**: Add `SPOTIFY_CLIENT_ID` and `SPOTIFY_CLIENT_SECRET` in `.env` to enable playing Spotify track and playlist links.
- **Clearing Queue**: You can clear upcoming songs using `,clear`, `,cq`, or `,queue clear`.

---

## 24/7 Hosting

The bot includes an internal HTTP server on port `8080` (`/health`) so cloud hosts do not shut down the process.

### Hosting on Linux (VPS with systemd)

1. Create a service file:
   ```bash
   sudo nano /etc/systemd/system/kyro.service
   ```

2. Add this configuration (update username and path):
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

3. Enable and start:
   ```bash
   sudo systemctl daemon-reload
   sudo systemctl enable kyro
   sudo systemctl start kyro
   ```

4. Check logs:
   ```bash
   journalctl -u kyro -f
   ```

### Hosting on Render
1. Connect your repository to Render.
2. Select **Blueprint** and pick `render.yaml`.
3. Fill in your environment variables in the Render dashboard.

---

## Troubleshooting

### Bot does not respond to prefix commands (?, ,)
- Make sure **Message Content Intent** is turned on in the Discord Developer Portal under the Bot tab.
- Check that the bot has `Send Messages` and `View Channel` permissions in that channel.

### Database connection error or timeout
- If using Supabase, make sure you use the **Transaction pooler URI** on port `6543`, not the direct connection.
- Check that your database password does not contain unescaped special characters.

### Slash commands are not showing up
- Global slash commands can take Discord a few minutes to register on initial setup.
- Ensure `SYNC_COMMANDS_ON_STARTUP=true` is in your `.env`.

### FFmpeg not found
- Kyro installs `static-ffmpeg` automatically. If your OS still complains:
  - Windows: Run `winget install Gyan.FFmpeg`
  - Linux (Ubuntu/Debian): Run `sudo apt update && sudo apt install -y ffmpeg`

---

## Command Reference

Supports both prefix commands (default `?` or `,`) and slash commands (`/`).

### Music
| Command | Aliases | Description |
| :--- | :--- | :--- |
| `/play <query>` | `,p` | Play a song or playlist from YouTube/Spotify |
| `/pause` | `,pause` | Pause currently playing song |
| `/resume` | `,resume` | Resume playback |
| `/skip` | `,s` | Skip to the next track |
| `/stop` | `,stop` | Stop playback, clear queue, and leave voice |
| `/queue [page]` | `,q` | View current queue (or use `,queue clear` to empty) |
| `/clear` | `,clearqueue`, `,cq` | Clear upcoming songs from queue |
| `/nowplaying` | `,np`, `,now` | Show player card with playback controls |
| `/loop [mode]` | `,loop` | Set loop mode (`off`, `track`, or `queue`) |
| `/shuffle` | `,shuffle` | Shuffle upcoming queue |
| `/volume <0-200>` | `,vol` | Change playback volume |
| `/stay` | `,247` | Toggle 24/7 voice channel stay mode |
| `/jump <index>` | `,skipto` | Jump directly to a track in queue |

### Meeting & Voice Recording
| Command | Description |
| :--- | :--- |
| `/meeting start` | Joins voice channel and begins live recording/transcription |
| `/meeting stop` | Stops recording, compiles transcript, and generates AI summary |
| `/meeting status` | Shows recording duration, active speakers, and audio status |

### Moderation & Management
| Command | Description |
| :--- | :--- |
| `/purge <count>` | Bulk delete messages (aliases: `,clean`, `,prune`) |
| `/purge bot <count>` | Bulk delete only messages sent by bots |
| `/purge human <count>` | Bulk delete only messages sent by human users |
| `/ban <user> [reason]` | Ban a user from the server |
| `/kick <user> [reason]` | Kick a user from the server |
| `/timeout <user> <duration>` | Timeout a member |
| `/ticket setup` | Set up an interactive support ticket panel |
| `/antinuke enable` | Turn on automated server raid protection |
| `/prefix <new_prefix>` | Change the bot prefix for the server |

---

## Project Structure

```text
Kyro/
├── main.py                  # Root entrypoint (python main.py)
├── .env.example             # Configuration template
├── requirements.txt         # Python dependencies
├── render.yaml              # Render deployment blueprint
│
├── src/
│   ├── main.py              # Application lifecycle and watchdog runner
│   │
│   ├── core/                # Bot client, service registry, config
│   │   ├── bot.py           # KyroBot client
│   │   ├── services.py      # Dependency container and guild concurrency locks
│   │   ├── config.py        # Environment variables parser
│   │   └── server.py        # Keep-alive HTTP health server
│   │
│   ├── repositories/        # Database access layer (SQL)
│   │   ├── guild_repo.py    # Guild settings, prefixes, modules
│   │   ├── system_repo.py   # Developers, blacklists, bot state
│   │   ├── ticket_repo.py   # Support ticket panels and claims
│   │   └── meeting_repo.py  # Meeting recordings and notes
│   │
│   ├── sentinel/            # Voice watchdog and memory health monitor
│   │   └── agent.py         # Voice session recovery and health loops
│   │
│   ├── cogs/                # Feature modules
│   │   ├── music/           # Audio engine and queue controller
│   │   ├── meeting/         # Voice transcription and AI summary
│   │   ├── moderation/      # Moderation, purge, and media channels
│   │   ├── antinuke/        # Anti-raid and security rules
│   │   ├── ticket/          # Interactive support tickets
│   │   └── utility/         # Autoroles, giveaways, and temp voice
│   │
│   └── utils/               # Discord Components V2 container formatting
```

---

## License

This project is licensed under the MIT License.
