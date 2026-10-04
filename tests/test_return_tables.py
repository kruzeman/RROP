import json
import subprocess
from genesis_recompiler.cli import main
from genesis_recompiler.decode import analyze
from genesis_recompiler.emit import emit
from support import CompiledTestCase


def return_table_rom(index=35, code_at=0x200, table=0x400, post_lea=True):
    rom=bytearray(0x1800)
    rom[:8]=(0xffff00).to_bytes(4,'big')+code_at.to_bytes(4,'big')
    target0,target1=code_at+0x80,code_at+0x90
    # Word indexing discards MOVEQ's sign-extended high half.
    raw=bytes.fromhex(f'70{index&0xf0:02x} 72{index&15:02x} c07c 00f0 8001 e540')
    lea=code_at+len(raw)
    displacement=table-(lea+2)
    raw+=bytes.fromhex('43fa')+(displacement&0xffff).to_bytes(2,'big')
    push=code_at+len(raw)
    raw+=bytes.fromhex('2f31 0000')
    if post_lea: raw+=bytes.fromhex('43f9 00000010')  # Replace A1 after its pointer was pushed.
    ret=code_at+len(raw)
    raw+=bytes.fromhex('4e75')
    rom[code_at:code_at+len(raw)]=raw
    for n in range(256):
        rom[table+n*4:table+n*4+4]=(target1 if n==35 or n==255 else target0).to_bytes(4,'big')
    rom[target0:target0+6]=bytes.fromhex('7455 4e72 2700')
    rom[target1:target1+6]=bytes.fromhex('7466 4e72 2700')
    return rom,{'pc':ret,'push':push,'lea':lea,'table':table,'target0':target0,'target1':target1}


class ReturnTableTests(CompiledTestCase):
    def test_dispatch_translates_all_targets_and_executes_with_intact_stack(self):
        for index,post_lea,expected in [(0,False,0x55),(35,True,0x66),(255,True,0x66)]:
            with self.subTest(index=index,post_lea=post_lea):
                rom,info=return_table_rom(index,post_lea=post_lea)
                program=analyze(bytes(rom),[0x200])
                self.assertEqual(program.errors,{})
                table=program.return_tables[info['pc']]
                self.assertEqual(table['table'],0x400)
                self.assertEqual(table['count'],256)
                self.assertEqual(table['push_pc'],info['push'])
                self.assertEqual(set(table['targets']),{info['target0'],info['target1']})
                binary=self.compile(emit(program))
                result=subprocess.run([str(binary)],capture_output=True,text=True)
                self.assertEqual(result.returncode,0,result.stderr)
                self.assertIn(f'D2={expected:08x}',result.stdout)
                self.assertIn('A7=00ffff00',result.stdout)

    def test_backward_pc_relative_table(self):
        rom,info=return_table_rom(code_at=0x1000,table=0x400)
        program=analyze(bytes(rom),[0x1000])
        self.assertEqual(program.errors,{})
        self.assertEqual(program.return_tables[info['pc']]['table'],0x400)
        result=subprocess.run([str(self.compile(emit(program)))],capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertIn('D2=00000066',result.stdout)

    def test_mismatched_mask_index_push_and_stack_changes_are_rejected(self):
        rom,info=return_table_rom()
        edits=[(0x206,'0200'),  # Too large a conservative bound.
               (0x208,'8041'),  # OR.W permits unbounded source bits.
               (0x20a,'e548'),  # LSL rather than the recognized ASL form.
               (0x20a,'e340'),  # Shift by one rather than four-byte entries.
               (info['push']+2,'0800'),  # Long indexing is not bounded by AND.W.
               (info['push']+2,'1000'),  # Wrong index register.
               (info['push'],'3f31'),  # Two-byte push is not an RTS pointer.
               (info['push']+4,'4ff9')]  # LEA modifies the stack after the push.
        for at,raw in edits:
            with self.subTest(at=at,raw=raw):
                changed=bytearray(rom);changed[at:at+2]=bytes.fromhex(raw)
                program=analyze(bytes(changed),[0x200])
                self.assertEqual(program.return_tables,{})
        changed=bytearray(rom);changed[0x204:0x206]=bytes.fromhex('c03c')
        self.assertEqual(analyze(bytes(changed),[0x200]).return_tables,{})

    def test_invalid_targets_unaligned_tables_and_truncated_tables_are_rejected(self):
        for target in (0,0x281,0xff0000):
            rom,info=return_table_rom()
            rom[0x400:0x404]=target.to_bytes(4,'big')
            self.assertEqual(analyze(bytes(rom),[0x200]).return_tables,{})
        rom,info=return_table_rom()
        displacement=int.from_bytes(rom[info['lea']+2:info['lea']+4],'big')
        rom[info['lea']+2:info['lea']+4]=(displacement+1).to_bytes(2,'big')
        self.assertEqual(analyze(bytes(rom),[0x200]).return_tables,{})
        rom,info=return_table_rom()
        self.assertEqual(analyze(bytes(rom[:0x7fe]),[0x200]).return_tables,{})

    def test_newly_reachable_return_table_is_discovered_and_reported(self):
        rom,first=return_table_rom(index=0)
        second_rom,second=return_table_rom(index=35,code_at=0x1000,table=0x800)
        rom[0x800:]=second_rom[0x800:]
        displacement=0x1000-(first['target0']+2)
        rom[first['target0']:first['target0']+4]=bytes.fromhex('6000')+displacement.to_bytes(2,'big')
        program=analyze(bytes(rom),[0x200])
        self.assertEqual(program.errors,{})
        self.assertEqual(set(program.return_tables),{first['pc'],second['pc']})
        result=subprocess.run([str(self.compile(emit(program)))],capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertIn('D2=00000066',result.stdout)
        input_file,source,report=self.root/'game.bin',self.root/'game.c',self.root/'report.json'
        input_file.write_bytes(rom)
        self.assertEqual(main([str(input_file),'-o',str(source),'--report',str(report)]),0)
        self.assertEqual(len(json.loads(report.read_text())['return_tables']),2)
