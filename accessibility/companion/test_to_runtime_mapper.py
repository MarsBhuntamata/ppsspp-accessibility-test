"""Pure tests for the read-only decrypted ELF runtime mapper."""
import struct
import unittest
import to_runtime_mapper as m


class RuntimeMapperTests(unittest.TestCase):
    def test_locates_module_using_two_independent_signatures(self):
        base = 0x08804000
        region = base + 0x2A7000
        data = bytearray(0x1000)
        n = base + m.NAME_ELF - region
        b = base + m.BIRTHDAY_ELF - region
        data[n:n+len(m.NAME)] = m.NAME
        data[b:b+len(m.BIRTHDAY)] = m.BIRTHDAY
        self.assertEqual(m.find_load_base(region, bytes(data),
                         lambda addr, text: data[addr-region:addr-region+len(text)] == text),
                         base)

    def test_rejects_name_without_birthday(self):
        base = 0x08804000
        region = base + 0x2A7000
        data = bytearray(0x1000)
        off = base + m.NAME_ELF - region
        data[off:off+len(m.NAME)] = m.NAME
        self.assertIsNone(m.find_load_base(region, bytes(data),
                         lambda addr, text: data[addr-region:addr-region+len(text)] == text))

    def test_method_signature_allows_relocated_immediates(self):
        self.assertTrue(m.matches_relocated_method(m.METHOD_PREFIX))
        words = [struct.unpack_from("<I", m.METHOD_PREFIX, i)[0] for i in (0,4,8)]
        relocated = struct.pack("<III", (words[0]&0xffff0000)|0x888,
            (words[1]&0xffff0000)|0x1234, (words[2]&0xfc000000)|0x654321)
        self.assertTrue(m.matches_relocated_method(relocated))
        self.assertFalse(m.matches_relocated_method(b"\x00"*12))

    def test_find_word_references_requires_alignment(self):
        target = 0x08AAD830
        data = bytearray(36)
        struct.pack_into("<I", data, 8, target)
        struct.pack_into("<I", data, 20, target)
        self.assertEqual(m.find_aligned_words(0x09000000, data, {target}),
                         [(0x09000008, target), (0x09000014, target)])


if __name__ == "__main__":
    unittest.main()
