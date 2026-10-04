"""Game-independent discovery, including native calls and rejected data."""
import subprocess
from genesis_recompiler.decode import EA, analyze
from genesis_recompiler.discovery import ValueSlice
from genesis_recompiler.emit import emit
from support import CompiledTestCase, rom_with


class DiscoveryTests(CompiledTestCase):
    def test_lea_register_copy_and_signed_displacement_call_execute(self):
        rom = bytearray(rom_with('41fa 00fe 2248 43e9 fffe 4e91 4e72 2700'))
        rom[0x2fe:0x302] = bytes.fromhex('7455 4e75')
        p = analyze(bytes(rom), [0x200])
        self.assertEqual(p.errors, {})
        self.assertEqual(p.value_transfers[0x20a]['targets'], [0x2fe])
        result = self.execute(bytes(rom))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('D2=00000055', result.stdout)
        self.assertIn('A7=00ffff00', result.stdout)

    def test_masked_scaled_index_resolves_only_read_function_pointers(self):
        # Unknown D0.W is masked to 0..3, then doubled twice. This table is
        # remote from the dispatcher, so only value analysis can find it.
        rom = bytearray(rom_with('3038 8010 0240 0003 d040 d040 207b 0062 4e90 4e72 2700'))
        for n in range(4):
            rom[0x270+4*n:0x274+4*n] = (0x300+8*n).to_bytes(4, 'big')
            rom[0x300+8*n:0x304+8*n] = bytes.fromhex(f'74{n+1:02x} 4e75')
        p = analyze(bytes(rom), [0x200])
        self.assertEqual(p.value_transfers[0x210]['targets'], [0x300, 0x308, 0x310, 0x318])
        self.assertEqual(len(p.value_transfers[0x210]['rom_reads']), 4)
        self.assertIn(0x210, p.indirect)  # Never advertise exhaustive resolution.
        result = self.execute(bytes(rom))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('D2=00000001', result.stdout)
        # One bad pointer rejects the whole finite set, rather than filtering
        # out evidence that the index or table may be wrong.
        rom[0x278:0x27c] = (0x301).to_bytes(4, 'big')
        self.assertEqual(analyze(bytes(rom), [0x200]).value_transfers, {})

    def test_callback_parameter_is_followed_through_a_generic_installer(self):
        rom = bytearray(rom_with('41fa 00fe 6100 003a 2278 8010 4e91 4e72 2700'))
        rom[0x240:0x246] = bytes.fromhex('2448 21ca 8010')
        rom[0x246:0x248] = bytes.fromhex('4e75')
        rom[0x300:0x304] = bytes.fromhex('7466 4e75')
        p = analyze(bytes(rom), [0x200])
        self.assertEqual(p.ram_callbacks[0x20c]['targets'], [0x300])
        result = self.execute(bytes(rom))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('D2=00000066', result.stdout)

    def test_calls_clobbers_updates_and_branch_entries_stop_value_slices(self):
        for body in ('207c 00000300 5888 4ed0',
                     '207c 00000300 1018 4ed0',
                     '207c 00000300 4eb9 00000320 4ed0',
                     '207c 00000300 4c90 0100 4ed0',
                     '2078 8010 4ed0'):
            rom = bytearray(rom_with(body))
            rom[0x300:0x302] = bytes.fromhex('4e75')
            rom[0x304:0x306] = bytes.fromhex('4e75')
            rom[0x320:0x322] = bytes.fromhex('4e75')
            p = analyze(bytes(rom), [0x200])
            if '5888' in body:
                self.assertEqual(next(iter(p.value_transfers.values()))['targets'], [0x304])
            else:
                self.assertEqual(p.value_transfers, {})
        # One path skips the LEA. Physical adjacency must not prove A0's value.
        rom = rom_with('6704 41fa 00fc 4ed0')
        self.assertEqual(analyze(rom, [0x200]).value_transfers, {})

    def test_partial_writes_keep_unknown_high_bits_and_right_shifts_use_them(self):
        rom = rom_with('203c 80000000 e088 303c 0300 4e72 2700')
        p = analyze(rom, [0x200])
        s = ValueSlice(p, {i.end:i for i in p.instructions.values()}, set())
        self.assertEqual(s.register(EA(0,0), 0x208, 2), frozenset((0,)))
        self.assertEqual(s.register(EA(0,0), 0x20c, 4), frozenset((0x00800300,)))
        unknown = analyze(rom_with('303c 0300 4e72 2700'), [0x200])
        s = ValueSlice(unknown, {i.end:i for i in unknown.instructions.values()}, set())
        self.assertIsNone(s.register(EA(0,0), 0x204, 4))

    def test_long_right_shift_moves_high_bits_into_low_word(self):
        rom = rom_with('203c 80010000 e088 e088 4e72 2700')  # LSR.L #8 twice
        p = analyze(rom, [0x200])
        s = ValueSlice(p, {i.end:i for i in p.instructions.values()}, set())
        self.assertEqual(s.register(EA(0,0), 0x20a, 2), frozenset((0x8001,)))

    def test_unknown_long_index_is_not_bounded_by_a_word_mask(self):
        rom = bytearray(rom_with('0240 0003 207b 087a 4ed0'))
        rom[0x280:0x290] = (0x300).to_bytes(4, 'big')*4
        self.assertEqual(analyze(bytes(rom), [0x200]).value_transfers, {})

    def test_unsigned_branch_bounds_a_remote_table_without_pattern_matching(self):
        rom = bytearray(rom_with('3038 8010 0c40 0003 6410 4e71 d040 d040 207b 0068 4e90 4e72 2700 4e72 2700'))
        for n in range(3):
            rom[0x27a+4*n:0x27e+4*n] = (0x300+8*n).to_bytes(4, 'big')
            rom[0x300+8*n:0x304+8*n] = bytes.fromhex(f'74{n+1:02x} 4e75')
        p = analyze(bytes(rom), [0x200])
        # This is not one of the legacy exact instruction patterns.
        self.assertEqual(p.value_transfers[0x214]['targets'], [0x300, 0x308, 0x310])
        result = self.execute(bytes(rom))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('D2=00000001', result.stdout)

    def test_inline_pointer_table_without_index_bound_executes(self):
        rom = bytearray(rom_with('7001 e540 207b 0004 4ed0'))
        table = 0x20a
        for n, target in enumerate((0x216, 0x21c, 0x222)):
            rom[table+4*n:table+4*n+4] = target.to_bytes(4, 'big')
            rom[target:target+6] = bytes.fromhex(f'74{n+1:02x} 4e72 2700')
        p = analyze(bytes(rom), [0x200])
        self.assertEqual(p.inline_pointer_tables[0x208]['count'], 3)
        result = self.execute(bytes(rom))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('D2=00000002', result.stdout)
        rom[table+4:table+8] = (0x21d).to_bytes(4, 'big')
        self.assertEqual(analyze(bytes(rom), [0x200]).inline_pointer_tables, {})

    def test_inline_word_offsets_discover_unselected_handlers(self):
        rom = bytearray(rom_with('7001 d040 303b 0006 4efb 0002'))
        rom[0x20c:0x212] = bytes.fromhex('0006 000c 0012')
        for n in range(3):
            rom[0x212+6*n:0x218+6*n] = bytes.fromhex(f'74{n+1:02x} 4e72 2700')
        p = analyze(bytes(rom), [0x200])
        self.assertEqual(p.inline_relative_tables[0x208]['targets'], [0x212, 0x218, 0x21e])
        result = self.execute(bytes(rom))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('D2=00000002', result.stdout)

    def test_inline_pointer_base_can_follow_a_negative_index_fallback(self):
        rom = bytearray(rom_with('303c ffff e548 207b 0008 4ed0'))
        for n, target in enumerate((0x21c, 0x222, 0x228, 0x22e)):
            rom[0x20c+4*n:0x210+4*n] = target.to_bytes(4, 'big')
            rom[target:target+6] = bytes.fromhex(f'74{n+1:02x} 4e72 2700')
        p = analyze(bytes(rom), [0x200])
        table = p.inline_pointer_tables[0x20a]
        self.assertEqual((table['table'], table['start'], table['count']), (0x210, 0x20c, 4))
        result = self.execute(bytes(rom))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('D2=00000001', result.stdout)

    def test_inline_pointer_table_can_follow_a_call_return_branch(self):
        rom = bytearray(rom_with('3038 8010 e540 207b 0006 4e90 6022'))
        for n, target in enumerate((0x21a, 0x21e, 0x222)):
            rom[0x20e+4*n:0x212+4*n] = target.to_bytes(4, 'big')
            rom[target:target+4] = bytes.fromhex(f'74{n+1:02x} 4e75')
        rom[0x230:0x234] = bytes.fromhex('4e72 2700')
        p = analyze(bytes(rom), [0x200])
        self.assertEqual(p.inline_pointer_tables[0x20a]['count'], 3)
        result = self.execute(bytes(rom))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('D2=00000001', result.stdout)

    def test_unknown_indirect_target_still_faults_without_runtime_decoding(self):
        # The pointer is copied through mutable RAM, so its value remains
        # unknown to the static slices. No hidden opcode fallback is allowed.
        rom = bytearray(rom_with('23fc 00000300 00ff8020 2039 00ff8020 '
                                '23c0 00ff8010 2078 8010 4ed0'))
        rom[0x300:0x304] = bytes.fromhex('4e72 2700')
        p = analyze(bytes(rom), [0x200])
        self.assertNotIn(0x300, p.instructions)
        run = subprocess.run([str(self.compile(emit(p)))], capture_output=True, text=True)
        self.assertEqual(run.returncode, 1)
        self.assertIn('no translated instruction', run.stderr)

    def test_broad_candidate_set_cannot_decode_overlapping_instruction_entries(self):
        rom = bytearray(b'\xff' * 0x800)
        rom[:8] = bytes.fromhex('00ffff00 00000200')
        rom[0x200:0x20c] = bytes.fromhex('7000 1011 d040 d040 4efb 0036')
        rom[0x240:0x24a] = bytes.fromhex('243c 00000055 4e72 2700')
        p = analyze(bytes(rom), [0x200])
        self.assertEqual(p.errors, {})
        self.assertEqual(p.value_transfers, {})
        self.assertNotIn(0x240, p.instructions)
