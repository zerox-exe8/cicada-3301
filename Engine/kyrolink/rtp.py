import struct
from typing import Optional

class RTPPacketizer:
    """Constructs and serializes standard RFC 3550 RTP audio packets for Discord Voice."""

    RTP_VERSION = 2
    PAYLOAD_TYPE_OPUS = 120
    SAMPLES_PER_FRAME = 960  # 48kHz * 20ms

    def __init__(self, ssrc: int) -> None:
        self.ssrc: int = ssrc
        self.sequence: int = 0
        self.timestamp: int = 0

    def create_packet(self, opus_frame: bytes) -> bytes:
        """Pack an Opus audio frame into an unencrypted RTP packet.
        Format:
        [Byte 0: 0x80] [Byte 1: 0x78] [Bytes 2-3: Sequence] [Bytes 4-7: Timestamp] [Bytes 8-11: SSRC] [Opus Data]
        """
        # Wrap sequence at 65535 (16-bit unsigned)
        seq = self.sequence & 0xFFFF
        # Wrap timestamp at 4294967295 (32-bit unsigned)
        ts = self.timestamp & 0xFFFFFFFF

        header = struct.pack(">BBHII", 0x80, self.PAYLOAD_TYPE_OPUS, seq, ts, self.ssrc)

        self.sequence = (self.sequence + 1) & 0xFFFF
        self.timestamp = (self.timestamp + self.SAMPLES_PER_FRAME) & 0xFFFFFFFF

        return header + opus_frame
