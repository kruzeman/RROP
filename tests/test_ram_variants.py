"""Different uploaded MC68000 images dispatch only precompiled operations."""
import contextlib
import io
import json
import subprocess
from genesis_recompiler.cli import main
from genesis_recompiler.decode import RamCodeCopy, analyze
from genesis_recompiler.emit import emit
from genesis_recompiler.resources import plan_resources, write_resources
from support import CompiledTestCase


class UploadRom:
    def __init__(self):
        self.rom = bytearray(0x1000)
        self.rom[:8] = bytes.fromhex('00ffff00 00000200')
        self.code = bytearray()

    def add(self, text):
        self.code.extend(bytes.fromhex(text))

    def image(self, source, text):
        raw = bytes.fromhex(text)
        self.rom[source:source+len(raw)] = raw
        return len(raw)

    def upload(self, source, destination, size):
        self.add(f'41f9 {source:08x} 43f9 {destination:08x} '
                 f'3e3c {size//2-1:04x} 32d8 51cf fffc')

    def call(self, destination=0xff8100):
        self.add(f'4eb9 {destination:08x}')

    def finish(self):
        self.add('4e72 2700')
        self.rom[0x200:0x200+len(self.code)] = self.code
        return bytes(self.rom)


class RamVariantTests(CompiledTestCase):
    def execute(self, program, *args):
        return subprocess.run([str(self.compile(emit(program))), *args], capture_output=True, text=True)

    def pair(self, first='7001 4e75', second='7002 4e75', destination=0xff8100):
        fixture = UploadRom()
        n = fixture.image(0x600, first)
        m = fixture.image(0x680, second)
        fixture.upload(0x600, destination, n)
        fixture.call(destination)
        fixture.add('2200')  # Preserve first result in D1.
        fixture.upload(0x680, destination, m)
        fixture.call(destination)
        return fixture

    def test_same_pc_selects_each_real_upload_and_can_return_to_the_first(self):
        fixture = self.pair()
        fixture.add('2600')
        fixture.upload(0x600, 0xff8100, 4)
        fixture.call()
        program = analyze(fixture.finish(), [0x200])
        self.assertEqual(program.errors, {})
        self.assertEqual(program.ram_variant_errors, [])
        self.assertEqual(len(program.ram_variants[0xff8100]), 2)
        self.assertEqual(len(program.ram_variants[0xff8102]), 1)  # Shared RTS.
        self.assertEqual(program.instruction_count, len(program.instructions)+1)
        result = self.execute(program)
        self.assertEqual(result.returncode, 0, result.stderr)
        for value in ('D0=00000001', 'D1=00000001', 'D3=00000002', 'A7=00ffff00'):
            self.assertIn(value, result.stdout)

    def test_different_instruction_lengths_keep_independent_boundaries(self):
        program = analyze(self.pair(second='303c beef 4e75').finish(), [0x200])
        self.assertEqual(program.ram_variant_errors, [])
        self.assertEqual({len(v.instruction.raw) for v in program.ram_variants[0xff8100]}, {2, 4})
        self.assertEqual(program.ram_variants[0xff8104][0].instruction.op, 'RTS')
        result = self.execute(program)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('D0=0000beef', result.stdout)
        self.assertIn('D1=00000001', result.stdout)

    def test_pc_relative_code_uses_its_ram_execution_address_and_live_data(self):
        fixture = self.pair(first='41fa 0006 7001 4e75 deadcafe',
                            second='41fa 0006 7002 4e75 beefcafe', destination=0xe08100)
        fixture.add('2410')
        program = analyze(fixture.finish(), [0x200])
        result = self.execute(program)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('D2=beefcafe', result.stdout)
        self.assertIn('A0=00e08108', result.stdout)

    def test_partially_overlapping_images_can_have_different_ops_at_one_pc(self):
        fixture = UploadRom()
        fixture.image(0x600, '7001 4e75')
        fixture.image(0x680, '7002 4e75')
        fixture.upload(0x600, 0xff8100, 4)
        fixture.call()
        fixture.add('2200')
        fixture.upload(0x680, 0xff8102, 4)
        fixture.call(0xff8102)
        program = analyze(fixture.finish(), [0x200])
        self.assertEqual({v.instruction.op for v in program.ram_variants[0xff8102]}, {'MOVEQ', 'RTS'})
        result = self.execute(program)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('D0=00000002', result.stdout)

    def test_later_discovery_adds_a_variant_at_an_already_translated_pc(self):
        fixture = UploadRom()
        fixture.image(0x600, '4ef9 00000300')
        fixture.image(0x680, '7002 4e75')
        fixture.upload(0x600, 0xff8100, 6)
        fixture.call()
        fixture.add('4e72 2700')
        initial = fixture.code[:]
        fixture.code.clear()
        fixture.upload(0x680, 0xff8100, 4)
        fixture.call()
        fixture.add('4e75')
        fixture.rom[0x300:0x300+len(fixture.code)] = fixture.code
        fixture.code = initial
        program = analyze(fixture.finish(), [0x200])
        self.assertEqual(len(program.ram_variants[0xff8100]), 2)
        result = self.execute(program)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('D0=00000002', result.stdout)

    def test_unknown_opcode_variant_faults_before_register_or_stack_effects(self):
        fixture = self.pair()
        fixture.add('31fc 7003 8100')
        fixture.call()
        program = analyze(fixture.finish(), [0x200])
        result = self.execute(program)
        self.assertEqual(result.returncode, 1)
        self.assertIn('RAM instruction bytes', result.stderr)
        self.assertIn('D0=00000002', result.stdout)
        self.assertIn('A7=00fffefc', result.stdout)  # JSR ran; faulted instruction did not.

    def test_unknown_immediate_does_not_match_a_known_longer_variant(self):
        fixture = self.pair(second='303c beef 4e75')
        fixture.add('31fc babe 8102')
        fixture.call()
        result = self.execute(analyze(fixture.finish(), [0x200]))
        self.assertEqual(result.returncode, 1)
        self.assertIn('RAM instruction bytes', result.stderr)
        self.assertIn('D0=0000beef', result.stdout)

    def test_live_lea_source_is_inferred_and_destination_register_stays_guarded(self):
        for patch, success in (('', True), ('31fc 43f9 8100', False)):
            fixture = self.pair(second='41f9 00ff8200 4e75')
            fixture.add('23fc 00ff8300 00ff8102 ' + patch)
            fixture.call()
            program = analyze(fixture.finish(), [0x200])
            self.assertIn(0xff8100, program.auto_mutable_addresses)
            self.assertEqual({v.instruction.op: v.mutable_address for v in program.ram_variants[0xff8100]},
                             {'MOVEQ': False, 'LEA': True})
            result = self.execute(program)
            self.assertEqual(result.returncode, 0 if success else 1, result.stderr)
            if success:
                self.assertIn('A0=00ff8300', result.stdout)
            else:
                self.assertIn('RAM instruction bytes', result.stderr)

    def test_explicit_images_keep_guards_and_accept_an_explicit_lea_annotation(self):
        fixture = UploadRom()
        fixture.image(0x600, '41f9 00ff8200 4e75')
        fixture.upload(0x600, 0xff8100, 8)
        fixture.add('23fc 00ff8300 00ff8102')
        fixture.call()
        rom = fixture.finish()
        image = RamCodeCopy(0x600, 0xff8100, 8)
        for annotations, success in (((), False), ((0xff8100,), True)):
            program = analyze(rom, [0x200], [image], mutable_addresses=annotations)
            self.assertEqual(program.auto_mutable_addresses, ())
            result = self.execute(program)
            self.assertEqual(result.returncode, 0 if success else 1, result.stderr)

    def test_explicit_image_does_not_hide_a_different_automatic_upload(self):
        rom = self.pair().finish()
        program = analyze(rom, [0x200], [RamCodeCopy(0x600, 0xff8100, 4)])
        self.assertEqual(len(program.ram_variants[0xff8100]), 2)
        self.assertEqual({r['status'] for r in program.ram_uploads}, {'declared', 'variant'})
        result = self.execute(program)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_invalid_upload_does_not_poison_a_known_image(self):
        fixture = UploadRom()
        fixture.image(0x600, '4e70 4e75')
        fixture.image(0x680, '7002 4e75')
        fixture.upload(0x600, 0xff8100, 4)
        fixture.upload(0x680, 0xff8100, 4)
        fixture.call()
        program = analyze(fixture.finish(), [0x200])
        self.assertEqual(program.errors, {})
        self.assertEqual(len(program.ram_copies), 1)
        self.assertIn('invalid', {r['status'] for r in program.ram_uploads})
        result = self.execute(program)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_variant_decode_error_is_retained_even_if_another_image_covers_pc(self):
        rom = self.pair(first='7001 4e70', second='7002 4e75').finish()
        program = analyze(rom, [0x200])
        self.assertEqual(program.errors, {})
        self.assertEqual(program.ram_variant_errors[0]['pc'], 0xff8102)
        source, output, report = self.root/'rom.bin', self.root/'game.c', self.root/'report.json'
        source.write_bytes(rom)
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(main([str(source), '-o', str(output), '--report', str(report)]), 1)
        data = json.loads(report.read_text())
        self.assertTrue(data['m68k_ram_variant_errors'])
        self.assertEqual(len([v for v in data['m68k_ram_variants'] if v['pc']==0xff8100]), 2)
        self.assertFalse(output.exists())

    def test_external_resources_preserve_all_variant_sources_and_switch_correctly(self):
        program = analyze(self.pair(second='303c beef 4e75').finish(), [0x200])
        plan = plan_resources(program)
        for start, end in ((0x600, 0x604), (0x680, 0x686)):
            self.assertTrue(any(a<=start and end<=a+n for a, _, n in plan.code_spans))
        directory = self.root/'resources'
        write_resources(plan, directory)
        result = subprocess.run([str(self.compile(emit(program, resources=plan))),
                                 '--resources-dir', str(directory)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('D0=0000beef', result.stdout)

    def test_last_two_ram_instructions_never_read_beyond_the_guard_window(self):
        program = analyze(self.pair(destination=0xfffffc).finish(), [0x200])
        result = self.execute(program)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('D0=00000002', result.stdout)

    def test_ambiguous_pointer_set_cannot_promote_its_plausible_ram_subset(self):
        fixture = UploadRom()
        fixture.image(0x600, '7001 4e75')
        fixture.upload(0x600, 0xff8100, 4)
        fixture.add('7000 1038 8200 e548 41f9 00000700 2070 0000 4e90')
        fixture.rom[0x700:0x704] = bytes.fromhex('00ff8100')
        program = analyze(fixture.finish(), [0x200])
        self.assertEqual(program.ram_copies, ())
        self.assertEqual(program.ram_variants, {})
