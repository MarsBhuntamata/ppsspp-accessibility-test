"""Tests for native navigation trace parsing and candidate ranking."""
import importlib.util
from pathlib import Path
import unittest

path = Path(__file__).with_name("to_trace_report.py")
spec = importlib.util.spec_from_file_location("to_trace_report", path)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


class TraceReportTests(unittest.TestCase):
    def test_directions_and_reversible_candidate(self):
        data = """PPSSPP TACTICS OGRE NAVIGATION TRACE v1
ACTION 1 down
08801004 00000001 00000002
END_ACTION changed=1 logged=1
ACTION 2 down
08801004 00000002 00000003
END_ACTION changed=1 logged=1
ACTION 3 up
08801004 00000003 00000002
END_ACTION changed=1 logged=1
ACTION 4 up
08801004 00000002 00000001
END_ACTION changed=1 logged=1
"""
        actions = mod.parse_trace(data)
        self.assertEqual([a["direction"] for a in actions], ["down", "down", "up", "up"])
        results = mod.rank_candidates(actions)
        self.assertTrue(results)
        self.assertEqual(results[0][1], 0x08801004)
        self.assertEqual(results[0][0][0], 1.0)

    def test_truncated_and_malformed_lines(self):
        data = "ACTION 1 left\nnot memory\nEND_ACTION changed=0 logged=0\n"
        self.assertEqual(mod.parse_trace(data)[0]["changes"], {})
        self.assertEqual(mod.rank_candidates(mod.parse_trace(data)), [])


if __name__ == "__main__":
    unittest.main()
