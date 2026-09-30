# VASUDEV AI ARENA x DISCORD BOT ECOSYSTEM
### Enterprise Full-Stack Integration & Architecture Specification
> **Prepared for:** Senior Development Team & Technical Leads  
> **Platform Target:** Vasudev AI Arena (arena.vasudevai.in) & Kyro Discord Engine  
> **Document Version:** 1.0.0-PROD | **Classification:** Technical Architecture Specification

---

## TABLE OF CONTENTS
1. [Executive Summary](#1-executive-summary)
2. [Design System & Visual Language](#2-design-system--visual-language)
3. [Ecosystem Architecture & Data Flow](#3-ecosystem-architecture--data-flow)
4. [Full Feature Matrix](#4-full-feature-matrix)
5. [Database & Document Schema Specifications](#5-database--document-schema-specifications)
6. [API & Real-time Integration Protocols](#6-api--real-time-integration-protocols)
7. [Discord Interface & Components V2 Design](#7-discord-interface--components-v2-design)
8. [Role & Level Synchronisation Engine](#8-role--level-synchronisation-engine)
9. [Security, Auth & Anti-Abuse Standards](#9-security-auth--anti-abuse-standards)
10. [Milestones & Implementation Checklist](#10-milestones--implementation-checklist)

---

## 1. EXECUTIVE SUMMARY

Vasudev AI Arena (arena.vasudevai.in) is India's gamified builder community platform where developers and student coders complete practical quests, contribute to real open-source bounties, accumulate verifiable XP, and compete on seasonal leaderboards.

This architectural document defines the end-to-end, bi-directional integration between the Arena web application layer (Next.js App Router, Tailwind CSS, Firebase Authentication, and Cloud Firestore) and the server Discord bot engine (Kyro).

The primary objective is to transform Discord into a native client for the Arena platform. This ensures:
- Instant synchronization of builder XP and level advancement.
- Real-time notification of new open-source bounties and seasonal quests.
- Automated Discord server role progression matching in-game ranks.
- Seamless account verification between Google OAuth credentials and Discord user profiles.

---

## 2. DESIGN SYSTEM & VISUAL LANGUAGE

Both the Arena web platform and the Discord user interface strictly follow a Neo-Brutalist Playful Minimalist standard characterized by high-contrast contrast borders, structured box layouts, monospace data labels, and defined color accents.

### Brand Palette Tokens

| Token Name | Hex Code | Purpose & Semantic Application |
| :--- | :--- | :--- |
| **Arena Yellow** | `#FFE45C` | Primary brand accent, level highlights, call-to-action buttons |
| **Dark Ink** | `#111111` | Primary text, 1.8px borders, card contours, hard offset shadows |
| **Arena Canvas** | `#F8F8F5` | Background canvas, base containers, primary card surfaces |
| **Soft Lilac** | `#C9B8FF` | Quests, documentation bounties, achievement indicators |
| **Mint Emerald** | `#BFEEDB` | XP drops, success validations, live status indicators |
| **Warm Peach** | `#FFC19D` | Streaks, active community events, challenge badges |
| **Sky Blue** | `#BFD7FF` | Explorer tier, onboarding milestones, developer guides |
| **Discord Blurple**| `#5865F2` | External community bindings, OAuth status cards |

### Structural Styling Standards
- **Border Treatment:** Consistent 1.8px solid `#111111` line weights on all containers, embeds, and badges.
- **Elevation and Shadows:** Hard offset box-shadows (3px 3px 0px `#111111`) without Gaussian blur.
- **Typography Standards:** Manrope for headers and section titles (weights 700 to 900); Geist Mono or system monospace for numerical metrics, XP scores, and status tags.

---

## 3. ECOSYSTEM ARCHITECTURE & DATA FLOW

The platform architecture operates across three distinct operational layers:

```
[ Vasudev AI Arena Web App ]
  - Next.js App Router & Server Actions
  - Firebase Authentication (Google OAuth)
  - Cloud Firestore Database
  - Next.js API Routes (/api/*)
              │
              ▼  (Bi-Directional Event Bridge)
[ Communication & Integration Bridge ]
  - Firebase Admin SDK Real-time Document Listeners
  - Cryptographic HMAC-SHA256 Signed Webhooks
              │
              ▼
[ Kyro Discord Bot Ecosystem ]
  - Python 3.13 Discord.py Runtime
  - Discord Components V2 Interactive Containers
  - Dynamic Role Progression Daemon
  - Slash and Prefix Command Parsers
```

### End-to-End Event Sequences

#### Sequence A: Account Handshake & Verification
1. User executes `?arena link` or `/arena link` in Discord.
2. Bot invokes internal token generator producing a single-use, 6-digit nonce expiring in 10 minutes.
3. Bot responds with an ephemeral container containing a direct authentication URL:
   `https://arena.vasudevai.in/settings?link=NONCE_TOKEN`
4. User completes Google Sign-in on Arena. The web application resolves the nonce and stores the user's Discord ID into their Firestore profile document.
5. Firestore snapshot emits a mutation event to the bot daemon.
6. Bot verifies the handshake and automatically grants the "Verified Builder" role in the Discord server.

#### Sequence B: Progression & Automatic Elevation
1. User completes an open-source bounty; PR is reviewed and merged on GitHub.
2. Arena backend increments total user XP (for example, +500 XP crossing the 2,000 XP boundary).
3. Cloud Firestore updates user Level from Level 2 (Builder) to Level 3 (Warrior).
4. The bot's snapshot listener captures the document update.
5. Bot removes the previous `@Arena Builder` role and provisions the `@Arena Warrior` role on Discord.
6. Bot dispatches a level-up celebratory container to the designated server feed channel.

---

## 4. FULL FEATURE MATRIX

The integration covers the entire functional surface of the platform without omissions:

```
+------------------------------------------------------------------------+
|                        VASUDEV AI ARENA PLATFORM                       |
+-------------------+--------------------+-------------------------------+
| Module            | In-App Capability  | Discord Connected Capability  |
+-------------------+--------------------+-------------------------------+
| Identity & Auth   | Google Sign-In     | Account Handshake & Verify    |
| Builder Profile   | /u/{username} Page | Interactive Components V2 Card|
| Progression       | 10-Tier XP System  | Automated Role Synchronization|
| Badges & Streaks  | 40+ Badges, Days   | Badge Showcase on Profile     |
| Quests System     | Daily/Weekly Tasks | Quest Browser & Proof Submit  |
| Bounties Engine   | GitHub Issues/PRs  | Real-Time Bounty Drop Radar   |
| Leaderboard       | Live Season Ranks  | Top 10 Live Server Standings  |
| Seasonal Rewards  | Finale Drop Tracker| Season Countdown & Drop Alerts|
+-------------------+--------------------+-------------------------------+
```

### Detailed Functional Scope
1. **Builder Identity (`/u/{username}`):** Displays username, verified badge, joined date, total XP, current rank title, streak status, and recent contributions directly inside Discord.
2. **10-Tier Level Progression:** Strict adherence to official XP boundaries with bidirectional status synchronization.
3. **Quests Engine:** Inspection of active tasks (starter quests, daily challenges, weekly sprints).
4. **Open-Source Bounty Radar:** Automated push notification to channels when open issues in the Vasudev AI ecosystem are posted.
5. **Leaderboard & Season System:** Live ranking table displaying top 10 builders competing for seasonal prizes (cash drops, swags, hoodies).

---

## 5. DATABASE & DOCUMENT SCHEMA SPECIFICATIONS

The Firestore schema operates with structured document models mirrored in memory within the Discord bot daemon.

### Collection: `users`
```typescript
interface ArenaUserDocument {
  // Identity & Auth
  uid: string;                       // Firebase Auth UID
  username: string;                  // Unique handle (arena.vasudevai.in/u/{slug})
  displayName: string;               // Full display name
  email: string;                     // Primary email address
  avatarUrl: string;                 // Profile avatar URL
  discordId?: string;                // Discord Snowflake ID (if linked)
  githubUsername?: string;           // Connected GitHub handle
  
  // Progression & Gamification
  xp: number;                        // Total verifiable XP
  level: number;                     // Integer Level Tier (1 to 10)
  levelTitle: string;                // Title (Explorer, Builder, Warrior, etc.)
  streakDays: number;                // Consecutive daily activity count
  lastActiveTimestamp: number;       // Unix epoch timestamp
  
  // Achievements & Activity
  badges: string[];                  // Array of unlocked badge IDs
  completedQuestsCount: number;      // Total completed quests
  mergedBountiesCount: number;       // Total accepted GitHub contributions
  referralCode: string;              // User referral string
  referredBy?: string;               // Referrer UID
  
  // Timestamps
  createdAt: FirebaseFirestore.Timestamp;
  updatedAt: FirebaseFirestore.Timestamp;
}
```

### Collection: `bounties`
```typescript
interface ArenaBountyDocument {
  id: string;                        // Unique bounty identifier
  title: string;                     // Task summary
  repo: string;                      // GitHub repository path (e.g. Vasudev-ai/Core)
  issueUrl: string;                  // GitHub issue URL
  difficulty: "beginner" | "intermediate" | "advanced";
  xpReward: number;                  // Integer XP value (500 to 1500)
  status: "open" | "claimed" | "under_review" | "merged";
  claimedBy?: string;                // User UID / Discord ID
  tags: string[];                    // Technology tags (e.g. ["Python", "FastAPI"])
  createdAt: FirebaseFirestore.Timestamp;
}
```

### Collection: `season_state`
```typescript
interface ArenaSeasonDocument {
  seasonNumber: number;              // Numeric season index (e.g. 1)
  title: string;                     // Season label (e.g. "Season 01: Genesis")
  startTime: number;                 // Epoch start timestamp
  endTime: number;                   // Epoch end timestamp
  prizePoolDescription: string;      // Summary of seasonal awards
  status: "active" | "concluded";
}
```

---

## 6. API & REAL-TIME INTEGRATION PROTOCOLS

Two complementary integration vectors guarantee resilient, real-time communication:

### Vector 1: Firebase Admin SDK Streaming Listener (Primary)
The Python bot utilizes the official Firebase Admin SDK with Google Cloud Service Account credentials to establish duplex Firestore snapshot streams:
- Collection listeners on `users` detect XP and role changes instantly.
- Collection listeners on `bounties` detect new issues and broadcast alerts without polling delays.

### Vector 2: Authenticated Webhook Dispatcher (Secondary / Action Confirmations)
For manual reviewer actions or external triggers, the Next.js API routes dispatch signed HTTP POST requests to the bot's internal aiohttp server:

```http
POST /api/v1/arena/event-dispatch
Host: bot.vasudevai.in
Content-Type: application/json
X-Arena-Signature-256: <HMAC-SHA256 signature generated with shared secret>

{
  "event": "bounty.merged",
  "timestamp": 1727734200,
  "data": {
    "discord_id": "987654321012345678",
    "bounty_title": "Implement Redis Cache",
    "xp_gained": 750,
    "total_xp": 5250,
    "new_level": 4,
    "level_title": "Guardian"
  }
}
```

---

## 7. DISCORD INTERFACE & COMPONENTS V2 DESIGN

User interfaces in Discord replicate the Neo-Brutalist aesthetics of the web application using Discord Components V2 structural layouts.

### Interface Mockup 1: Builder Profile (`?arena profile`)
```
+------------------------------------------------------------------------+
| VASUDEV AI ARENA - BUILDER IDENTITY                      LIVE PROFILE  |
+------------------------------------------------------------------------+
| [ AVATAR ]   Aryan Sharma (@aryanbuilds)                               |
|              Level 03 - Warrior Builder                                |
|              Joined: Sep 2026 - Verified Builder                       |
+------------------------------------------------------------------------+
| XP SCORE          CURRENT LEVEL        ACTIVE STREAK     QUESTS DONE   |
| 2,450 XP          LVL 03 Warrior       7 Days            14 Quests     |
+------------------------------------------------------------------------+
| UNLOCKED BADGES (6)                                                    |
| [First Blood]  [7-Day Streak]  [Documentation Hero]                    |
| [Top 10 Season] [Early Builder] [Open Source Hunter]                   |
+------------------------------------------------------------------------+
| RECENT ARENA CONTRIBUTIONS                                             |
| - PR #14 Merged in Vasudev-ai/Core ......................... +500 XP   |
| - Daily Quest: Code Architecture Review .................... +100 XP   |
| - Community Referral: Verified Member Joined ............... +200 XP   |
+------------------------------------------------------------------------+
| [ View on Arena Web ]     [ Server Rank ]     [ Available Quests ]     |
+------------------------------------------------------------------------+
```

### Interface Mockup 2: Live Leaderboard (`?arena leaderboard`)
```
+------------------------------------------------------------------------+
| VASUDEV AI ARENA - SEASON 01 LEADERBOARD                14d 06h Left   |
+------------------------------------------------------------------------+
| TOP BUILDERS COMPETING FOR SEASONAL DROPS                              |
|                                                                        |
| Rank 01: Aryan Sharma (@aryanbuilds) ........ 12,450 XP [LVL 05 Sage]  |
| Rank 02: Devika Nair (@devbuilds) ........... 11,200 XP [LVL 05 Sage]  |
| Rank 03: Rohan Verma (@rohan_ai) ............  9,850 XP [LVL 04 Guard] |
| Rank 04: Kavya Patel (@kavya_code) ..........  8,100 XP [LVL 04 Guard] |
| Rank 05: Aman Gupta (@amang) ................  6,750 XP [LVL 04 Guard] |
| Rank 06: Vikram Singh (@vikram) .............  5,300 XP [LVL 04 Guard] |
| Rank 07: Pooja Sharma (@pooja) ..............  4,900 XP [LVL 03 Warr]  |
| Rank 08: Sameer Khan (@sameer) ..............  3,400 XP [LVL 03 Warr]  |
| Rank 09: Neha Joshi (@neha) .................  2,800 XP [LVL 03 Warr]  |
| Rank 10: Aditya Rao (@aditya) ...............  2,100 XP [LVL 03 Warr]  |
+------------------------------------------------------------------------+
| Your Standing: Rank 14 - 1,850 XP (Target: +250 XP to crack Top 10)    |
+------------------------------------------------------------------------+
| [ Explore Quests ]        [ Season Rewards ]        [ Refresh Board ]  |
+------------------------------------------------------------------------+
```

---

## 8. ROLE & LEVEL SYNCHRONISATION ENGINE

The bot provisions and manages a structured role hierarchy in the Discord server corresponding to the exact XP boundaries established on the Arena platform:

| Tier | Level Name | Required XP Threshold | Discord Role Designation | Hex Color Accent |
| :---: | :--- | :---: | :--- | :--- |
| **01** | **Explorer** | `0 XP` | `@Arena Explorer` | `#BFD7FF` (Sky Blue) |
| **02** | **Builder** | `500 XP` | `@Arena Builder` | `#FFE45C` (Yellow) |
| **03** | **Warrior** | `2,000 XP` | `@Arena Warrior` | `#C9B8FF` (Lilac) |
| **04** | **Guardian** | `5,000 XP` | `@Arena Guardian` | `#BFEEDB` (Mint) |
| **05** | **Sage** | `10,000 XP` | `@Arena Sage` | `#FFC19D` (Peach) |
| **06** | **Architect** | `20,000 XP` | `@Arena Architect` | `#9AD0F5` (Ocean) |
| **07** | **Champion** | `40,000 XP` | `@Arena Champion` | `#E8C547` (Gold) |
| **08** | **Legend** | `75,000 XP` | `@Arena Legend` | `#FF6B6B` (Crimson) |
| **09** | **Mythic** | `120,000 XP` | `@Arena Mythic` | `#A06CD5` (Amethyst) |
| **10** | **Eternal** | `200,000 XP` | `@Arena Eternal` | `#FFFFFF` (Prismatic) |

### Promotion Mechanics
1. When a user's total XP crosses into a higher boundary, the daemon assigns the new level role and revokes preceding tier roles.
2. A structured celebration announcement is emitted to the server's `#level-ups` or `#arena-feed` channel.
3. The server's in-memory leaderboard cache is invalidated and rebuilt immediately.

---

## 9. SECURITY, AUTH & ANTI-ABUSE STANDARDS

1. **Cryptographic Handshake Security:**
   - Linkage between Discord IDs and Google accounts requires single-use cryptographic nonces verified exclusively through authenticated Arena browser sessions.
2. **Immutable XP Origin:**
   - The Discord bot runtime is strictly read-only regarding XP allocation, except for verified community activities where signed server transactions take place. Arbitrary bot commands cannot alter user XP.
3. **Rate Limiting & Anti-Spam:**
   - All public bot commands feature per-user cooldown timers (5 seconds for queries, 60 seconds for link handshakes). Channel alerts are throttled to prevent Discord rate-limiting.
4. **Data Protection Compliance:**
   - Personal emails retrieved during Google OAuth are never stored in Discord bot cache, logs, or public Discord embeds. Only public handles, avatar links, and gameplay statistics are indexed.

---

## 10. MILESTONES & IMPLEMENTATION CHECKLIST

| Phase | Milestone Objective | Core Technical Deliverable | Status |
| :---: | :--- | :--- | :---: |
| **Phase 1** | **Credentials & Connection** | Configure Firebase Service Account JSON / Admin SDK in Kyro | `Awaiting Key` |
| **Phase 2** | **Account Handshake Flow** | Implement `?arena link` nonce verification and `/u/` mapping | `Ready to Code` |
| **Phase 3** | **Builder Profile Command** | Implement `?arena profile` Components V2 card viewer | `Ready to Code` |
| **Phase 4** | **Level Role Promotion Daemon** | Build automatic role upgrade handler across all 10 tiers | `Ready to Code` |
| **Phase 5** | **Live Leaderboard & Season** | Implement `?arena leaderboard` with Season 01 drop clock | `Ready to Code` |
| **Phase 6** | **Open Source Bounty Radar** | Channel alerts for new issues created in Vasudev AI repositories | `Ready to Code` |

---

> **Technical Handover Note:**  
> To initialize the real-time synchronization daemon, provide the Firebase project credentials (`serviceAccountKey.json`) or API webhook secret. The Kyro bot module structure is pre-configured to register and connect immediately.
