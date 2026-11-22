"""Synthetic tests of read-only, input-triggered memory comparisons."""
import importlib.util
import unittest
from pathlib import Path

path = Path(__file__).with_name("to_navigation_probe.py")
spec = importlib.util.spec_from_file_location("to_navigation_probe", path)
probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)


class InputTraceTests(unittest.TestCase):
    def test_release_only(self):
        event = {"event": "input.buttons", "changed": {"down": False, "cross": True}}
        self.assertEqual(probe.navigation_releases(event), ("down",))
        self.assertEqual(probe.navigation_releases({"event": "input.buttons", "changed": {"up": True}}), ())
        self.assertEqual(probe.navigation_releases({"event": "game.start", "changed": {"up": False}}), ())

    def test_changed_offsets(self):
        actual = list(probe.changed_offsets(b"abcd", b"axcZ"))
        self.assertEqual(actual, [(1, ord("b"), ord("x")), (3, ord("d"), ord("Z"))])
        self.assertEqual(list(probe.changed_offsets(b"abcd", b"axcZ", limit=1)), actual[:1])

    def test_length_mismatch(self):
        with self.assertRaises(ValueError):
            list(probe.changed_offsets(b"abcd", b"abc"))


if __name__ == "__main__":
    unittest.main()
