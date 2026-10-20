import time
from typing import Dict, Any, Optional
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
from schemas.responses import EngineResponse
from platforms.discord.service import DiscordPlatformService

router = APIRouter(prefix="/v1/platforms/discord", tags=["Platform: Discord"])

# Global Service Dependency Holder (initialized in main.py)
_discord_service: Optional[DiscordPlatformService] = None

def set_discord_service(service: DiscordPlatformService) -> None:
    global _discord_service
    _discord_service = service

def get_discord_service() -> DiscordPlatformService:
    if _discord_service is None:
        raise HTTPException(status_code=500, detail="Discord platform service not initialized")
    return _discord_service


class DiscordActionRequestPayload(BaseModel):
    guild_id: str
    action_name: str
    target_id: Optional[str] = None
    params: Dict[str, Any] = Field(default_factory=dict)


@router.post("/messages/ingest", response_model=EngineResponse)
async def ingest_discord_message(
    payload: Dict[str, Any],
    service: DiscordPlatformService = Depends(get_discord_service)
) -> EngineResponse:
    start = time.perf_counter_ns()
    res = await service.ingest_message(payload)
    elapsed_ms = (time.perf_counter_ns() - start) / 1_000_000.0
    return EngineResponse.ok(data=res, message="Discord message ingested", exec_time=elapsed_ms)


@router.post("/audits/ingest", response_model=EngineResponse)
async def ingest_discord_audit(
    payload: Dict[str, Any],
    service: DiscordPlatformService = Depends(get_discord_service)
) -> EngineResponse:
    start = time.perf_counter_ns()
    res = await service.ingest_audit(payload)
    elapsed_ms = (time.perf_counter_ns() - start) / 1_000_000.0
    return EngineResponse.ok(data=res, message="Discord audit log ingested", exec_time=elapsed_ms)


@router.post("/actions/execute", response_model=EngineResponse)
async def execute_discord_action(
    req: DiscordActionRequestPayload,
    service: DiscordPlatformService = Depends(get_discord_service)
) -> EngineResponse:
    start = time.perf_counter_ns()
    res = await service.execute_action(
        action_name=req.action_name,
        guild_id=req.guild_id,
        target_id=req.target_id,
        params=req.params
    )
    elapsed_ms = (time.perf_counter_ns() - start) / 1_000_000.0
    if not res.success:
        raise HTTPException(status_code=400, detail=res.message)
    return EngineResponse.ok(data=res.model_dump(), message=res.message, exec_time=elapsed_ms)


@router.get("/guilds/{guild_id}/stats", response_model=EngineResponse)
async def get_discord_guild_stats(
    guild_id: str,
    service: DiscordPlatformService = Depends(get_discord_service)
) -> EngineResponse:
    start = time.perf_counter_ns()
    msg_count = 0
    if service.cache:
        val = await service.cache.get(f"discord:guild:{guild_id}:msg_count")
        msg_count = int(val) if val else 0
    elapsed_ms = (time.perf_counter_ns() - start) / 1_000_000.0
    return EngineResponse.ok(
        data={"guild_id": guild_id, "messages_processed_today": msg_count},
        message="Guild stats fetched",
        exec_time=elapsed_ms
    )
