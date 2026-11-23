"""Unit tests for focused character-creation / gameplay cursor probing."""
import importlib.util
from pathlib import Path
import sys
import unittest

root = Path(__file__).parent
sys.path.insert(0, str(root))
spec = importlib.util.spec_from_file_location("to_gameplay_cursor", root / "to_gameplay_cursor.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class TestGameplayCursor(unittest.TestCase):
    def test_inverse_pair(self):
        self.assertTrue(module.inverse_pair("down", "up"))
        self.assertTrue(module.inverse_pair("left", "right"))
        self.assertFalse(module.inverse_pair("down", "down"))
        self.assertFalse(module.inverse_pair("up", "right"))

    def test_return_candidate(self):
        base = module.WATCH_PAGES[0]
        old = {base: b"\x00\x04"}
        mid = {base: b"\x01\x04"}
        end = {base: b"\x00\x04"}
        pages = module.WATCH_PAGES
        module.WATCH_PAGES = (base,)
        try:
            self.assertEqual(module.inverse_returns(old, mid, end, "down", "up"),
                             ((base, 0, 1),))
            self.assertEqual(module.inverse_returns(old, mid, end, "down", "down"), ())
        finally:
            module.WATCH_PAGES = pages

    def test_confidence_threshold(self):
        self.assertEqual(module.confident_candidates({1: 1, 2: 2, 3: 4}),
                         [(4, 3), (2, 2)])

    def test_seven_small_memory_reads(self):
        import base64
        class FakeConnection:
            def __init__(self):
                self.requests = []
            def request(self, event, **kwargs):
                self.requests.append((event, kwargs))
                data = bytearray(module.PAGE_BYTES)
                return {"base64": base64.b64encode(data).decode("ascii")}
        conn = FakeConnection()
        pages = module.read_pages(conn)
        self.assertEqual(set(pages), set(module.WATCH_PAGES))
        self.assertEqual(len(conn.requests), 7)
        self.assertEqual({kw["size"] for _, kw in conn.requests}, {4096})


if __name__ == "__main__":
    unittest.main()
