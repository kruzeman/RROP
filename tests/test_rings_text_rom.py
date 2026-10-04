"""Optional tests of the actual text-writer ABI, without publishing ROM bytes."""
import hashlib
from pathlib import Path
import subprocess
import unittest

from genesis_recompiler.decode import analyze
from genesis_recompiler.emit import emit
from support import CompiledTestCase

ROM=Path(__file__).resolve().parents[1]/'build/rings-of-power/Rings of Power (UE) [!].gen'


class RingsTextROMTests(CompiledTestCase):
    @unittest.skipUnless(ROM.exists(),'user-provided Rings of Power [!] ROM is not present')
    def test_original_writers_capture_ram_text_and_preserve_cpu_behavior(self):
        rom=ROM.read_bytes()
        self.assertEqual(hashlib.sha256(rom).hexdigest(),'36303fc447c433ebc69c3d4df86c783c86b383e0acead1c19595f13269e248f5')
        program=analyze(rom,[0x1113c,0x1119e])
        self.assertEqual(program.errors,{})
        harness=r'''
#include <assert.h>
static void setup(CPU *c,unsigned pc,int capture) {
    c->rom=rom_data;c->rom_size=sizeof rom_data;c->sr=0x2700;
    c->vdp.registers[1]=0x44;c->vdp.registers[2]=8;c->vdp.registers[4]=5;
    c->vdp.registers[12]=1;c->vdp.registers[13]=0x38;c->vdp.registers[15]=2;c->vdp.registers[16]=1;
    c->vdp.font_enabled=(uint8_t)capture;
    memset(c->vdp.font_supported,1,sizeof c->vdp.font_supported);
    const char *text="Live 42.,-!";
    for(unsigned i=0;text[i];++i)write_mem(c,0xff1000+i,1,(unsigned char)text[i]);
    write_mem(c,0xff1000+strlen(text),1,0);write_mem(c,0xff8640,2,0x294);
    c->a[7]=0xffdff0;c->a[6]=0xffe100;c->d[4]=0x12345678;
    write_mem(c,c->a[7],4,0x2000);write_mem(c,c->a[7]+4,2,64);
    write_mem(c,c->a[7]+6,2,3);write_mem(c,c->a[7]+8,2,5);
    write_mem(c,c->a[7]+10,4,0xff1000);write_mem(c,c->a[7]+14,2,0x8000);
    push32(c,0x400);c->pc=pc;
}
int main(void) {
    CPU *observed=calloc(1,sizeof *observed),*plain=calloc(1,sizeof *plain);
    assert(observed && plain);
    const unsigned writers[]={0x1113c,0x1119e};
    for(unsigned w=0;w<2;++w) {
        memset(observed,0,sizeof *observed);memset(plain,0,sizeof *plain);
        setup(observed,writers[w],1);setup(plain,writers[w],0);
        while(observed->pc!=0x400 && !observed->fault && observed->steps<10000)machine_step(observed);
        while(plain->pc!=0x400 && !plain->fault && plain->steps<10000)machine_step(plain);
        assert(!observed->fault && !plain->fault && observed->pc==0x400 && plain->pc==0x400);
        assert(!memcmp(observed->d,plain->d,sizeof observed->d));
        assert(!memcmp(observed->a,plain->a,sizeof observed->a));
        assert(!memcmp(observed->ram,plain->ram,sizeof observed->ram));
        assert(!memcmp(observed->vdp.vram,plain->vdp.vram,sizeof observed->vdp.vram));
        assert(observed->sr==plain->sr && observed->steps==plain->steps && observed->cycles==plain->cycles);
        assert(observed->d[4]==0x12345678 && observed->a[6]==0xffe100);
        assert(observed->vdp.font_captured[w]==11 && !observed->vdp.font_captured[1-w]);
        const char *text="Live 42.,-!";
        for(unsigned i=0;text[i];++i) {
            unsigned at=0x2000+(5*64+3+i)*2;
            assert(observed->vdp.font_marks[at/2].ch==text[i]);
            assert(observed->vdp.font_marks[at/2].run==observed->vdp.font_marks[(0x2000+(5*64+3)*2)/2].run);
        }
    }
    free(observed);free(plain);return 0;
}
'''
        binary=self.compile('#define GENESIS_NO_MAIN\n#define GENESIS_RINGS_MENU_FONT\n'+emit(program)+harness)
        result=subprocess.run([str(binary)],capture_output=True,text=True,timeout=20)
        self.assertEqual(result.returncode,0,result.stderr)
