import asyncio
import time
import unittest
from kyrolink.clock import AudioClock
from kyrolink.ring_buffer import AudioRingBuffer
from kyrolink.rtp import RTPPacketizer
from managers.media import MediaManager

class TestKyroLinkInternal(unittest.IsolatedAsyncioTestCase):

    async def test_audio_clock_zero_drift(self):
        """Verify the monotonic nanosecond audio clock maintains 20ms cadence."""
        clock = AudioClock(frame_duration_ms=20.0)
        clock.start()

        for _ in range(5):
            await clock.tick()

        # Cumulative drift must be under 20ms (Windows timer quantum tolerance)
        self.assertLess(abs(clock.total_drift_ms), 20.0)

    async def test_ring_buffer_multicast(self):
        """Verify shared ring buffer multicasts 1 stream to multiple readers without lock contention."""
        buffer = AudioRingBuffer(capacity_frames=50)
        reader1 = buffer.create_reader()
        reader2 = buffer.create_reader()

        frame_a = b"\xf8\xff\xfe\x01"
        frame_b = b"\xf8\xff\xfe\x02"

        buffer.write(frame_a)
        buffer.write(frame_b)
        buffer.finish()

        self.assertEqual(await reader1.read_frame(), frame_a)
        self.assertEqual(await reader2.read_frame(), frame_a)
        self.assertEqual(await reader1.read_frame(), frame_b)
        self.assertEqual(await reader2.read_frame(), frame_b)
        self.assertIsNone(await reader1.read_frame())
        self.assertIsNone(await reader2.read_frame())

    def test_rtp_packetizer(self):
        """Verify RFC 3550 RTP 12-byte header serialization for Discord Voice UDP."""
        packetizer = RTPPacketizer(ssrc=0xABCDEF01)
        p1 = packetizer.create_packet(b"\x01\x02\x03\x04")
        self.assertEqual(len(p1), 16)
        self.assertEqual(p1[0], 0x80)
        self.assertEqual(p1[1], 120)

    async def test_kyrolink_loadtracks(self):
        """Verify MediaManager integrates cleanly into KyroLink track loader."""
        media = MediaManager()
        track = await media.resolve("Tum Hi Ho")
        await media.close()

        self.assertIsNotNone(track)
        self.assertTrue(track.stream_url.startswith("http"))
        self.assertEqual(track.bitrate_kbps, 320)

if __name__ == "__main__":
    unittest.main()
