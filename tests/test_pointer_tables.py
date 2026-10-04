import subprocess
from genesis_recompiler.decode import analyze
from genesis_recompiler.emit import emit
from support import CompiledTestCase


def pointer_table_rom(index=1, scale='d040 d040', setup=True, code=0x200, table=0x280):
    rom = bytearray(0x700)
    rom[:8] = (0xffff00).to_bytes(4,'big') + code.to_bytes(4,'big')
    raw = bytearray.fromhex(f'70{index:02x} 0c40 0003 6504 4e72 2700')
    if setup: raw += bytes.fromhex('21fc 00000300 8010 21fc 00000310 8014')
    shift = code + len(raw)
    raw += bytes.fromhex(scale)
    load = code + len(raw)
    displacement = table - (load + 2)
    assert -128 <= displacement <= 127
    raw += bytes.fromhex('247b 0000')
    raw[-1] = displacement & 255
    arguments = code + len(raw)
    raw += bytes.fromhex('41f8 8010 3038 8014')
    jump = code + len(raw)
    raw += bytes.fromhex('4ed2')
    rom[code:code+len(raw)] = raw
    for n in range(3):
        target = 0x300 + n*0x10
        rom[table+n*4:table+n*4+4] = target.to_bytes(4,'big')
        rom[target:target+6] = bytes.fromhex(f'74{0x50+n:02x} 4e72 2700')
    return bytes(rom), {'shift': shift, 'load': load, 'args': arguments, 'jump': jump}


class PointerTableTests(CompiledTestCase):
    def test_bounded_pointer_dispatch_executes_and_retains_argument_setup(self):
        for index in (0, 1, 2, 3):
            with self.subTest(index=index):
                rom, info = pointer_table_rom(index)
                program = analyze(rom, [0x200])
                self.assertEqual(program.errors, {})
                self.assertEqual(program.pointer_tables[info['jump']],
                                 {'table': 0x280, 'count': 3, 'targets': [0x300, 0x310, 0x320]})
                result = subprocess.run([str(self.compile(emit(program)))], capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn(f'D2={0x50+index if index<3 else 0:08x}', result.stdout)
                if index < 3:
                    self.assertIn('A0=ffff8010', result.stdout)
                    self.assertIn('D0=00000000', result.stdout)  # Changed after pointer lookup.

    def test_shift_form_and_backward_table(self):
        for scale in ('e540', 'e548'):
            rom, info = pointer_table_rom(scale=scale, setup=False, code=0x500, table=0x490)
            program = analyze(rom, [0x500])
            self.assertEqual(program.errors, {})
            self.assertEqual(program.pointer_tables[info['jump']]['table'], 0x490)

    def test_bcc_fallthrough_and_indirect_subroutine_preserve_the_stack(self):
        rom, _ = pointer_table_rom()
        rom = bytearray(rom)
        rom[0x200:0x21a] = bytes.fromhex('7001 0c40 0003 640e d040 d040 247b 0072 4e92 4e72 2700 4e72 2700')
        for n in range(3):
            rom[0x300+n*0x10:0x304+n*0x10] = bytes.fromhex(f'74{0x50+n:02x} 4e75')
        program = analyze(bytes(rom), [0x200])
        self.assertEqual(program.errors, {})
        self.assertEqual(program.pointer_tables[0x210]['targets'], [0x300, 0x310, 0x320])
        result = subprocess.run([str(self.compile(emit(program)))], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('D2=00000051', result.stdout)
        self.assertIn('A7=00ffff00', result.stdout)

    def test_newly_discovered_table_targets_can_expose_another_table(self):
        rom, first = pointer_table_rom()
        rom = bytearray(rom)
        second, info = pointer_table_rom(setup=False, code=0x500, table=0x494)
        rom[0x494:] = second[0x494:]
        rom[0x300:0x304] = bytes.fromhex('6000 01fe')
        program = analyze(bytes(rom), [0x200])
        self.assertEqual(program.errors, {})
        self.assertEqual(set(program.pointer_tables), {first['jump'], info['jump']})

    def test_wrong_scale_index_and_clobbered_pointer_are_rejected(self):
        rom, info = pointer_table_rom()
        for at, raw in [(info['shift'], '4e71 4e71'),
                        (info['shift'], 'd040 4e71'),
                        (info['shift'], 'd080 d080'),
                        (info['load']+2, '0800'),
                        (info['load']+2, '1000'),
                        (info['args'], '45f8'),
                        (0x206, '6604'),
                        (0x204, '0201')]:
            with self.subTest(at=at, raw=raw):
                changed = bytearray(rom)
                changed[at:at+len(bytes.fromhex(raw))] = bytes.fromhex(raw)
                self.assertEqual(analyze(bytes(changed), [0x200]).pointer_tables, {})

    def test_invalid_pointers_and_truncated_table_are_rejected(self):
        for target in (0, 0x301, 0xff0000, 0x700):
            rom, _ = pointer_table_rom()
            changed = bytearray(rom)
            changed[0x280:0x284] = target.to_bytes(4,'big')
            self.assertEqual(analyze(bytes(changed), [0x200]).pointer_tables, {})
        rom, _ = pointer_table_rom()
        self.assertEqual(analyze(rom[:0x28a], [0x200]).pointer_tables, {})
