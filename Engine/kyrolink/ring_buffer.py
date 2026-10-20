import asyncio
from typing import Optional, List

class AudioRingBuffer:
    """Fixed-capacity In-Memory Circular Ring Buffer for Opus Audio Frames.
    Allows lock-free multicasting: 1 Audio Stream can be consumed concurrently
    by hundreds of Discord Voice sockets and Web audio players without duplication.
    """

    def __init__(self, capacity_frames: int = 250) -> None:
        self.capacity = capacity_frames  # e.g., 250 frames = 5 seconds of audio at 20ms
        self._buffer: List[Optional[bytes]] = [None] * capacity_frames
        self._write_pos: int = 0
        self._total_written: int = 0
        self._is_finished: bool = False
        self._data_event: asyncio.Event = asyncio.Event()

    def write(self, opus_frame: bytes) -> None:
        """Write an Opus frame to the circular ring buffer."""
        self._buffer[self._write_pos] = opus_frame
        self._write_pos = (self._write_pos + 1) % self.capacity
        self._total_written += 1
        self._data_event.set()

    def finish(self) -> None:
        """Mark stream as complete (track finished)."""
        self._is_finished = True
        self._data_event.set()

    @property
    def is_finished(self) -> bool:
        return self._is_finished

    def create_reader(self) -> "RingBufferReader":
        return RingBufferReader(self)


class RingBufferReader:
    """Independent reader pointer for a consumer socket (e.g. 1 Discord Guild Player)."""

    def __init__(self, buffer: AudioRingBuffer) -> None:
        self.buffer = buffer
        self._read_pos: int = 0
        self._frames_read: int = 0

    async def read_frame(self) -> Optional[bytes]:
        """Read the next 20ms Opus frame. Waits if buffer underrun occurs."""
        while self._frames_read >= self.buffer._total_written:
            if self.buffer.is_finished:
                return None
            self.buffer._data_event.clear()
            await self.buffer._data_event.wait()

        frame = self.buffer._buffer[self._read_pos]
        self._read_pos = (self._read_pos + 1) % self.buffer.capacity
        self._frames_read += 1
        return frame
