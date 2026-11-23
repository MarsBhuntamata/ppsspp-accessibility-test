"""Offline tests for the first speaking title-menu companion."""
import importlib.util
from pathlib import Path
import sys
import unittest

root = Path(__file__).parent
sys.path.insert(0, str(root))
spec = importlib.util.spec_from_file_location("to_speaking_title", root / "to_speaking_title.py")
speaker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(speaker)


class FakeSpeaker:
    def __init__(self):
        self.sent = []

    def say(self, words):
        self.sent.append(words)


class SpeakerTests(unittest.TestCase):
    def test_title_indices(self):
        self.assertEqual(speaker.selection_announcement(0), "Title menu, option 1")
        self.assertEqual(speaker.selection_announcement(1), "Title menu, option 2")
        self.assertEqual(speaker.selection_announcement(2), "Title menu, option 3")

    def test_transitional_value_not_mislabeled(self):
        self.assertIsNone(speaker.selection_announcement(4))
        self.assertIsNone(speaker.selection_announcement(255))

    def test_move_speaks_once(self):
        voice = FakeSpeaker()
        self.assertTrue(speaker.record_and_announce(0, 1, voice))
        self.assertFalse(speaker.record_and_announce(1, 1, voice))
        self.assertFalse(speaker.record_and_announce(1, 4, voice))
        self.assertEqual(voice.sent, ["Title menu, option 2"])

    def test_short_memory_response_fails(self):
        import base64
        with self.assertRaises(ValueError):
            speaker.parse_value({"base64": base64.b64encode(b"\0").decode("ascii")})

    def test_candidate_value_at_proven_offset(self):
        import base64
        from to_target_watch import SIZE, OFFSET
        data = bytearray(SIZE)
        data[OFFSET] = 2
        self.assertEqual(speaker.parse_value({
            "base64": base64.b64encode(data).decode("ascii")}), 2)


if __name__ == "__main__":
    unittest.main()
