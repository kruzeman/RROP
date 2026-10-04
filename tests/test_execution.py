from pathlib import Path
import subprocess
import unittest
from genesis_recompiler.decode import analyze
from genesis_recompiler.emit import emit
from genesis_recompiler.cli import main
from examples.make_demo import make_demo
from support import CompiledTestCase, rom_with


class ExecutionTests(CompiledTestCase):
    def test_line_a_f_still_fault_when_executed(self):
        for raw, op in (('a123', 'LINE_A'), ('f000', 'LINE_F')):
            result=self.execute(rom_with(raw+' 4f55 5420 4f46'))
            self.assertEqual(result.returncode, 1)
            self.assertIn('fault at 000200: 68000 '+op, result.stderr)
            self.assertIn('exception not implemented', result.stderr)

    def test_demo_loop_subroutine_ram(self):
        result = self.execute(make_demo(), ["--peek", "0xff0000"])
        self.assertEqual(result.returncode, 0, result.stderr)
        for expected in ("steps=18", "D0=00000008", "D1=0000ffff", "A7=00ffff00", "mem[ff0000]=00000008"):
            self.assertIn(expected, result.stdout)

    def test_move_sizes_sign_extension_and_aliasing(self):
        # A0 RAM; MOVE.B (A0)+,(A0)+ must use the incremented destination.
        code = "207c 00ff0000 10bc 0080 10d8 223c 12345678 123c 00ff 347c 8000 4e72 2700"
        result = self.execute(rom_with(code), ["--peek", "0xff0000"])
        self.assertEqual(result.returncode, 0, result.stderr)
        for expected in ("A0=00ff0002", "D1=123456ff", "A2=ffff8000", "mem[ff0000]=80800000"):
            self.assertIn(expected, result.stdout)

    def test_arithmetic_flags_drive_branches(self):
        # 127+1 at byte size overflows signed range; BVS skips MOVEQ #0.
        code = "707f 0600 0001 6902 7000 4e72 2700"
        result = self.execute(rom_with(code))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("D0=00000080", result.stdout)
        # subtraction with borrow and BCS, then compare preserving X.
        code = "7000 0400 0001 6502 7000 0c00 00ff 6602 7207 4e72 2700"
        result = self.execute(rom_with(code))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("D0=000000ff", result.stdout)
        self.assertIn("D1=00000007", result.stdout)

    def test_pc_relative_and_indexed_memory(self):
        code = "41fa 001c 7202 3030 1000 343b 1012 4e72 2700"
        rom = bytearray(rom_with(code))
        rom[0x21E:0x222] = bytes.fromhex("0000abcd")
        result = self.execute(bytes(rom))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("D0=0000abcd", result.stdout)
        self.assertIn("D2=0000abcd", result.stdout)

    def test_a7_byte_postincrement(self):
        result = self.execute(rom_with("1efc 0042 101f 4e72 2700"))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("A7=00ffff04", result.stdout)

    def test_quick_address_math_preserves_flags(self):
        # MOVEQ sets Z. ADDQ.W A0 uses full width, leaves Z set.
        result = self.execute(rom_with("7000 207c 0000ffff 5248 6602 7207 4e72 2700"))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("A0=00010000", result.stdout)
        self.assertIn("D1=00000007", result.stdout)

    def test_dbcc_true_does_not_decrement(self):
        result = self.execute(rom_with("7002 50c8 fffe 4e72 2700"))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("D0=00000002", result.stdout)

    def test_unmapped_and_alignment_faults(self):
        for code, expected in [("3039 00ff0001 4e72 2700", "address error"), ("3039 00400000 4e72 2700", "unmapped read")]:
            with self.subTest(code=code):
                result = self.execute(rom_with(code))
                self.assertEqual(result.returncode, 1)
                self.assertIn(expected, result.stderr)

    def test_constant_indirect_target_is_discovered_automatically(self):
        rom = rom_with("207c 0000020a 4ed0 4e71 4e72 2700")
        result = self.execute(rom)
        self.assertEqual(result.returncode, 0, result.stderr)
        result = self.execute(rom, entries=[0x20A])
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_budget_stops_infinite_loop(self):
        result = self.execute(rom_with("60fe"), ["--limit", "9"])
        self.assertEqual(result.returncode, 2)
        self.assertIn("status=budget steps=9", result.stdout)

    def test_stop_privilege(self):
        result = self.execute(rom_with("4e72 0000 4e72 2700"))
        self.assertEqual(result.returncode, 0)
        # Execute a second STOP after the first cleared supervisor state.
        p = analyze(rom_with("4e72 0000 4e72 2700"), [0x200, 0x204])
        source = "#define GENESIS_NO_MAIN\n" + emit(p) + '''
int main(void) { CPU c={0}; c.rom=rom_data; c.pc=0x204; translated_step(&c); return !(c.fault && !c.halted); }
'''
        result = subprocess.run([str(self.compile(source))], capture_output=True)
        self.assertEqual(result.returncode, 0)

    def test_cli_errors_and_partial_translation(self):
        rom = self.root / "unsupported.bin"
        rom.write_bytes(rom_with("4e70"))
        output, report = self.root / "out.c", self.root / "report.json"
        self.assertEqual(main([str(rom), "-o", str(output), "--report", str(report)]), 1)
        self.assertFalse(output.exists())
        self.assertTrue(report.exists())
        self.assertEqual(main([str(rom), "-o", str(output), "--allow-partial"]), 0)
        result = subprocess.run([str(self.compile(output.read_text()))], capture_output=True)
        self.assertEqual(result.returncode, 1)
        original = rom.read_bytes()
        self.assertEqual(main([str(rom), "-o", str(rom)]), 1)
        self.assertEqual(rom.read_bytes(), original)

    def test_immediate_logic_and_unary_operations(self):
        # OR/AND/XOR byte operations preserve the upper register bytes.
        code = "203c 12345600 0000 00ff 0200 000f 0a00 0003 4a00 6702 7201 4200 6602 7402 4e72 2700"
        result = self.execute(rom_with(code))
        self.assertEqual(result.returncode, 0, result.stderr)
        for expected in ("D0=12345600", "D1=00000001", "D2=00000002"):
            self.assertIn(expected, result.stdout)

    def test_predecrement_and_absolute_jsr(self):
        code = "207c 00ff0004 213c 12345678 4eb9 00000218 4e72 2700 4e71 7009 4e75"
        result = self.execute(rom_with(code), ["--peek", "0xe00000"])
        self.assertEqual(result.returncode, 0, result.stderr)
        for expected in ("mem[e00000]=12345678", "D0=00000009", "A0=00ff0000", "A7=00ffff00"):
            self.assertIn(expected, result.stdout)

    def test_exhaustive_byte_arithmetic_and_comparison_conditions(self):
        # Independent mathematical oracle: signed range tests for V, unsigned
        # range tests for C; all 65,536 operand pairs, both add and subtract.
        harness = Path(__file__).with_name("runtime_checks.c").read_text()
        p = analyze(make_demo(), [0x200])
        exe = self.compile("#define GENESIS_NO_MAIN\n" + emit(p) + harness)
        result = subprocess.run([str(exe)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_register_arithmetic_and_logical_operations(self):
        result = self.execute(rom_with("7003 7204 d081 9240 c0bc 00000006 8081 b181 4e72 2700"))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("D0=0000ffff", result.stdout)
        self.assertIn("D1=00000002", result.stdout)

    def test_address_arithmetic_sign_extension(self):
        result = self.execute(rom_with("207c 12340000 d0fc ffff 2208 91c8 b1fc 00000000 40c7 4e72 2700"))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("A0=00000000", result.stdout)
        self.assertIn("D1=1233ffff", result.stdout)
        self.assertIn("D7=00002704", result.stdout)

    def test_movem_word_load_sign_extends_and_updates_base(self):
        code = "70ff 7207 207c 00ff0000 4890 0003 7000 7200 4c98 0103 4e72 2700"
        result = self.execute(rom_with(code), ["--peek", "0xff0000"])
        self.assertEqual(result.returncode, 0, result.stderr)
        for expected in ("D0=ffffffff", "D1=00000007", "A0=00ff0006", "mem[ff0000]=ffff0007"):
            self.assertIn(expected, result.stdout)

    def test_movem_predecrement_mask_and_original_base_value(self):
        code = "203c 11223344 207c 00ff0008 48e0 8080 2228 0004 4e72 2700"
        result = self.execute(rom_with(code), ["--peek", "0xff0000"])
        self.assertEqual(result.returncode, 0, result.stderr)
        for expected in ("D1=00ff0008", "A0=00ff0000", "mem[ff0000]=11223344"):
            self.assertIn(expected, result.stdout)

    def test_link_unlk_and_pea_restore_stack(self):
        code = "2c7c 00ff0100 4856 201f 4e56 fff8 4e5e 4e72 2700"
        result = self.execute(rom_with(code))
        self.assertEqual(result.returncode, 0, result.stderr)
        for expected in ("D0=00ff0100", "A6=00ff0100", "A7=00ffff00"):
            self.assertIn(expected, result.stdout)

    def test_bit_operations_and_condition_set(self):
        code = "7000 08c0 0020 0800 0000 56c1 0840 0000 08c0 0007 0880 0007 4e72 2700"
        result = self.execute(rom_with(code))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("D0=00000000", result.stdout)
        self.assertIn("D1=000000ff", result.stdout)

    def test_shifts_rotates_swap_extend_and_negation(self):
        code = "7080 4880 48c0 e280 4840 4680 4480 4e72 2700"
        result = self.execute(rom_with(code))
        self.assertEqual(result.returncode, 0, result.stderr)
        # -128 ASR.L #1 -> ffffffc0, SWAP -> ffc0ffff,
        # NOT -> 003f0000, NEG -> ffc10000.
        self.assertIn("D0=ffc10000", result.stdout)

    def test_signed_unsigned_multiply_and_divide(self):
        code = "70fd c1fc 0007 223c 00010000 c2fc 0003 243c fffffff3 85fc 0005 263c 00010000 86fc 0003 4e72 2700"
        result = self.execute(rom_with(code))
        self.assertEqual(result.returncode, 0, result.stderr)
        for expected in ("D0=ffffffeb", "D1=00000000", "D2=fffdfffe", "D3=00015555"):
            self.assertIn(expected, result.stdout)

    def test_compare_preserves_x_and_cmpm_advances_sources(self):
        code = "207c 00ff0000 227c 00ff0004 20bc 00000003 22bc 00000004 003c 0010 b388 40c7 4e72 2700"
        result = self.execute(rom_with(code))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("A0=00ff0004", result.stdout)
        self.assertIn("A1=00ff0008", result.stdout)
        self.assertIn("D7=00002710", result.stdout)

    def test_sr_stack_banks_rte_and_ccr(self):
        # Include all entries: RTE's target and a later privileged instruction
        # are not necessarily discovered from its control flow alone.
        p = analyze(rom_with("46fc 0000 4e73 44fc 0015 003c 0008 023c 001c 0a3c 0004 4e72 2700"), [0x200, 0x204, 0x206])
        self.assertEqual(p.errors, {})
        harness = '''
#include <assert.h>
int main(void) {
    CPU c={0}; c.rom=rom_data; c.rom_size=sizeof rom_data;
    c.sr=0x2700; c.a[7]=0xff0200; c.usp=0xff0400; c.pc=0x200;
    translated_step(&c);
    assert(!c.fault && c.sr==0 && c.a[7]==0xff0400 && c.ssp==0xff0200);
    c.sr=0x2700; c.a[7]=0xff0200; c.pc=0x204;
    write_mem(&c,c.a[7],2,0); write_mem(&c,c.a[7]+2,4,0x206);
    translated_step(&c);
    assert(c.pc==0x206 && c.a[7]==0xff0400 && c.ssp==0xff0206);
    for (unsigned i=0;i<4;++i) translated_step(&c);
    assert(!c.fault && c.sr==0x18);
    translated_step(&c); assert(c.fault); /* User-mode STOP is privileged. */
    return 0;
}
'''
        result = subprocess.run([str(self.compile("#define GENESIS_NO_MAIN\n" + emit(p) + harness))], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_genesis_io_controls_and_tmss_boot_accesses(self):
        # Same controller-control reads used at the selected game's reset entry.
        code = "4ab9 00a10008 40c7 1039 00a10001 13fc 0040 00a10009 13fc 0000 00a10003 1239 00a10003 23fc 53454741 00a14000 4e72 2700"
        result = self.execute(rom_with(code))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("D7=00002704", result.stdout)
        self.assertIn("D0=000000a1", result.stdout)
        self.assertIn("D1=00000033", result.stdout)

    def test_io_and_vdp_faults_are_distinct(self):
        result = self.execute(rom_with("13fc 0030 00a10013 4e72 2700"))
        self.assertEqual(result.returncode, 1)
        self.assertIn("active serial communication not implemented", result.stderr)
        result = self.execute(rom_with("3039 00c00010 4e72 2700"))
        self.assertEqual(result.returncode, 1)
        self.assertIn("write-only VDP/PSG port", result.stderr)

    def test_trace_shows_instruction_boundaries(self):
        result = self.execute(rom_with("7001 4e72 2700"), ["--trace"])
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("step=0 pc=000200", result.stderr)
        self.assertIn("step=1 pc=000202", result.stderr)

    def test_dispatch_across_translation_pages(self):
        rom = bytearray(0x2000)
        rom[:8] = bytes.fromhex("00ffff00 00000200")
        rom[0x200:0x206] = bytes.fromhex("4ef9 00001000")
        rom[0x1000:0x1006] = bytes.fromhex("7009 4e72 2700")
        result = self.execute(bytes(rom))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("D0=00000009", result.stdout)


if __name__ == "__main__": unittest.main()
