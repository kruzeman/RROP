"""Resolved object fields add ROM roots without conflating unrelated objects."""
import subprocess
from genesis_recompiler.decode import analyze
from genesis_recompiler.emit import emit
from support import CompiledTestCase
from test_ram_variants import UploadRom


class MemoryCallbackTests(CompiledTestCase):
    def run_fixture(self, fixture):
        program = analyze(fixture.finish(), [0x200])
        result = subprocess.run([str(self.compile(emit(program)))], capture_output=True, text=True)
        return program, result

    def test_object_relative_store_matches_the_resolved_load_slot(self):
        fixture = UploadRom()
        fixture.image(0x600, '7007 4e75')
        fixture.add('41f9 00ff8100 217c 00000600 000c 2268 000c 4e91')
        program, result = self.run_fixture(fixture)
        self.assertEqual(program.errors, {})
        callback = next(iter(program.memory_callbacks.values()))
        self.assertEqual(callback['slots'], [0xff810c])
        self.assertEqual(callback['targets'], [0x600])
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('D0=00000007', result.stdout)

    def test_another_object_with_the_same_field_offset_is_not_a_match(self):
        fixture = UploadRom()
        fixture.image(0x600, '7007 4e75')
        fixture.image(0x620, '7009 4e75')
        fixture.add('41f9 00ff8100 217c 00000600 000c '
                    '45f9 00ff8200 257c 00000620 000c 2268 000c 4e91')
        program, result = self.run_fixture(fixture)
        self.assertEqual(next(iter(program.memory_callbacks.values()))['targets'], [0x600])
        self.assertNotIn(0x620, program.instructions)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_ram_mirror_addresses_match_one_physical_slot(self):
        fixture = UploadRom()
        fixture.image(0x600, '7007 4e75')
        fixture.add('41f9 00e08100 217c 00000600 000c '
                    '41f9 00ff8100 2268 000c 4e91')
        program, result = self.run_fixture(fixture)
        self.assertEqual(next(iter(program.memory_callbacks.values()))['slots'], [0xff810c])
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_register_copies_and_postincrement_pointer_load_preserve_the_origin(self):
        fixture = UploadRom()
        fixture.image(0x600, '7007 4e75')
        fixture.add('41f9 00ff8100 20bc 00000600 2258 2409 2642 4e93')
        _, result = self.run_fixture(fixture)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('D0=00000007', result.stdout)

    def test_static_ram_variant_reads_an_object_callback_and_executes_its_rom_body(self):
        fixture = UploadRom()
        size = fixture.image(0x600, '41f9 00ff8400 2268 000c 4e91 4e75')
        fixture.image(0x680, '7007 4e75')
        fixture.add('41f9 00ff8400 217c 00000680 000c')
        fixture.upload(0x600, 0xff8100, size)
        fixture.call()
        program, result = self.run_fixture(fixture)
        self.assertEqual(program.memory_callbacks[0xff810a]['targets'], [0x680])
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('D0=00000007', result.stdout)

    def test_patched_ram_lea_discovers_both_known_object_addresses(self):
        fixture = UploadRom()
        size = fixture.image(0x600, '41f9 00ff8400 2268 000c 4e91 4e75')
        fixture.image(0x680, '7007 4e75')
        fixture.image(0x700, '7009 4e75')
        fixture.add('41f9 00ff8400 217c 00000680 000c '
                    '41f9 00ff8500 217c 00000700 000c')
        fixture.upload(0x600, 0xff8100, size)
        fixture.add('23fc 00ff8500 00ff8102')
        fixture.call()
        program, result = self.run_fixture(fixture)
        self.assertEqual(program.memory_callbacks[0xff810a]['targets'], [0x680, 0x700])
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('D0=00000009', result.stdout)

    def test_unknown_object_address_is_not_guessed_from_displacement_alone(self):
        fixture = UploadRom()
        fixture.image(0x600, '7007 4e75')
        fixture.add('217c 00000600 000c 2268 000c 4e91')
        program = analyze(fixture.finish(), [0x200])
        self.assertEqual(program.memory_callbacks, {})
        self.assertNotIn(0x600, program.instructions)

    def test_call_clobbers_prevent_borrowing_an_object_definition(self):
        fixture = UploadRom()
        fixture.image(0x600, '7007 4e75')
        fixture.image(0x680, '41f9 00ff8200 4e75')
        fixture.add('41f9 00ff8100 217c 00000600 000c '
                    '4eb9 00000680 2268 000c 4e91')
        program = analyze(fixture.finish(), [0x200])
        self.assertEqual(program.memory_callbacks, {})
        self.assertNotIn(0x600, program.instructions)

    def test_known_register_function_constant_can_be_stored_into_a_resolved_field(self):
        fixture = UploadRom()
        fixture.image(0x600, '7007 4e75')
        fixture.add('41f9 00ff8100 45f9 00000600 214a 000c 2268 000c 4e91')
        program, result = self.run_fixture(fixture)
        self.assertEqual(next(iter(program.memory_callbacks.values()))['targets'], [0x600])
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_partial_store_cannot_supply_a_longword_function_pointer(self):
        fixture = UploadRom()
        fixture.image(0x600, '7007 4e75')
        fixture.add('41f9 00ff8100 317c 0600 000e 2268 000c 4e91')
        program = analyze(fixture.finish(), [0x200])
        self.assertEqual(program.memory_callbacks, {})
