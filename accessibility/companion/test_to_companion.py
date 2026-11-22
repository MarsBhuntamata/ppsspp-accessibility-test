"""Companion self-tests, runnable on CI without PPSSPP or Windows."""
import importlib.util
from pathlib import Path
import unittest

path = Path(__file__).with_name("to_companion.py")
spec = importlib.util.spec_from_file_location("to_companion", path)
companion = importlib.util.module_from_spec(spec)
spec.loader.exec_module(companion)


class CompanionTests(unittest.TestCase):
    def test_release_only(self):
        msg = {"event": "input.buttons", "changed": {"up": False, "cross": True}}
        self.assertEqual(companion.released_directions(msg), ("up",))
        self.assertEqual(companion.released_directions({"event": "input.buttons", "changed": {"up": True}}), ())
        self.assertEqual(companion.released_directions({"event": "game.quit"}), ())

    def test_memory_diff_reports_word_values(self):
        a = bytearray(b"\x00" * 16)
        b = bytearray(a)
        b[4] = 1
        b[8] = 2
        count, changes = companion.changed_words(bytes(a), bytes(b), 0x8800000)
        self.assertEqual(count, 2)
        self.assertEqual(changes, [(0x8800004, 0, 1), (0x8800008, 0, 2)])

    def test_memory_diff_is_bounded_per_block(self):
        a = bytes(64)
        b = bytes([1] * 64)
        count, changes = companion.changed_words(a, b)
        self.assertEqual(count, 16)
        self.assertEqual(len(changes), companion.MAX_CHANGES_PER_BLOCK)

    def test_stationary_selection_changes_survive(self):
        old_a = bytes([0, 0, 0, 0, 1, 0, 0, 0])
        old_b = old_a
        new_a = bytes([3, 0, 0, 0, 2, 0, 0, 0])
        new_b = bytes([4, 0, 0, 0, 2, 0, 0, 0])
        count, rows = companion.stable_changed_words(
            old_a, old_b, new_a, new_b, 0x09000000)
        self.assertEqual(count, 1)
        self.assertEqual(rows, [(0x09000004, 1, 2)])

    def test_unstable_baseline_excluded(self):
        old_a = bytes([1, 0, 0, 0])
        old_b = bytes([2, 0, 0, 0])
        new_a = new_b = bytes([3, 0, 0, 0])
        count, rows = companion.stable_changed_words(
            old_a, old_b, new_a, new_b, 0x09000000)
        self.assertEqual((count, rows), (0, []))

    def test_bad_snapshots_fail(self):
        with self.assertRaises(ValueError):
            companion.changed_words(b"\0", b"\0")


if __name__ == "__main__":
    unittest.main()
