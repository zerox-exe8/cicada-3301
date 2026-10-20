import os
from typing import Optional
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

class EngineSettings(BaseSettings):
    # Core Engine Info
    ENV: str = Field(default="development")
    DEBUG: bool = Field(default=False)
    WORKER_ID: str = Field(default="worker-01")
    
    # Ingress Server (FastAPI / Gateway)
    HOST: str = Field(default="0.0.0.0")
    PORT: int = Field(default=8000)
    AUTH_SECRET_KEY: str = Field(default="kyro-super-engine-secret-key-change-in-prod")
    
    # In-Memory Cache (Dragonfly / Redis)
    REDIS_URL: str = Field(default="redis://localhost:6379/0")
    REDIS_MAX_CONNECTIONS: int = Field(default=50)
    
    # Database (PostgreSQL via PgBouncer)
    POSTGRES_DSN: str = Field(default="postgresql://postgres:postgres@localhost:5432/kyro_engine")
    DB_POOL_MIN_SIZE: int = Field(default=5)
    DB_POOL_MAX_SIZE: int = Field(default=30)
    
    # Event Fabric
    NATS_URL: str = Field(default="nats://localhost:4222")
    USE_NATS: bool = Field(default=False)  # Fallback to high-performance async memory bus when NATS is off
    
    # KyroLink Anti-Ban & Unblockable Audio Node Settings
    PROXY_LIST: str = Field(default="", description="Comma-separated list of residential/datacenter/SOCKS5 proxies")
    PROXY_QUARANTINE_SECONDS: float = Field(default=300.0, description="Auto-quarantine duration for blocked IPs")
    YOUTUBE_CLIENTS: str = Field(default="android_music,android,ios", description="Innertube client targets to bypass BotGuard")
    YOUTUBE_COOKIE_FILE: Optional[str] = Field(default=None, description="Path to Netscape cookies.txt if available")
    SPOTIFY_CLIENT_ID: Optional[str] = Field(default=None, description="Spotify Client ID for high-speed metadata extraction")
    SPOTIFY_CLIENT_SECRET: Optional[str] = Field(default=None, description="Spotify Client Secret")
    AUDIO_PREBUFFER_SECONDS: int = Field(default=5, description="Audio prebuffer seconds in RingBuffer for zero-freeze playback")

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

settings = EngineSettings()
