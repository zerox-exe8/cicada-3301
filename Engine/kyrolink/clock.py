import asyncio
import time
from typing import AsyncGenerator

class AudioClock:
    """High-Precision Drift-Compensating Monotonic Audio Clock.
    Maintains an absolute 50.000 packets/sec (20.00ms interval) cadence
    using nanosecond time tracking and hybrid micro-sleep to achieve sub-millisecond precision.
    """

    def __init__(self, frame_duration_ms: float = 20.0) -> None:
        self.frame_duration_ns: int = int(frame_duration_ms * 1_000_000)
        self.frame_duration_sec: float = frame_duration_ms / 1000.0
        self._start_time_ns: int = 0
        self._frame_count: int = 0
        self.total_drift_ms: float = 0.0

    def start(self) -> None:
        self._start_time_ns = time.perf_counter_ns()
        self._frame_count = 0
        self.total_drift_ms = 0.0

    async def tick(self) -> float:
        """Wait until the exact moment the next 20ms audio frame is due.
        Uses hybrid async sleep for the bulk delay and a microsecond spin for exact accuracy.
        """
        self._frame_count += 1
        expected_time_ns = self._start_time_ns + (self._frame_count * self.frame_duration_ns)
        now_ns = time.perf_counter_ns()

        delay_ns = expected_time_ns - now_ns
        # If more than 3ms remaining, yield to event loop
        if delay_ns > 3_000_000:
            await asyncio.sleep((delay_ns - 2_000_000) / 1_000_000_000.0)

        # Microsecond spin-lock for the final stretch to kill Windows timer jitter
        while time.perf_counter_ns() < expected_time_ns:
            pass

        actual_time_ns = time.perf_counter_ns()
        drift_ns = actual_time_ns - expected_time_ns
        self.total_drift_ms = drift_ns / 1_000_000.0
        return self.total_drift_ms

    async def generator(self) -> AsyncGenerator[int, None]:
        self.start()
        while True:
            await self.tick()
            yield self._frame_count
