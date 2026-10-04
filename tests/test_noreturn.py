"""Explicit analysis annotations for coroutine exits that unwind their caller."""
import json
import subprocess
from genesis_recompiler.cli import main
from genesis_recompiler.decode import analyze
from genesis_recompiler.emit import emit
from support import CompiledTestCase, rom_with


def coroutine_rom(call='6100 000e', exit_code='588f 4e75'):
    rom = bytearray(rom_with('6100 001e 4e72 2700'))
    raw = bytes.fromhex(call)
    rom[0x220:0x220+len(raw)] = raw
    rom[0x220+len(raw):0x230] = bytes.fromhex('4e70') * ((0x10-len(raw))//2)
    raw = bytes.fromhex(exit_code)
    rom[0x230:0x230+len(raw)] = raw
    return bytes(rom)


class NonreturnTests(CompiledTestCase):
    def test_jsr_and_bsr_preserve_real_stack_unwinding_without_decoding_inline_data(self):
        for call in ('6100 000e', '4eb9 00000230'):
            rom = coroutine_rom(call)
            self.assertTrue(analyze(rom, [0x200]).errors)
            program = analyze(rom, [0x200], noreturn=[0x230])
            self.assertEqual(program.errors, {})
            self.assertIn(0x230, program.instructions)
            self.assertNotIn(0x220+len(bytes.fromhex(call)), program.instructions)
            exe = self.compile(emit(program))
            result = subprocess.run([str(exe)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn('status=halted steps=5 pc=000208', result.stdout)
            self.assertIn('A7=00ffff00', result.stdout)

    def test_incorrect_annotation_still_faults_when_callee_really_returns(self):
        program = analyze(coroutine_rom(exit_code='4e75'), [0x200], noreturn=[0x230])
        self.assertEqual(program.errors, {})
        result = subprocess.run([str(self.compile(emit(program)))], capture_output=True, text=True)
        self.assertEqual(result.returncode, 1)
        self.assertIn('fault at 000224: PC has no translated instruction', result.stderr)

    def test_validation_and_cli_report(self):
        rom = coroutine_rom()
        for pc in (0, 0x231, len(rom), 0xc00004):
            with self.subTest(pc=pc), self.assertRaisesRegex(ValueError, 'nonreturning targets'):
                analyze(rom, [0x200], noreturn=[pc])
        source, output, report = self.root/'rom.bin', self.root/'game.c', self.root/'report.json'
        source.write_bytes(rom)
        self.assertEqual(main([str(source), '-o', str(output), '--noreturn', '0x230',
                               '--noreturn', '0x230', '--report', str(report)]), 0)
        self.assertEqual(json.loads(report.read_text())['noreturn_targets'], [0x230])
