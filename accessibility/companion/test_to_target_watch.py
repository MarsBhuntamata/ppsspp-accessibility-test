"""Focused title-menu memory watch regression tests."""
import importlib.util
from pathlib import Path
import unittest

path = Path(__file__).with_name("to_target_watch.py")
spec = importlib.util.spec_from_file_location("watch", path)
watch = importlib.util.module_from_spec(spec)
spec.loader.exec_module(watch)


class TargetWatchTests(unittest.TestCase):
    def test_candidate_offset(self):
        buf = bytearray(watch.SIZE)
        buf[watch.OFFSET] = 1
        self.assertEqual(watch.candidate_value(bytes(buf)), 1)

    def test_short_data_rejected(self):
        with self.assertRaises(ValueError):
            watch.candidate_value(b"\0")

    def test_release_event(self):
        msg = {"event": "input.buttons", "changed": {"up": False, "down": True}}
        self.assertEqual(watch.directions_released(msg), ("up",))
        self.assertEqual(watch.directions_released({"event": "game.quit"}), ())

    def test_compact_diff_prioritizes_watch_address(self):
        a = bytearray(watch.SIZE)
        b = bytearray(a)
        b[12] = 2
        b[watch.OFFSET] = 1
        rows = watch.concise_changes(a, b)
        self.assertEqual(rows[0], (watch.ADDRESS, 0, 1))
        self.assertIn((watch.WINDOW + 12, 0, 2), rows)

    def test_high_valued_noise_suppressed(self):
        a = bytearray(watch.SIZE)
        b = bytearray(a)
        b[0] = 255
        self.assertEqual(watch.concise_changes(a, b), [])


if __name__ == "__main__":
    unittest.main()
