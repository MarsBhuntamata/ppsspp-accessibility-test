"""Synthetic regression tests for the PSP Tactics Ogre FILETABLE reader."""
import importlib.util
import struct
import unittest
from pathlib import Path

SCRIPT = Path(__file__).with_name("to_filetable_manifest.py")
SPEC = importlib.util.spec_from_file_location("to_filetable_manifest", SCRIPT)
mod = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(mod)


class FileTableTests(unittest.TestCase):
    @staticmethod
    def fixture():
        # 68 byte header, 24 byte directory, 8 byte batch, 4 byte file.
        data = bytearray(104)
        struct.pack_into("<HHHHII", data, 0, 0x1EF1, 0, 1, 4, 100, 104)
        data[16:25] = b"ULUS10565"
        data[32:41] = b"ULUS10565"
        struct.pack_into("<HBBIBBHHHII", data, 68,
                         0x0384, 0, 0, 0, 0, 0, 1, 0, 0xffff, 0, 0)
        struct.pack_into("<HHI", data, 92, 10, 1, (2 << 29))
        struct.pack_into("<HH", data, 100, 3, 25)
        return bytes(data)

    def test_decoding(self):
        result = mod.decode_table(self.fixture())
        self.assertEqual(result["title_id"], "ULUS10565")
        self.assertEqual(result["records"][0]["archive"], "0384.BIN")
        self.assertEqual(result["records"][0]["file_id"], 10)
        self.assertEqual(result["records"][0]["offset"], 0x1800)
        self.assertEqual(result["records"][0]["size"], 25)

    def test_bad_signature(self):
        data = bytearray(self.fixture())
        data[0] = 0
        with self.assertRaises(ValueError):
            mod.decode_table(data)

    def test_truncated_table(self):
        with self.assertRaises(ValueError):
            mod.decode_table(self.fixture()[:-5])


if __name__ == "__main__":
    unittest.main()
