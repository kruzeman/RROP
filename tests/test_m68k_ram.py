"""ROM-derived RAM code must be translated at its execution address and guarded."""
import json
import subprocess
from genesis_recompiler.cli import main
from genesis_recompiler.decode import RamCodeCopy, analyze
from genesis_recompiler.emit import emit
from support import CompiledTestCase


def ram_code_rom(destination=0xff8100, patch='', upload=True):
    rom = bytearray(0x400)
    rom[:8] = bytes.fromhex('00ffff00 00000200')
    code = '41f9 00000300 43f9 00ff8100 7202 22d8 51c9 fffc' if upload else ''
    raw = bytes.fromhex(code + ' ' + patch + f' 4eb9 {destination:08x} 2410 4e72 2700')
    rom[0x200:0x200+len(raw)] = raw
    rom[0x300:0x30c] = bytes.fromhex('41fa 0006 7007 4e75 deadcafe')
    return bytes(rom), RamCodeCopy(0x300, destination, 12)


def mutable_address_rom(address=0xff8200, patch=''):
    rom=bytearray(0x400);rom[:8]=bytes.fromhex('00ffff00 00000200')
    code=('41f9 00000300 43f9 00ff8100 22d8 22d8 '
          '23fc beefcafe 00ff8200 '+f'23fc {address:08x} 00ff8102 '+patch+
          ' 4eb9 00ff8100 3200 23fc 00ff8202 00ff8102 4eb9 00ff8100 4e72 2700')
    raw=bytes.fromhex(code);rom[0x200:0x200+len(raw)]=raw
    rom[0x300:0x308]=bytes.fromhex('3039 12345678 4e75')
    return bytes(rom), RamCodeCopy(0x300, 0xff8100, 8)


class M68kRamTests(CompiledTestCase):
    def test_mutable_address_reads_the_live_field_after_each_real_game_patch(self):
        rom,copy=mutable_address_rom()
        program=analyze(rom,[0x200],[copy],mutable_addresses=[0xff8100])
        self.assertEqual(program.errors,{})
        result=subprocess.run([str(self.compile(emit(program)))],capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertIn('D0=0000cafe',result.stdout)
        self.assertIn('D1=0000beef',result.stdout)

    def test_mutable_address_keeps_opcode_guards_and_bus_faults(self):
        for address,patch,reason in ((0xff8200,'31fc 3239 8100','RAM instruction bytes'),
                                      (0xff8201,'','address error'),
                                      (0x400000,'','unmapped read')):
            rom,copy=mutable_address_rom(address,patch)
            program=analyze(rom,[0x200],[copy],mutable_addresses=[0xff8100])
            result=subprocess.run([str(self.compile(emit(program)))],capture_output=True,text=True)
            self.assertEqual(result.returncode,1)
            self.assertIn(reason,result.stderr)
            self.assertIn('D0=00000000',result.stdout)

    def test_mutable_address_annotation_requires_a_ram_move_source(self):
        rom,copy=mutable_address_rom()
        for pc in (0x200,0xff8102,0xff8106):
            with self.assertRaisesRegex(ValueError,'RAM MOVE'):
                analyze(rom,[0x200],[copy],mutable_addresses=[pc])
        with self.assertRaisesRegex(ValueError,'RAM MOVE'):
            analyze(rom,[0x200,0x300],mutable_addresses=[0x300])

    def test_cli_reports_mutable_address_declaration(self):
        rom,_=mutable_address_rom()
        source,output,report=self.root/'rom.bin',self.root/'game.c',self.root/'game.json'
        source.write_bytes(rom)
        self.assertEqual(main([str(source),'-o',str(output),'--report',str(report),
            '--m68k-copy','0x300:0xff8100:8','--m68k-mutable-address','0xff8100']),0)
        self.assertEqual(json.loads(report.read_text())['m68k_mutable_addresses'],[0xff8100])

    def test_real_upload_executes_pc_relative_ram_code_and_returns(self):
        for destination in (0xff8100, 0xe08100):
            rom, copy = ram_code_rom(destination)
            program = analyze(rom, [0x200], [copy])
            self.assertEqual(program.errors, {})
            self.assertEqual(program.instructions[destination].src.value, destination+8)
            self.assertEqual(program.instructions[destination].raw, bytes.fromhex('41fa 0006'))
            result = subprocess.run([str(self.compile(emit(program)))], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn('D0=00000007', result.stdout)
            self.assertIn('D2=deadcafe', result.stdout)
            self.assertIn('A7=00ffff00', result.stdout)

    def test_changed_opcode_or_operand_faults_before_the_instruction_runs(self):
        for patch, pc in [('31fc 4e71 8104', 0xff8104), ('31fc 0008 8102', 0xff8100)]:
            rom, copy = ram_code_rom(patch=patch)
            program = analyze(rom, [0x200], [copy])
            result = subprocess.run([str(self.compile(emit(program)))], capture_output=True, text=True)
            self.assertEqual(result.returncode, 1)
            self.assertIn(f'fault at {pc:06x}: 68000 RAM instruction bytes do not match static translation', result.stderr)
            self.assertIn('D0=00000000', result.stdout)

    def test_static_copy_does_not_populate_runtime_ram(self):
        rom, copy = ram_code_rom(upload=False)
        result = subprocess.run([str(self.compile(emit(analyze(rom, [0x200], [copy]))))], capture_output=True, text=True)
        self.assertEqual(result.returncode, 1)
        self.assertIn('fault at ff8100: 68000 RAM instruction bytes do not match static translation', result.stderr)

    def test_invalid_sources_and_destinations_are_rejected_and_alias_images_are_allowed(self):
        rom, copy = ram_code_rom()
        for wrong in [RamCodeCopy(-1, 0xff8100, 12), RamCodeCopy(0x3fc, 0xff8100, 12),
                      RamCodeCopy(0x300, 0xff8101, 12), RamCodeCopy(0x300, 0xc00000, 12),
                      RamCodeCopy(0x300, 0xfffffa, 12), RamCodeCopy(0x300, 0xff8100, 1)]:
            with self.assertRaises(ValueError): analyze(rom, [0x200], [wrong])
        aliases = analyze(rom, [0x200], [copy, RamCodeCopy(0x300, 0xe08100, 12)])
        self.assertEqual(aliases.errors, {})
        self.assertIn(0xe08100, aliases.ram_variants)
        rom, _ = ram_code_rom(upload=False)
        program = analyze(rom, [0x200], [RamCodeCopy(0x300, 0xff8100, 4)])
        self.assertIn(0xff8104, program.errors)

    def test_cli_reports_known_copy_and_additional_ram_roots(self):
        rom, _ = ram_code_rom()
        input_file, source, report = self.root/'rom.bin', self.root/'game.c', self.root/'game.json'
        input_file.write_bytes(rom)
        self.assertEqual(main([str(input_file), '-o', str(source), '--report', str(report),
                               '--m68k-copy', '0x300:0xff8100:12']), 0)
        self.assertEqual(json.loads(report.read_text())['m68k_ram_copies'],
                         [{'rom_offset': 0x300, 'address': 0xff8100, 'size': 12}])
        self.assertEqual(main([str(input_file), '-o', str(source), '--m68k-copy', '0x300:0xfffffa:12']), 1)

    def test_cli_discovers_interrupt_entry_inside_a_declared_ram_copy(self):
        rom, _ = ram_code_rom()
        rom = bytearray(rom)
        rom[0x70:0x74] = (0xff810c).to_bytes(4,'big')
        rom[0x30c:0x30e] = bytes.fromhex('4e73')
        input_file, source, report = self.root/'rom.bin', self.root/'game.c', self.root/'game.json'
        input_file.write_bytes(rom)
        self.assertEqual(main([str(input_file), '-o', str(source), '--report', str(report),
                               '--m68k-copy', '0x300:0xff8100:14']), 0)
        result = json.loads(report.read_text())
        self.assertEqual(result['interrupt_targets'], {'4': 0xff810c})
        self.assertEqual(next(i['assembly'] for i in result['instructions'] if i['pc']==0xff810c), 'RTE')
