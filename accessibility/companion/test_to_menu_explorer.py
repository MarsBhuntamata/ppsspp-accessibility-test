"""Offline tests for phase-aware non-destructive menu explorer."""
import importlib.util
from pathlib import Path
import sys
import unittest
from collections import Counter

folder = Path(__file__).parent
sys.path.insert(0, str(folder))
spec = importlib.util.spec_from_file_location("to_menu_explorer", folder / "to_menu_explorer.py")
explorer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(explorer)


class ExplorerTests(unittest.TestCase):
    def test_button_releases(self):
        msg = {"event": "input.buttons",
               "changed": {"cross": False, "up": False, "circle": True}}
        self.assertEqual(explorer.release_events(msg), ("up", "cross"))
        self.assertEqual(explorer.classify_action("cross"), "transition")
        self.assertEqual(explorer.classify_action("up"), "navigate")
        self.assertEqual(explorer.classify_action("square"), "other")

    def test_return_matches_selection(self):
        base = explorer.WINDOWS[0]
        a = {base: bytes([0, 0, 9])}
        b = {base: bytes([1, 0, 9])}
        c = {base: bytes([0, 0, 9])}
        prior = explorer.WINDOWS
        explorer.WINDOWS = (base,)
        try:
            count, matches = explorer.return_candidates(a, b, c)
            self.assertEqual(count, 1)
            self.assertEqual(matches, [(base, 0, 1)])
        finally:
            explorer.WINDOWS = prior

    def test_inverse_moves_get_credit(self):
        base = explorer.WINDOWS[0]
        a = {base: bytes([0])}
        b = {base: bytes([1])}
        c = {base: bytes([0])}
        # Return candidate helper uses the module's configured region set,
        # so use one real window with tiny first data and patch region set.
        prior = explorer.WINDOWS
        explorer.WINDOWS = (base,)
        try:
            scores, veto = {}, Counter()
            count, sampled, inverse = explorer.add_triplet(
                scores, veto, (a, b, c), ("down", "up"))
            self.assertEqual((count, sampled, inverse), (1, 1, True))
            self.assertEqual(explorer.ranking(scores, veto)[0][1], base)
            explorer.add_triplet(scores, veto, (a, b, c), ("down", "down"))
            self.assertEqual(explorer.ranking(scores, veto), [])
        finally:
            explorer.WINDOWS = prior

    def test_title_name_mapping_available_to_explorer(self):
        self.assertEqual(explorer.selection_announcement(0, {0: "New Game"}), "New Game")
        self.assertEqual(explorer.selection_announcement(1, {}), "Title menu, option 2")

    def test_fast_cursor_selection(self):
        a, b = explorer.FAST_CURSORS
        old = {a: 0, b: 0}
        new = {a: 1, b: 0}
        self.assertEqual(explorer.select_cursor(old, new, 1), (a, 1))
        self.assertEqual(explorer.select_cursor(old, new, 2), (a, 1))
        new = {a: 0, b: 1}
        self.assertEqual(explorer.select_cursor(old, new, 2), (b, 1))
        self.assertEqual(explorer.select_cursor(old, old, 2), (None, None))

    def test_fast_speech_is_short(self):
        self.assertEqual(explorer.speech_label(7, explorer.ADDRESS, 2, {}), "Option 3")
        self.assertNotIn("unverified", explorer.speech_label(7, explorer.ADDRESS, 2, {}))

    def test_fast_read_samples_full_region_once(self):
        import base64
        class ConnectionStub:
            def __init__(self):
                self.calls = []
            def request(self, event, **kwargs):
                self.calls.append((event, kwargs))
                data = bytearray(explorer.FAST_SIZE)
                data[explorer.FAST_OFFSETS[explorer.ADDRESS]] = 2
                return {"base64": base64.b64encode(data).decode("ascii")}
        conn = ConnectionStub()
        result = explorer.read_fast(conn)
        self.assertEqual(result[explorer.ADDRESS], 2)
        self.assertEqual(len(conn.calls), 1)
        self.assertEqual(conn.calls[0][1]["size"], 4096)

    def test_sparse_low_value_changes(self):
        base = explorer.WINDOWS[0]
        old = {base: bytes([0, 99, 2])}
        new = {base: bytes([1, 98, 3])}
        count, rows = explorer.small_changes(old, new)
        self.assertEqual(count, 2)
        self.assertEqual(rows, [(base, 0, 1), (base + 2, 2, 3)])


if __name__ == "__main__":
    unittest.main()
