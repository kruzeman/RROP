import subprocess
from genesis_recompiler.decode import analyze
from genesis_recompiler.emit import emit
from support import CompiledTestCase


def unrolled_rom(index=3, count=16, unit='24c0 d4c3'):
    rom=bytearray(0x400)
    rom[:8]=bytes.fromhex('00ffff00 00000200')
    raw=bytearray.fromhex(f'7055 72{index:02x} 7602 45f9 00ff0100 d241 d241 4441')
    jump=0x200+len(raw)
    block=bytes.fromhex(unit)*count
    raw+=bytes.fromhex('4efb 1000')
    raw[-1]=len(block)+2
    start=0x200+len(raw)
    raw+=block+bytes.fromhex('4e72 2700')
    rom[0x200:0x200+len(raw)]=raw
    return bytes(rom),jump,start,start+len(block)


class UnrolledBlockTests(CompiledTestCase):
    def test_partial_and_full_unrolled_fill_execute_without_interpreting_opcodes(self):
        for index in (0,1,3,16):
            rom,jump,start,end=unrolled_rom(index)
            program=analyze(rom,[0x200])
            self.assertEqual(program.errors,{})
            self.assertEqual(program.unrolled_blocks[jump],
                             {'start':start,'end':end,'stride':4,'count':16,'targets':list(range(start,end+1,4))})
            self.assertIn(jump,program.indirect)  # Candidate roots don't prove all possible indices.
            harness=f'''
#include <assert.h>
int main(void) {{
    CPU c={{0}}; c.rom=rom_data; c.rom_size=sizeof rom_data; c.sr=0x2700; c.pc=0x200;
    while (!c.halted && !c.fault && c.steps<100) {{ translated_step(&c); ++c.steps; }}
    assert(c.halted && !c.fault && c.a[2]==0xff0100+{index}*6);
    for (unsigned n=0;n<16;n++) {{
        assert(read_mem(&c,0xff0100+n*6,4)==((int)n<{index}?0x55:0));
        assert(read_mem(&c,0xff0104+n*6,2)==0);
    }}
    return 0;
}}
'''
            result=subprocess.run([str(self.compile('#define GENESIS_NO_MAIN\n'+emit(program)+harness))],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)

    def test_wrong_index_scale_register_and_nonidentical_rows_are_rejected(self):
        rom,jump,start,end=unrolled_rom()
        for at,raw in [(0x20c,'4e71'),(0x210,'4440'),(0x210,'4481'),
                       (jump+2,f'{0x1800+end-jump-2:04x}'),(start+4,'24c1')]:
            with self.subTest(at=at,raw=raw):
                changed=bytearray(rom);changed[at:at+2]=bytes.fromhex(raw)
                self.assertEqual(analyze(bytes(changed),[0x200]).unrolled_blocks,{})
        for unit in ('24c0 d2c3','24c0 d4c8','24c0 4e71'):
            rom,_,_,_=unrolled_rom(unit=unit)
            self.assertEqual(analyze(rom,[0x200]).unrolled_blocks,{})

    def test_truncated_and_non_code_blocks_are_rejected(self):
        rom,_,_,end=unrolled_rom()
        self.assertEqual(analyze(rom[:end],[0x200]).unrolled_blocks,{})
        rom,jump,start,end=unrolled_rom(unit='0000 0000')
        self.assertEqual(analyze(rom,[0x200]).unrolled_blocks,{})
