"""Cross-platform unit tests for screenshot response and OCR text utilities."""
import base64
import importlib.util
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent / "to_speaking_probe.py"
SPEC = importlib.util.spec_from_file_location("to_speaking_probe", SCRIPT)
mod = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(mod)


class FramebufferTests(unittest.TestCase):
    def test_png_response(self):
        example = b"\x89PNG\r\n\x1a\n" + b"rest of image"
        response = {
            "event": "gpu.buffer.screenshot",
            "uri": "data:image/png;base64," + base64.b64encode(example).decode("ascii"),
        }
        self.assertEqual(mod.extract_screenshot(response), example)

    def test_reject_non_image(self):
        with self.assertRaises(ValueError):
            mod.extract_screenshot({"event": "gpu.buffer.screenshot", "uri": ""})

    def test_normalization(self):
        self.assertEqual(mod.clean_text("  Attack  \n\n   Items  "), "Attack\nItems")

    def test_line_diff(self):
        self.assertEqual(mod.new_lines("Gold\nAttack", "Gold\nItems"), "Items")


if __name__ == "__main__":
    unittest.main()
