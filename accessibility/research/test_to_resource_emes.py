"""Synthetic test of resource-ID-to-EMES mapping. No game data required."""
import importlib.util
import json
import struct
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location("to_resource_emes", ROOT / "to_resource_emes.py")
mod = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(mod)


class ResourceMessageTests(unittest.TestCase):
    def test_mapping_and_bounds(self):
        # 2-entry EMES: first message at +20 (two bytes), second at +22.
        data = bytearray(48)
        data[0:4] = b"EMES"
        struct.pack_into("<H", data, 4, 2)
        struct.pack_into("<2H", data, 8, 9, 10)
        struct.pack_into("<2I", data, 12, 20, 22)
        data[20:22] = b"Hi"
        data[22:34] = b"hello world!"
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder)
            (base / "0384.BIN").write_bytes(bytes(data))
            index = {"records": [{
                "archive": "0384.BIN", "directory_id": 900,
                "file_id": 10, "offset": 0, "size": 48,
                "encrypted": False, "install": False,
            }]}
            rows, counts = mod.map_resources(index, base)
            self.assertEqual(counts[("0384.BIN", 10)], 1)
            self.assertEqual([row["message_id"] for row in rows], [9, 10])
            self.assertEqual(rows[0]["message_offset_in_archive"], 20)
            index["records"][0]["size"] = 49
            with self.assertRaises(ValueError):
                mod.map_resources(index, base)


if __name__ == "__main__":
    unittest.main()
