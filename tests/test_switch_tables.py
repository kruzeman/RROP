from genesis_recompiler.decode import analyze
from support import CompiledTestCase


def place_switch(rom, at, index):
    # The signed table entries point backwards from JMP's indexed PC base.
    header=f'70{index&255:02x} b0bc 00000002 6400 0046 e380 303b 0010 4efb 002c'
    raw=bytes.fromhex(header); rom[at:at+len(raw)]=raw
    rom[at+0x20:at+0x24]=bytes.fromhex('fff0 fff8')
    rom[at+0x30:at+0x36]=bytes.fromhex('7455 4e72 2700')
    rom[at+0x38:at+0x3e]=bytes.fromhex('7466 4e72 2700')
    rom[at+0x50:at+0x56]=bytes.fromhex('7444 4e72 2700')


def switch_rom(index=0):
    rom=bytearray(0x400)
    rom[:8]=bytes.fromhex('00ffff00 00000200')
    place_switch(rom,0x200,index)
    return rom


class SwitchTableTests(CompiledTestCase):
    def test_signed_table_targets_are_compiled_and_execute(self):
        for index,expected in [(0,0x55),(1,0x66),(2,0x44),(-1,0x44)]:
            with self.subTest(index=index):
                rom=bytes(switch_rom(index));p=analyze(rom,[0x200])
                self.assertEqual(p.errors,{})
                self.assertEqual(p.indirect,[])
                self.assertEqual(p.jump_tables[0x212],{'table':0x220,'base':0x240,'count':2,'targets':[0x230,0x238]})
                result=self.execute(rom)
                self.assertEqual(result.returncode,0,result.stderr)
                self.assertIn(f'D2={expected:08x}',result.stdout)

    def test_newly_reachable_switch_is_discovered(self):
        rom=switch_rom();place_switch(rom,0x300,1)
        rom[0x230:0x234]=bytes.fromhex('6000 00ce')
        p=analyze(bytes(rom),[0x200])
        self.assertEqual(p.errors,{})
        self.assertEqual(set(p.jump_tables),{0x212,0x312})
        result=self.execute(bytes(rom))
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertIn('D2=00000066',result.stdout)

    def test_nonmatching_patterns_remain_unresolved(self):
        edits=[(0x20c,'e580'), # shift by two
               (0x208,'6600'), # wrong bound condition
               (0x20e,'323b'), # different destination register
               (0x210,'1010'), # different table index register
               (0x214,'082c'), # long JMP index instead of signed word
               (0x20a,'0002')] # out-of-range branch enters dispatch
        for at,raw in edits:
            with self.subTest(at=at,raw=raw):
                rom=switch_rom();rom[at:at+2]=bytes.fromhex(raw)
                p=analyze(bytes(rom),[0x200])
                self.assertEqual(p.jump_tables,{})
                self.assertIn(0x212,p.indirect)

    def test_invalid_targets_and_oversized_count_are_not_inferred(self):
        for table in ('fff1 fff8','7fff fff8'):
            rom=switch_rom();rom[0x220:0x224]=bytes.fromhex(table)
            p=analyze(bytes(rom),[0x200]);self.assertEqual(p.jump_tables,{})
        rom=switch_rom();rom[0x204:0x208]=(513).to_bytes(4,'big')
        self.assertEqual(analyze(bytes(rom),[0x200]).jump_tables,{})
