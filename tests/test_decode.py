import unittest
from genesis_recompiler.decode import Decoder, DecodeError, analyze


def decode(hex_bytes, pc=0):
    return Decoder(bytes(pc) + bytes.fromhex(hex_bytes), pc).decode()


class DecoderTests(unittest.TestCase):
    def test_line_a_f_exceptions_terminate_before_inline_assertion_data(self):
        for raw, op in (('a123', 'LINE_A'), ('f000', 'LINE_F')):
            p=analyze(bytes.fromhex(raw+' 4f55 5420 4f46'), [0])
            self.assertEqual(p.errors, {})
            self.assertEqual(list(p.instructions), [0])
            self.assertEqual(p.instructions[0].op, op)

    def test_moveq_sign_extension(self):
        i = decode("76ff")
        self.assertEqual((i.op, i.dst.reg, i.value), ("MOVEQ", 3, -1))

    def test_branch_byte_and_word_base(self):
        self.assertEqual(decode("60fe", 0x200).target, 0x200)
        self.assertEqual(decode("6000 fffc", 0x200).target, 0x1FE)
        # $ff is an 8-bit -1 on original 68000, not a 68020 long branch.
        self.assertEqual(decode("60ff", 0x200).end, 0x202)

    def test_pc_relative_uses_extension_address(self):
        self.assertEqual(decode("41fa 0010", 0x200).src.value, 0x212)
        self.assertEqual(decode("23fa 0010 00ff 0000", 0x200).src.value, 0x212)

    def test_indexed_and_absolute_short(self):
        i = decode("2030 18fe")
        self.assertEqual((i.src.mode, i.src.value, i.src.index), (6, -2, 0x18FE))
        self.assertEqual(decode("4ef8 ff00").target, 0xFFFF00)
        with self.assertRaises(DecodeError): decode("2030 1afe")

    def test_dbcc_base(self):
        i = decode("51c9 fffc", 0x200)
        self.assertEqual((i.op, i.condition, i.target), ("DBCC", 1, 0x1FE))

    def test_source_extensions_precede_destination_extensions(self):
        i = decode("23fc 1234 5678 00ff 0010")
        self.assertEqual(i.src.value, 0x12345678)
        self.assertEqual(i.dst.value, 0xFF0010)
        self.assertEqual(i.end, 10)

    def test_invalid_encodings_and_truncation(self):
        for code in ("1008", "1040", "4ec0", "4e80", "5008", "203c 0000"):
            with self.subTest(code=code), self.assertRaises(DecodeError): decode(code)
        with self.assertRaises(DecodeError): Decoder(b"\x00\x4e\x71", 1).decode()

    def test_reachable_analysis_skips_data_and_detects_overlap(self):
        p = analyze(bytes.fromhex("6002 ffff 4e72 2700"), [0])
        self.assertEqual(set(p.instructions), {0, 4})
        self.assertEqual(p.errors, {})
        p = analyze(bytes.fromhex("203c 0000 0000 4e72 2700"), [0, 2])
        self.assertIn("overlaps", p.errors[2])

    def test_indirect_transfer_is_recorded(self):
        p = analyze(bytes.fromhex("4ed0"), [0])
        self.assertEqual(p.indirect, [0])

    def test_movem_mask_precedes_address_extension(self):
        i = decode("48f9 0101 00ff 0000")
        self.assertEqual((i.op, i.size, i.value, i.dst.value, i.end), ("MOVEM_STORE", 4, 0x0101, 0xFF0000, 8))
        i = decode("4c9d 01ff")
        self.assertEqual((i.op, i.size, i.src.mode, i.src.reg), ("MOVEM_LOAD", 2, 3, 5))
        for code in ("4898 0001", "4ca0 0001", "48fa 0001 0002"):
            with self.subTest(code=code), self.assertRaises(DecodeError): decode(code)

    def test_muls_divs_always_read_word_source(self):
        for code, op in (("c1fc 8000", "MULS"), ("81fc ffff", "DIVS")):
            i = decode(code)
            self.assertEqual((i.op, i.size, i.end), (op, 2, 4))

    def test_sr_ccr_and_quick_encodings(self):
        self.assertEqual(decode("46fc 2700").op, "TO_SR")
        self.assertEqual(decode("003c 0010").op, "CCR_OR")
        self.assertEqual(decode("91c8").op, "SUBA")
        self.assertEqual(decode("d180").op, "ADDX")
        self.assertEqual(decode("c148").op, "EXG")
        self.assertEqual(decode("4850").op, "PEA")

    def test_shift_counts_and_bit_operand_sizes(self):
        self.assertEqual(decode("e148").src.value, 8)
        self.assertEqual(decode("e3d0").op, "LSL")
        self.assertEqual(decode("0800 0020").size, 4)
        self.assertEqual(decode("0810 0020").size, 1)
        with self.assertRaises(DecodeError): decode("ebd0")


if __name__ == "__main__": unittest.main()
