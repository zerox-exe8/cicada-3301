# KYRO DISTRIBUTED CORE ENGINE — SYSTEM DESIGN SPECIFICATION
**Target Scale:** 100,000 Concurrent Active Users (C100K CCU)  
**Throughput Target:** 20,000 – 50,000 Requests/Sec (RPS)  
**Latency SLA:** p99 < 50ms (API), p99 < 15ms (Internal Event Bus), p99 < 5ms (Reflex Interceptor)  
**Availability:** 99.99% (High Availability, Zero-Downtime Hot Swapping)

---

## 1. ARCHITECTURAL PHILOSOPHY: THE MICRO-KERNEL HUB-AND-SPOKE

Kyro Engine is designed as a **Headless Event-Driven Distributed Kernel**. It strips away all platform-specific dependencies (Discord API, Telegram MTProto, Web DOM) and operates strictly on standardized, typed domain events.

### Core Tenets:
1. **Platform Neutrality:** The engine does not know what Discord or Telegram is. It only knows `Entities` (Tenants, Guilds, Channels, Users, Roles) and `Events` (Messages, AuditActions, AudioPackets, Telemetry).
2. **Actor-Isolated Concurrency:** Every Guild/Community operates as an isolated virtual actor. Events for the same guild are serialized in FIFO order to permanently eliminate race conditions and database deadlocks.
3. **Tri-Tier Reflex AI Pipeline:** 99% of security and moderation decisions happen in microseconds at the reflex layer; only genuine ambiguities escalate to semantic vectors or deep LLM reasoning.
4. **Zero-DB Choke (L1/L2 Caching + Connection Virtualization):** 90%+ of all reads resolve in-memory. Database writes are batched and buffered through transaction-pooled queues.

---

## 2. SYSTEM TOPOLOGY & LAYER BREAKDOWN

```
[ Clients: Discord Bot | Web Dashboard | Telegram Bot | Voice Worker ]
                                  │
                                  ▼
┌──────────────────────────────────────────────────────────────────┐
│ LAYER 1: EDGE INGRESS & GATEWAY                                  │
│ - Protocol Termination: WebSockets, gRPC, HTTP/2                 │
│ - Security: DDoS Protection, Token-Bucket Rate Limiting (Redis)   │
│ - Auth Verification: JWT / Ephemeral Handshake Token             │
└─────────────────────────────────┬────────────────────────────────┘
                                  │
                                  ▼
┌──────────────────────────────────────────────────────────────────┐
│ LAYER 2: DISTRIBUTED EVENT FABRIC (NATS JetStream / Redis Bus)  │
│ - Topics: event.security.*, event.media.*, event.moderation.*    │
│ - Guarantees: At-least-once delivery, sub-millisecond dispatch   │
└─────────────────────────────────┬────────────────────────────────┘
                                  │
                                  ▼
┌──────────────────────────────────────────────────────────────────┐
│ LAYER 3: STATELESS EXECUTION FLEET (Core Workers)                │
│ - Per-Guild Actor Model (Serialized Event Processing)            │
│ - Business Managers: Antinuke, Moderation, Tickets, Media, Meet  │
│ - Tri-Tier Sentinel Agent Brain                                  │
└───────────────────┬──────────────────────────────┬───────────────┘
                    │                              │
                    ▼                              ▼
┌───────────────────────────────┐  ┌───────────────────────────────┐
│ LAYER 4: IN-MEMORY HOT STATE  │  │ LAYER 5: PERSISTENT STORAGE   │
│ - DragonflyDB / Redis Cluster │  │ - PostgreSQL 16 (Master/Repl) │
│ - L1 In-Process Cache (RAM)   │  │ - PgBouncer (Tx Pooling)      │
│ - Ephemeral Sessions & Locks  │  │ - TimescaleDB (Audit Logs)    │
└───────────────────────────────┘  └───────────────────────────────┘
```

---

## 3. DEEP DIVE: LAYER SPECIFICATIONS

### Layer 1: Ingress & Gateway Layer
* **Protocol Support:**
  * **gRPC (Protocol Buffers):** High-speed inter-service communication (Discord Bot Adapter <-> Engine).
  * **WebSocket (WSS):** Real-time bidirectional streaming for Web Dashboards & Voice state feeds.
  * **HTTP/2 (REST):** Public webhooks, billing integrations, external callbacks.
* **Rate Limiting Engine:**
  * Distributed Token Bucket algorithm implemented via atomic Redis/Dragonfly scripts.
  * Tiers: Per-IP, Per-User, Per-Guild.
  * Abuse Protection: Burst traffic automatically throttled with `429 Too Many Requests` + progressive backoff penalties before hitting workers.

### Layer 2: Event Fabric (The Nervous System)
* **Technology:** NATS JetStream (or Redis Streams fallback).
* **Pattern:** Publish-Subscribe with Consumer Groups.
* **Partitioning Key:** `guild_id` or `tenant_id` ensures that all events for a specific community hit the designated worker partition in exact chronological order.
* **Dead Letter Queue (DLQ):** Any event that fails processing after 3 exponential retries is routed to a DLQ for inspection without blocking the primary event stream.

### Layer 3: Core Stateless Execution Fleet
* **Concurrency Engine:** Python 3.13 with `uvloop` (C-based epoll event loop) + native Asyncio.
* **Worker Isolation:** Workers are completely stateless. Scale from 2 instances to 50 instances on demand.
* **The Guild Actor Queue:**
  * Each guild has an active in-memory lock/queue.
  * Prevents state conflict (e.g., simultaneous whitelist addition and role deletion will never conflict).

### Layer 4 & 5: State & Data Persistence
* **L1 Cache (In-Worker RAM):**
  * Holds immutable configs (server prefix, active module toggles, guild tier).
  * TTL: 15–30 seconds. Invalidated instantly via Redis Pub/Sub broadcast on update.
* **L2 Cache (Distributed Memory - DragonflyDB):**
  * Holds mutable operational state: active voice sessions, rate-limit counters, ongoing ticket states, temp-bans.
* **Persistent DB (PostgreSQL + PgBouncer):**
  * Max 100 dedicated physical connections from PgBouncer to PostgreSQL.
  * PgBouncer handles up to 50,000 incoming worker transactions via pooling.
  * Read-Write splitting: Heavy analytical queries and log searches hit Read Replicas; state updates hit Primary.

---

## 4. AUTONOMOUS AGENT DESIGN: TRI-TIER SENTINEL BRAIN

To protect 100k users in real-time without latency spikes or insane LLM costs, the engine implements a **Tri-Tier Reflex-Reasoning Architecture**:

```
Incoming Action (Message / Audit Event / Webhook)
                      │
                      ▼
        [ STAGE 1: REFLEX INTERCEPTOR ]
        - Execution Time: < 1ms
        - Technology: Compiled Regex, Bloom Filters, Token Burst
        - Decision: Normal (Pass) or Flagged
                      │
            (If Flagged / Suspicious)
                      ▼
        [ STAGE 2: SEMANTIC PERCEPTION ]
        - Execution Time: 15 - 30ms
        - Technology: Local Vector Search / Embeddings
        - Match against known raid patterns, toxicity vectors
        - Decision: High Confidence Action OR Ambiguous
                      │
            (If Ambiguous / High Complexity)
                      ▼
        [ STAGE 3: COGNITIVE REASONING AGENT ]
        - Execution Time: 300 - 800ms
        - Technology: Fast LLM (Gemini 2.5/3 Flash) with Structured Output
        - Inputs: 5-minute event trail + server policy guidelines
        - Outputs: Strict Pydantic Action (Quarantine, Lock, Escalate)
```

### Agent Safeguards:
1. **Idempotency Keys:** Every agent action carries a unique hash `MD5(guild_id + target_id + action + timestamp_window)`. Duplicate execution is physically impossible.
2. **Deterministic Enforcers:** LLM outputs are validated against strict schema before any action is executed on the database or network.
3. **Kill Switch:** Guild owners can disable AI autonomous actions instantly via a single hardware-level bypass flag stored in L1 cache.

---

## 5. HARDWARE TUNING & THE C100K PROBLEM

To handle 100k concurrent connections on Linux hosts:
* **File Descriptors:** `ulimit -n 1048576` (enables over 1 million concurrent sockets).
* **TCP Memory & Backlog:**
  * `net.core.somaxconn = 65535`
  * `net.ipv4.tcp_max_syn_backlog = 65535`
  * `net.ipv4.tcp_tw_reuse = 1` (instant port recycling).
* **Event Loop:** `uvloop` replaces standard `asyncio.SelectorEventLoop`, providing C-level epoll performance on Linux.

---

## 6. PROJECT DIRECTORY ARCHITECTURE (`Engine/`)

```
Engine/
├── SYSTEM_DESIGN.md         # Master System Design Specification (This Document)
├── pyproject.toml           # Engine dependencies, build tools & metadata
├── config/                  # Environment & Engine Settings
│   ├── settings.py          # Pydantic BaseSettings (validated env vars)
│   └── constants.py         # Global opcode constants, limits & SLAs
├── core/                    # The Central Micro-Kernel
│   ├── bus/                 # Event Bus (NATS / Redis / Memory implementations)
│   ├── gateway/             # Ingress interfaces (gRPC & WebSocket servers)
│   ├── actors/              # Guild/Tenant concurrency actor model
│   └── pipeline/            # Middleware execution chain (Auth, RateLimit, Log)
├── schemas/                 # Platform-Agnostic Data Contracts (Pydantic Models)
│   ├── events.py            # Generic Event definitions (MessageEvent, AuditEvent)
│   ├── entities.py          # Domain entities (User, Guild, Channel, Role)
│   └── responses.py         # Standardized API response contracts
├── agents/                  # Autonomous Sentinel Security Engine
│   ├── reflex/              # Stage 1: Ultra-fast regex & bloom filters (<1ms)
│   ├── semantic/            # Stage 2: Embeddings & similarity matcher (<30ms)
│   └── reasoning/           # Stage 3: LLM reasoning agent (Pydantic function calling)
├── managers/                # Platform-Agnostic Business Services
│   ├── media.py             # Audio/Video metadata & 320kbps Akamai stream link extractor
│   ├── security.py          # Anti-raid, quarantine, and policy enforcement
│   ├── meeting.py           # Audio transcription & AI meeting summary pipeline
│   └── ticket.py            # Omni-channel support ticketing engine
├── platforms/               # Hexagonal Ports & Adapters (Isolated Platform Chambers)
│   ├── discord/             # Dedicated Discord Platform Adapter
│   │   ├── translator.py    # Raw Discord JSON payloads <-> Universal Events
│   │   ├── actions.py       # Discord-specific action execution (Ban, Kick, Timeout, Roles)
│   │   ├── service.py       # Discord Platform Service Orchestrator
│   │   └── routes.py        # Dedicated Discord API Endpoints (/v1/platforms/discord/*)
│   ├── telegram/            # Future Telegram MTProto & PyTgCalls adapter
│   └── web/                 # Future Web App & WebSocket adapter
├── storage/                 # Persistence & Caching Abstraction
│   ├── cache.py             # L1 In-Memory + L2 Redis/DragonflyDB driver
│   ├── db.py                # PostgreSQL connection pooler (asyncpg + PgBouncer)
│   └── repositories/        # Clean CRUD repository pattern per domain
└── tests/                   # Load, benchmark & unit test suite
    ├── benchmarks/          # Concurrency & latency load tests (Locust/K6)
    └── unit/                # Core isolation test cases
```

---

## 7. MIGRATION STRATEGY: HOW KYRO CONNECTS

1. **Phase 1 (Engine Initialization):** Build and unit-test `Engine/` independently with zero impact on `Kyro/`.
2. **Phase 2 (Adapter Connection):** In `Kyro/src/core/`, add a lightweight `EngineClient` (gRPC / WebSocket).
3. **Phase 3 (Progressive Handoff):**
   * Antinuke security checks switch from local Kyro managers to Engine API.
   * Music stream resolution routes through `Engine/managers/media.py`.
   * Meeting transcripts route through `Engine/managers/meeting.py`.
4. **Phase 4 (Omni-Channel Activation):** Connect Web Dashboard, Telegram Bot, and external microservices to the same `Engine/` gateway.

---

## 8. KYROLINK: NATIVE ZERO-JVM AUDIO NODE & UNBLOCKABLE ARCHITECTURE

### 8.1 The Problem with Java Lavalink & Traditional Nodes
1. **JVM Memory Bloat:** Java Lavalink consumes 400MB - 1GB RAM on idle, with stop-the-world Garbage Collection (GC) pauses causing audible voice jitter and packet loss.
2. **Cloud Datacenter IP Bans (429 & BotGuard):** YouTube actively blocks major cloud providers (Hetzner, OVH, AWS, DigitalOcean) with HTTP 429 and `Sign in to confirm you're not a bot` challenges when web scraping.
3. **Spotify DRM Obstacle:** Spotify streams are Widevine DRM-encrypted, requiring reverse-engineered ISRC bridging to high-bitrate CDNs.

### 8.2 The 4-Tier Zero-Block, Zero-Freeze Resolution Engine
KyroLink (`Engine/kyrolink/`) operates as a completely native, in-house audio subsystem using Python 3.13 asyncio and nanosecond monotonic clocks (`time.perf_counter_ns`):

```
                       [Incoming Track / Query]
                                  │
                                  ▼
                     [UnblockableResolver Router]
                                  │
         ┌────────────────────────┼────────────────────────┐
         ▼                        ▼                        ▼
  [Tier 1: Akamai CDN]    [Tier 2: Spotify Bridge]  [Tier 3: YouTube Android]
  - JioSaavn DES Decrypt  - OEmbed & Public API     - Innertube Android App Emulation
  - 320kbps MP4 AAC       - ISRC Extraction         - Rotating Proxy Pool Injection
  - 0% Cloud Block Risk   - Bridges to Tier 1 / 3   - Auto-Quarantine on 429
         │                        │                        │
         └────────────────────────┼────────────────────────┘
                                  ▼
                    [Tier 4: SoundCloud / Invidious]
                                  ▼
                [5-Second PCM AudioRingBuffer Pacer]
                                  ▼
                [RFC 3550 RTP Packetizer (Discord Voice)]
```

### 8.3 Reverse-Engineering Principles (Inspired by REA)
* **Never Rely on Web Scraping:** Web endpoints trigger BotGuard and PoToken verification challenges.
* **Native Client Emulation (`ANDROID_MUSIC`):** Native Android/iOS applications communicate via pre-signed internal Innertube protocols that do not require browser PoTokens.
* **Zero-Bandwidth Proxy Efficiency:** Proxies are ONLY used for the initial 2KB metadata extraction handshake. Audio packets stream directly from high-speed edge CDNs (`googlevideo.com`, `saavncdn.com`), eliminating proxy bandwidth bottlenecks.
* **Self-Healing Proxy Pool:** Quarantines blocked IPs for 5 minutes automatically upon HTTP 429/403 and falls back seamlessly to unquarantined nodes.

### 8.4 Universal Host-Anywhere Portability
The entire engine is guaranteed to run across **any host environment**:
* **Cloud PaaS (Railway, Render, Fly.io, Heroku):** Auto-adapts to dynamic `$PORT` environment variables with zero code changes.
* **Bare Metal / VPS (Hetzner, OVH, AWS EC2):** Supported by `docker-compose.yml` with C100K kernel tuning (`ulimit -n 1048576`).
* **Offline Resilience:** If Redis, PostgreSQL, or NATS are unavailable, the engine gracefully falls back to L1 in-process caching and memory storage without crashing.

