"""Static callback discovery with native execution; no commercial ROM required."""
import json
import subprocess
from genesis_recompiler.cli import main
from genesis_recompiler.decode import analyze
from genesis_recompiler.emit import emit
from support import CompiledTestCase


def callback_rom(store='21fc 00000300 8010', load='2079 00e08010', call='4e90'):
    rom = bytearray(0x400)
    rom[:8] = bytes.fromhex('00ffff00 00000200')
    raw = bytes.fromhex(store + ' ' + load + ' ' + call + ' 4e72 2700')
    rom[0x200:0x200+len(raw)] = raw
    rom[0x300:0x304] = bytes.fromhex('7455 4e75')
    rom[0x320:0x324] = bytes.fromhex('7466 4e75')
    return bytes(rom), 0x200 + len(bytes.fromhex(store + ' ' + load))


class RamCallbackTests(CompiledTestCase):
    def test_absolute_short_store_and_ram_mirror_call_execute(self):
        rom, call = callback_rom()
        program = analyze(rom, [0x200])
        self.assertEqual(program.errors, {})
        self.assertEqual(program.ram_callbacks[call],
                         {'slot': 0xff8010, 'stores': [0x200], 'targets': [0x300]})
        # Other writes may still supply unknown values; this is not exhaustive.
        self.assertIn(call, program.indirect)
        result = subprocess.run([str(self.compile(emit(program)))], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('D2=00000055', result.stdout)
        self.assertIn('A7=00ffff00', result.stdout)

    def test_lea_constant_and_data_register_copy_across_conditional_branch(self):
        rom, call = callback_rom(store='41fa 00fe 21c8 8010',
                                 load='2038 8010 6708 42b8 8010 2240', call='4e91')
        program = analyze(rom, [0x200])
        self.assertEqual(program.errors, {})
        self.assertEqual(program.ram_callbacks[call]['targets'], [0x300])
        result = subprocess.run([str(self.compile(emit(program)))], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('D2=00000055', result.stdout)

    def test_newly_reachable_store_adds_another_target_and_json_metadata(self):
        rom, call = callback_rom()
        rom = bytearray(rom)
        rom[0x300:0x30a] = bytes.fromhex('21fc 00000320 8010 4e75')
        program = analyze(bytes(rom), [0x200])
        self.assertEqual(program.errors, {})
        self.assertEqual(program.ram_callbacks[call]['targets'], [0x300, 0x320])
        self.assertEqual(program.ram_callbacks[call]['stores'], [0x200, 0x300])
        self.assertIn(0x320, program.instructions)
        source, report, input_file = self.root/'game.c', self.root/'report.json', self.root/'game.bin'
        input_file.write_bytes(rom)
        self.assertEqual(main([str(input_file), '-o', str(source), '--report', str(report)]), 0)
        self.assertEqual(json.loads(report.read_text())['ram_callbacks'],
                         [{'pc': call, **program.ram_callbacks[call]}])

    def test_invalid_constants_slots_and_unreachable_stores_are_not_roots(self):
        for target in (0, 0x301, 0x400, 0xff0000):
            rom, _ = callback_rom(store=f'21fc {target:08x} 8010')
            self.assertEqual(analyze(rom, [0x200]).ram_callbacks, {})
        for store, load in [('21fc 00000300 8011', '2078 8011'),
                            ('23fc 00000300 00a10000', '2079 00a10000'),
                            ('31fc 0300 8010', '2078 8010'),
                            ('21fc 00000300 8010', '2078 8014')]:
            rom, _ = callback_rom(store=store, load=load)
            self.assertEqual(analyze(rom, [0x200]).ram_callbacks, {})
        rom, _ = callback_rom()
        self.assertEqual(analyze(rom, [0x208]).ram_callbacks, {})

    def test_clobbered_registers_calls_and_autoincrement_stop_the_slice(self):
        for load in ('2078 8010 307c 0000',  # MOVEA.W replaces the pointer.
                     '2078 8010 5288',       # ADDQ changes it.
                     '2078 8010 4e71 1018',  # (A0)+ changes it.
                     '2078 8010 c148',       # EXG changes it.
                     '2078 8010 48d0 0001',  # MOVEM is not inferred.
                     '2078 8010 4eb9 00000320'):
            rom, _ = callback_rom(load=load)
            self.assertEqual(analyze(rom, [0x200]).ram_callbacks, {})

    def test_long_immediate_register_store_and_24_bit_function_address(self):
        rom, call = callback_rom(store='223c ff000300 21c1 8010')
        program = analyze(rom, [0x200])
        self.assertEqual(program.ram_callbacks[call]['targets'], [0x300])


class IllegalInstructionTests(CompiledTestCase):
    def test_illegal_is_a_terminal_fault_and_does_not_decode_following_data(self):
        rom, _ = callback_rom(store='4afc ffff')
        program = analyze(rom, [0x200])
        self.assertEqual(program.errors, {})
        self.assertEqual(set(program.instructions), {0x200})
        self.assertEqual(program.instructions[0x200].op, 'ILLEGAL')
        result = subprocess.run([str(self.compile(emit(program)))], capture_output=True, text=True)
        self.assertEqual(result.returncode, 1)
        self.assertIn('fault at 000200: 68000 ILLEGAL instruction', result.stderr)
        self.assertIn('status=fault steps=1 pc=000200', result.stdout)

    def test_conditional_assertion_keeps_the_valid_branch_reachable(self):
        rom, _ = callback_rom(store='7000 6702 4afc')
        program = analyze(rom, [0x200])
        self.assertIn(0x206, program.instructions)
        self.assertIn(0x204, program.instructions)
