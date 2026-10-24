"""Guards the no-stutter setting: the stream's audio mixer waits for late audio.
Run: python3 -m unittest tools/test_audio_settings.py (no GStreamer needed)."""
import pathlib
import re
import unittest

SRC = (pathlib.Path(__file__).resolve().parent.parent / 'vn_video' / 'audio.py').read_text()


class AudioSettings(unittest.TestCase):
    def test_mixer_waits_for_late_audio(self):
        m = re.search(r'^MIXER_LATENCY_NS = ([\d_]+)', SRC, re.M)
        self.assertIsNotNone(m, 'MIXER_LATENCY_NS is missing')
        self.assertGreaterEqual(int(m.group(1).replace('_', '')), 200_000_000)
        self.assertIn('audiomixer name=mix latency={MIXER_LATENCY_NS}', SRC)


if __name__ == '__main__':
    unittest.main()
