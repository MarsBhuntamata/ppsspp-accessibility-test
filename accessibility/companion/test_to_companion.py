"""Offline regression tests for external Tactics Ogre companion."""
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
        self.assertEqual(companion.released_directions(
            {"event": "input.buttons", "changed": {"up": True}}), ())

    def test_true_return_to_position(self):
        a = (bytes([0, 0, 5, 99]), bytes([0, 0, 5, 99]))
        b = (bytes([1, 0, 5, 98]), bytes([1, 0, 5, 97]))
        c = (bytes([0, 0, 5, 96]), bytes([0, 0, 5, 95]))
        count, rows = companion.analyze_triplet(a, b, c, base=0x9000000)
        self.assertEqual(count, 1)
        self.assertEqual(rows, [(0x9000000, 0, 1)])

    def test_inconsistent_stationary_state_not_selected(self):
        a = (bytes([0]), bytes([0]))
        b = (bytes([1]), bytes([2]))
        c = (bytes([0]), bytes([0]))
        self.assertEqual(companion.analyze_triplet(a, b, c), (0, []))

    def test_same_direction_can_veto_double_buffer(self):
        a = (bytes([0]), bytes([0]))
        b = (bytes([1]), bytes([1]))
        c = (bytes([0]), bytes([0]))
        regions = ((0x9000000, 1),)
        opposite = companion.classify_triplet([a], [b], [c],
                                                ("down", "up"), regions)
        same = companion.classify_triplet([a], [b], [c],
                                            ("down", "down"), regions)
        self.assertEqual(opposite, (True, 1, [(0x9000000, 0, 1)]))
        self.assertEqual(same, (False, 1, [(0x9000000, 0, 1)]))
        scores = {0x9000000: {"returns": 1, "pairs": {(0, 1)}}}
        self.assertEqual(companion.summarize_candidates(scores, {0x9000000: 1}), [])

    def test_distinct_position_is_not_return(self):
        a = (bytes([0]), bytes([0]))
        b = (bytes([1]), bytes([1]))
        c = (bytes([2]), bytes([2]))
        self.assertEqual(companion.analyze_triplet(a, b, c), (0, []))

    def test_rank_repeated_returns(self):
        scores = {0x9000000: {"returns": 3, "pairs": {(0, 1)}}}
        ranked = companion.summarize_candidates(scores, {})
        self.assertEqual(ranked[0][0], 9)
        self.assertEqual(ranked[0][3], 0x9000000)


if __name__ == "__main__":
    unittest.main()
