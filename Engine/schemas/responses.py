import time
from typing import Optional, Any, Dict
from pydantic import BaseModel, Field

class EngineResponse(BaseModel):
    success: bool
    status_code: int = 200
    message: str = "OK"
    data: Optional[Any] = None
    execution_time_ms: float = 0.0
    timestamp: float = Field(default_factory=time.time)
    error_code: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)

    @classmethod
    def ok(cls, data: Any = None, message: str = "OK", exec_time: float = 0.0) -> "EngineResponse":
        return cls(success=True, status_code=200, message=message, data=data, execution_time_ms=exec_time)

    @classmethod
    def error(cls, message: str, status_code: int = 400, error_code: Optional[str] = None) -> "EngineResponse":
        return cls(success=False, status_code=status_code, message=message, error_code=error_code)
