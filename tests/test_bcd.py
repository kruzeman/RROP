"""BCD operations checked against decimal arithmetic, including chained bytes."""
import subprocess
from genesis_recompiler.decode import Decoder, DecodeError, analyze
from genesis_recompiler.emit import emit
from support import CompiledTestCase, rom_with


class BcdTests(CompiledTestCase):
    def test_decode_register_memory_and_unary_forms(self):
        for raw, op, src, dst in [('c300','ABCD',0,1), ('8300','SBCD',0,1),
                                  ('c509','ABCD',1,2), ('8f0f','SBCD',7,7)]:
            i=Decoder(bytes.fromhex(raw),0).decode()
            self.assertEqual((i.op,i.size,i.src.reg,i.dst.reg),(op,1,src,dst))
            self.assertEqual(i.src.mode,4 if int(raw,16)&8 else 0)
        self.assertEqual(Decoder(bytes.fromhex('4818'),0).decode().op,'NBCD')
        for raw in ('4808','483a 0000','483c 0000'):
            with self.assertRaises(DecodeError): Decoder(bytes.fromhex(raw),0).decode()

    def test_exhaustive_valid_decimal_operands_defined_flags_and_register_width(self):
        p=analyze(rom_with('c300 4e75 8300 4e75 4801 4e75'),[0x200,0x204,0x208])
        harness=r'''
#include <assert.h>
static unsigned packed(unsigned n) { return ((n/10)<<4)|(n%10); }
int main(void) {
    CPU c={0}; c.rom=rom_data; c.rom_size=sizeof rom_data;
    for (unsigned sub=0;sub<2;++sub) for (unsigned d=0;d<100;++d)
    for (unsigned s=0;s<100;++s) for (unsigned x=0;x<2;++x)
    for (unsigned oldz=0;oldz<2;++oldz) for (unsigned nv=0;nv<4;++nv) {
        c.pc=sub?0x204:0x200; c.d[0]=0x12345600|packed(s); c.d[1]=0xabcdef00|packed(d);
        unsigned keep=0x2700|(nv&1?F_N:0)|(nv&2?F_V:0);
        c.sr=keep|(x?F_X:0)|(oldz?F_Z:0);
        translated_step(&c); assert(!c.fault);
        int decimal=sub?(int)d-(int)s-(int)x:(int)d+(int)s+(int)x;
        unsigned carry=decimal<0||decimal>=100;
        unsigned result=packed((unsigned)((decimal+100)%100));
        assert(c.d[0]==(0x12345600|packed(s)) && c.d[1]==(0xabcdef00|result));
        assert(c.sr==(keep|(carry?F_C|F_X:0)|(oldz&&result==0?F_Z:0)));
    }
    for (unsigned d=0;d<100;++d) for (unsigned x=0;x<2;++x) {
        c.pc=0x208; c.d[1]=0xabcdef00|packed(d); c.sr=0x2704|(x?F_X:0);
        translated_step(&c); assert(!c.fault);
        unsigned result=packed((100-d-x)%100);
        assert(c.d[1]==(0xabcdef00|result));
        assert(c.sr==(0x2700|(d+x?F_C|F_X:0)|(result==0?F_Z:0)));
    }
    return 0;
}
'''
        exe=self.compile('#define GENESIS_NO_MAIN\n'+emit(p)+harness)
        result=subprocess.run([str(exe)],capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stderr)

    def test_predecrement_multibyte_carry_borrow_and_sticky_zero(self):
        for opcode,dst,src,expected,flags in [('c509','99999999','00000001','00000000',0x15),
                                              ('8509','00000000','00000001','99999999',0x11)]:
            p=analyze(rom_with((opcode+' ')*4+'4e75'),[0x200])
            harness=f'''
#include <assert.h>
int main(void) {{
    CPU c={{0}}; c.rom=rom_data; c.rom_size=sizeof rom_data; c.sr=0x2704;
    write_mem(&c,0xff0100,4,0x{src}); write_mem(&c,0xff0200,4,0x{dst});
    c.a[1]=0xff0104; c.a[2]=0xff0204; c.pc=0x200;
    for (unsigned n=0;n<4;n++) translated_step(&c);
    assert(!c.fault && read_mem(&c,0xff0200,4)==0x{expected});
    assert(c.a[1]==0xff0100 && c.a[2]==0xff0200 && c.sr==0x{0x2700|flags:04x});
    return 0;
}}
'''
            result=subprocess.run([str(self.compile('#define GENESIS_NO_MAIN\n'+emit(p)+harness))],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)

    def test_a7_aliasing_and_nbcd_postincrement(self):
        p=analyze(rom_with('cf0f 4818 4e75'),[0x200])
        harness=r'''
#include <assert.h>
int main(void) {
    CPU c={0}; c.rom=rom_data; c.rom_size=sizeof rom_data; c.sr=0x2704;
    c.a[7]=0xff0104; write_mem(&c,0xff0102,1,0x09); write_mem(&c,0xff0100,1,0x91);
    c.pc=0x200; translated_step(&c);
    assert(!c.fault && c.a[7]==0xff0100 && read_mem(&c,0xff0100,1)==0);
    assert(c.sr==0x2715); c.a[0]=0xff0200;
    write_mem(&c,0xff0200,1,0x49); translated_step(&c);
    assert(!c.fault && c.a[0]==0xff0201 && read_mem(&c,0xff0200,1)==0x50 && c.sr==0x2711);
    return 0;
}
'''
        result=subprocess.run([str(self.compile('#define GENESIS_NO_MAIN\n'+emit(p)+harness))],capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stderr)

    def test_non_decimal_byte_vectors_checked_against_musashi(self):
        # Musashi m68k_in.c ABCD/SBCD/NBCD handlers; compare result and X/C/Z,
        # excluding the architecturally undefined N/V bits.
        p=analyze(rom_with('c300 4e75 8300 4e75 4801 4e75'),[0x200,0x204,0x208])
        harness=r'''
#include <assert.h>
int main(void) {
    const unsigned vectors[][6]={
        {0x200,0xff,0xff,0x14,0x65,0x11},
        {0x204,0x00,0xff,0x04,0x9b,0x11},
        {0x208,0x0f,0x00,0x14,0x90,0x11},
        {0x208,0xff,0x00,0x14,0xff,0x04}
    };
    CPU c={0}; c.rom=rom_data; c.rom_size=sizeof rom_data;
    for (unsigned n=0;n<sizeof vectors/sizeof vectors[0];n++) {
        c.pc=vectors[n][0]; c.d[1]=0x12345600|vectors[n][1]; c.d[0]=vectors[n][2];
        c.sr=0x2700|vectors[n][3]; translated_step(&c);
        assert(!c.fault && c.d[1]==(0x12345600|vectors[n][4]));
        assert((c.sr&21)==vectors[n][5]);
    }
    return 0;
}
'''
        result=subprocess.run([str(self.compile('#define GENESIS_NO_MAIN\n'+emit(p)+harness))],capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stderr)
