"""Automatic uploads execute real game copies and retain strict RAM guards."""
import json
from pathlib import Path
import subprocess
import unittest
from genesis_recompiler.cli import main
from genesis_recompiler.decode import RamCodeCopy, analyze
from genesis_recompiler.emit import emit
from genesis_recompiler.resources import plan_resources, write_resources
from support import CompiledTestCase
from test_m68k_ram import ram_code_rom, mutable_address_rom


class RamDiscoveryTests(CompiledTestCase):
    def run_program(self, program):
        return subprocess.run([str(self.compile(emit(program)))], capture_output=True, text=True)

    def test_counted_upload_executes_without_copy_annotations(self):
        for destination in (0xff8100, 0xe08100):
            rom, expected = ram_code_rom(destination)
            if destination != 0xff8100:
                # The uploader writes through FF; execution uses the E0 alias.
                self.assertEqual(int.from_bytes(rom[0x208:0x20c], 'big'), 0xff8100)
            program = analyze(rom, [0x200])
            self.assertEqual(program.errors, {})
            self.assertEqual(program.ram_copies, (expected,))
            self.assertEqual(program.ram_uploads[0]['status'], 'translated')
            result = self.run_program(program)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn('D0=00000007', result.stdout)
            self.assertIn('D2=deadcafe', result.stdout)

    def test_unrolled_upload_discovers_a_live_absolute_source_field(self):
        rom, expected = mutable_address_rom()
        program = analyze(rom, [0x200])
        self.assertEqual(program.errors, {})
        self.assertEqual(program.ram_copies, (expected,))
        self.assertEqual(program.auto_mutable_addresses, (0xff8100,))
        result = self.run_program(program)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('D0=0000cafe', result.stdout)
        self.assertIn('D1=0000beef', result.stdout)

    def test_automatic_source_field_never_relaxes_opcode_or_bus_checks(self):
        for address, patch, reason in ((0xff8200, '31fc 3239 8100', 'RAM instruction bytes'),
                                      (0xff8201, '', 'address error'),
                                      (0x400000, '', 'unmapped read')):
            rom, _ = mutable_address_rom(address, patch)
            result = self.run_program(analyze(rom, [0x200]))
            self.assertEqual(result.returncode, 1)
            self.assertIn(reason, result.stderr)

    def test_explicit_copy_keeps_full_source_guard_without_mutable_annotation(self):
        rom, copy = mutable_address_rom()
        program = analyze(rom, [0x200], [copy])
        self.assertEqual(program.auto_mutable_addresses, ())
        self.assertEqual(program.mutable_addresses, ())
        result = self.run_program(program)
        self.assertEqual(result.returncode, 1)
        self.assertIn('RAM instruction bytes', result.stderr)

    def test_data_upload_and_missing_upload_are_not_executable_images(self):
        rom, _ = ram_code_rom(upload=False)
        program = analyze(rom, [0x200])
        self.assertEqual(program.ram_copies, ())
        result = self.run_program(program)
        self.assertEqual(result.returncode, 1)
        self.assertIn('no translated instruction', result.stderr)
        rom, _ = ram_code_rom()
        # Keep the upload but replace the only execution reference with STOP.
        changed = bytearray(rom)
        changed[0x214:0x21a] = bytes.fromhex('4e72 2700 4e71')
        self.assertEqual(analyze(bytes(changed), [0x200]).ram_copies, ())

    def test_modified_uploaded_operand_faults_before_cpu_effects(self):
        rom, _ = ram_code_rom(patch='31fc 0008 8102')
        result = self.run_program(analyze(rom, [0x200]))
        self.assertEqual(result.returncode, 1)
        self.assertIn('RAM instruction bytes', result.stderr)
        self.assertIn('D0=00000000', result.stdout)

    def test_incomplete_or_unknown_copy_setup_is_not_guessed(self):
        rom, _ = ram_code_rom()
        for pc, data in ((0x20c, '3238 8000'),   # Unknown counter replaces MOVEQ.
                         (0x210, '6600'),        # DBF is no longer a copy loop.
                         (0x206, '43f900c00000')):  # VDP is not work RAM.
            changed = bytearray(rom)
            changed[pc:pc+len(bytes.fromhex(data))] = bytes.fromhex(data)
            self.assertEqual(analyze(bytes(changed), [0x200]).ram_copies, ())

    def test_unknown_source_instruction_rejects_upload_without_retry_loop(self):
        rom, _ = ram_code_rom()
        changed = bytearray(rom)
        changed[0x300:0x302] = bytes.fromhex('4e70')
        program = analyze(bytes(changed), [0x200])
        self.assertIn(0xff8100, program.errors)
        self.assertEqual(program.ram_copies, ())
        self.assertEqual(program.ram_uploads[0]['status'], 'invalid')

    def test_two_callers_preserve_source_destination_and_count_correlation(self):
        rom = bytearray(0x500)
        rom[:8] = bytes.fromhex('00ffff00 00000200')
        code = ('41f9 00000300 43f9 00ff8100 7000 6100 0060 4eb9 00ff8100 '
                '3200 41f9 00000320 43f9 00ff8200 7000 6100 0046 4eb9 00ff8200 4e72 2700')
        raw = bytes.fromhex(code)
        rom[0x200:0x200+len(raw)] = raw
        # Both caller displacements above land at the same generic uploader.
        rom[0x270:0x278] = bytes.fromhex('22d8 51c8 fffc 4e75')
        rom[0x300:0x304] = bytes.fromhex('7001 4e75')
        rom[0x320:0x324] = bytes.fromhex('7002 4e75')
        program = analyze(bytes(rom), [0x200])
        self.assertEqual(program.errors, {})
        self.assertEqual(set(program.ram_copies), {RamCodeCopy(0x300, 0xff8100, 4), RamCodeCopy(0x320, 0xff8200, 4)})
        result = self.run_program(program)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('D0=00000002', result.stdout)
        self.assertIn('D1=00000001', result.stdout)

    def test_nested_uploader_calls_resolve_only_the_original_argument_chain(self):
        rom = bytearray(0x400)
        rom[:8] = bytes.fromhex('00ffff00 00000200')
        raw = bytes.fromhex('41f9 00000300 7001 6100 0036 4eb9 00ff8100 4e72 2700')
        rom[0x200:0x200+len(raw)] = raw
        rom[0x240:0x246] = bytes.fromhex('6100 003e 4e75')
        rom[0x280:0x28e] = bytes.fromhex('43f9 00ff8100 22d8 51c8 fffc 4e75')
        rom[0x300:0x308] = bytes.fromhex('7007 4e75 deadcafe')
        program = analyze(bytes(rom), [0x200])
        self.assertEqual(program.errors, {})
        self.assertEqual(program.ram_copies, (RamCodeCopy(0x300, 0xff8100, 8),))
        result = self.run_program(program)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('D0=00000007', result.stdout)

    def test_different_images_sharing_ram_are_translated_as_guarded_variants(self):
        rom, _ = ram_code_rom()
        changed = bytearray(rom)
        original = bytes.fromhex('41f9 00000320 43f9 00ff8100 7202 22d8 51c9 fffc 4eb9 00ff8100 4e72 2700')
        # Reachable second uploader exists even if execution would stop first.
        changed[0x214:0x214+len(original)] = original
        changed[0x320:0x32c] = bytes.fromhex('7009 4e75 4e71 4e71 4e71 4e71')
        program = analyze(bytes(changed), [0x200])
        self.assertEqual(len(program.ram_copies), 2)
        self.assertEqual({r['status'] for r in program.ram_uploads}, {'variant'})
        self.assertEqual(len(program.ram_variants[0xff8100]), 2)
        result = self.run_program(program)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('D0=00000009', result.stdout)

    def test_auto_copy_irq_vector_and_metadata_are_reported_by_cli(self):
        rom, _ = ram_code_rom()
        changed = bytearray(rom)
        changed[0x70:0x74] = (0xff8108).to_bytes(4, 'big')
        changed[0x308:0x30a] = bytes.fromhex('4e73')
        source, output, report = self.root/'rom.bin', self.root/'game.c', self.root/'game.json'
        source.write_bytes(changed)
        self.assertEqual(main([str(source), '-o', str(output), '--report', str(report)]), 0)
        metadata = json.loads(report.read_text())
        self.assertEqual(metadata['interrupt_targets'], {'4': 0xff8108})
        self.assertEqual(metadata['m68k_ram_uploads'][0]['status'], 'translated')
        self.assertTrue(any(i['pc'] == 0xff8108 and i['assembly'] == 'RTE' for i in metadata['instructions']))

    def test_external_resource_code_pool_retains_detected_upload_bytes(self):
        rom, _ = ram_code_rom()
        program = analyze(rom, [0x200])
        plan = plan_resources(program)
        self.assertTrue(any(a <= 0x300 and a+n >= 0x30c for a, _, n in plan.code_spans))
        directory = self.root/'resources';write_resources(plan, directory)
        source = emit(program, resources=plan)
        result = subprocess.run([str(self.compile(source)), '--resources-dir', str(directory)],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('D0=00000007', result.stdout)
