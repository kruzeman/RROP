import subprocess
from support import CompiledTestCase, rom_with
from genesis_recompiler.decode import analyze
from genesis_recompiler.emit import emit


class VDPTests(CompiledTestCase):
    def check(self, body):
        program = analyze(rom_with("4e72 2700"), [0x200])
        harness = '''
#include <assert.h>
static void command(CPU *c, unsigned address, unsigned code) {
    uint32_t words=((address&0x3fff)|((code&3)<<14))<<16;
    words|=((address>>14)&3)|((code&0x3c)<<2);
    write_mem(c,0xc00004,4,words);
}
static void reg(CPU *c, unsigned number, unsigned value) {
    write_mem(c,0xc00004,2,0x8000|(number<<8)|value);
}
int main(void) {
    CPU c={0}; c.rom=rom_data; c.rom_size=sizeof rom_data;
''' + body + '\nreturn 0;\n}\n'
        exe = self.compile("#define GENESIS_NO_MAIN\n" + emit(program) + harness)
        result = subprocess.run([str(exe)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_vram_long_bus_access_and_port_mirrors(self):
        self.check('''
reg(&c,15,2); command(&c,0x20,1);
write_mem(&c,0xc00000,4,0x12345678);
assert(!c.fault && c.vdp.address==0x24 && c.vdp.data_writes==2);
assert(c.vdp.vram[0x20]==0x12 && c.vdp.vram[0x23]==0x78);
command(&c,0x20,0); assert(read_mem(&c,0xc00000,4)==0x12345678);
command(&c,0x20,0); assert(read_mem(&c,0xc00002,2)==0x1234);
assert(c.vdp.address==0x22 && c.vdp.data_reads==3);
''')

    def test_vram_address_wrap_and_odd_word_byte_lanes(self):
        self.check('''
reg(&c,15,2); command(&c,0xffff,1);
write_mem(&c,0xc00000,2,0x1234);
assert(c.vdp.vram[0xffff]==0x12 && c.vdp.vram[0xfffe]==0x34);
assert(c.vdp.address==1);
write_mem(&c,0xc00000,2,0x5678);
assert(c.vdp.vram[1]==0x56 && c.vdp.vram[0]==0x78);
command(&c,0xffff,0); assert(read_mem(&c,0xc00000,2)==0x3412);
assert(!c.fault);
''')

    def test_cram_and_vsram_masks_and_autoincrement(self):
        self.check('''
reg(&c,15,2); command(&c,0x7e,3);
write_mem(&c,0xc00000,4,0xffff1234);
assert(c.vdp.cram[63]==0xeee && c.vdp.cram[0]==0x224);
command(&c,0x7e,8); assert(read_mem(&c,0xc00000,2)==0xeee);
command(&c,0,5); write_mem(&c,0xc00000,4,0xffff1234);
assert(c.vdp.vsram[0]==0x7ff && c.vdp.vsram[1]==0x234);
command(&c,0,4); assert(read_mem(&c,0xc00000,4)==0x07ff0234);
command(&c,80,5); write_mem(&c,0xc00000,2,0xffff);
assert(!c.fault);
''')

    def test_partial_command_cancelled_by_status_and_data(self):
        self.check('''
reg(&c,15,2);
write_mem(&c,0xc00004,2,0x4010); assert(c.vdp.command_pending);
uint32_t status=read_mem(&c,0xc00006,2);
assert((status&0x300)==0x200 && !c.vdp.command_pending);
reg(&c,15,4); assert(c.vdp.registers[15]==4);
write_mem(&c,0xc00004,2,0x4020); assert(c.vdp.command_pending);
write_mem(&c,0xc00000,2,0xabcd); assert(!c.vdp.command_pending);
assert(c.vdp.vram[0x20]==0xab && c.vdp.address==0x24);
assert(!c.fault);
''')

    def test_byte_write_replicates_on_vdp_bus(self):
        self.check('''
reg(&c,15,2); command(&c,0,1);
write_mem(&c,0xc00001,1,0xab);
assert(c.vdp.vram[0]==0xab && c.vdp.vram[1]==0xab);
assert(c.vdp.address==2 && c.vdp.data_writes==1);
assert(!c.fault);
''')

    def test_cpu_dma_rom_and_ram_sources(self):
        self.check('''
reg(&c,1,0x10); reg(&c,15,2);
reg(&c,19,3); reg(&c,20,0); reg(&c,21,0); reg(&c,22,0); reg(&c,23,0);
command(&c,0x100,0x21);
for (unsigned i=0;i<6;++i) assert(c.vdp.vram[0x100+i]==rom_data[i]);
assert(c.vdp.address==0x106 && c.vdp.dma_bytes==6);
assert(c.vdp.registers[19]==0 && c.vdp.registers[21]==3);
write_mem(&c,0xff0000,4,0x1234abcd);
reg(&c,19,2); reg(&c,21,0); reg(&c,22,0x80); reg(&c,23,0x7f);
command(&c,0x200,0x21);
assert(c.vdp.vram[0x200]==0x12 && c.vdp.vram[0x203]==0xcd);
assert(c.vdp.dma_bytes==10 && !c.fault);
''')

    def test_cpu_dma_wraps_128k_source_bank(self):
        self.check('''
reg(&c,1,0x10); reg(&c,15,2);
write_mem(&c,0xe1fffe,2,0x1122); write_mem(&c,0xe00000,2,0x3344);
reg(&c,19,2); reg(&c,21,0xff); reg(&c,22,0xff); reg(&c,23,0x70);
command(&c,0,0x21);
assert(c.vdp.vram[0]==0x11 && c.vdp.vram[1]==0x22);
assert(c.vdp.vram[2]==0x33 && c.vdp.vram[3]==0x44);
assert(c.vdp.registers[21]==1 && c.vdp.registers[22]==0);
assert(c.vdp.registers[23]==0x70 && !c.fault);
''')

    def test_dma_disabled_does_not_transfer(self):
        self.check('''
reg(&c,15,2); reg(&c,19,3); command(&c,0,0x21);
assert(c.vdp.dma_bytes==0 && c.vdp.registers[19]==3);
write_mem(&c,0xc00000,2,0xabcd);
assert(c.vdp.vram[0]==0xab && c.vdp.vram[1]==0xcd && !c.fault);
''')

    def test_dma_fill_waits_for_data_and_full_clear(self):
        self.check('''
memset(c.vdp.vram,0xa5,sizeof c.vdp.vram);
reg(&c,1,0x10); reg(&c,15,1); reg(&c,19,0xff); reg(&c,20,0xff); reg(&c,23,0x80);
command(&c,0,0x21);
assert(c.vdp.fill_pending && c.vdp.vram[100]==0xa5);
write_mem(&c,0xc00000,2,0);
for (unsigned i=0;i<65536;++i) assert(c.vdp.vram[i]==0);
assert(!c.vdp.fill_pending && c.vdp.registers[19]==0 && c.vdp.registers[20]==0);
assert(c.vdp.dma_bytes==65535 && c.vdp.data_writes==1 && !c.fault);
''')

    def test_dma_length_zero_means_65536(self):
        self.check('''
reg(&c,1,0x10); reg(&c,15,1); reg(&c,19,0); reg(&c,20,0); reg(&c,23,0x80);
command(&c,0,0x21); write_mem(&c,0xc00000,2,0xabab);
for (unsigned i=0;i<65536;++i) assert(c.vdp.vram[i]==0xab);
assert(c.vdp.dma_bytes==65536 && !c.fault);
''')

    def test_dma_copy_is_sequential_and_overlaps(self):
        self.check('''
for (unsigned i=0;i<16;++i) c.vdp.vram[i]=(uint8_t)(i+1);
reg(&c,1,0x10); reg(&c,15,1); reg(&c,19,4); reg(&c,21,0); reg(&c,22,0); reg(&c,23,0xc0);
command(&c,8,0x21);
for (unsigned i=0;i<4;++i) assert(c.vdp.vram[(8+i)^1]==c.vdp.vram[i^1]);
assert(c.vdp.dma_bytes==4 && c.vdp.registers[21]==4);
c.vdp.vram[0]=0xab; c.vdp.vram[1]=0xcd;
reg(&c,19,4); reg(&c,21,0); command(&c,2,0x21);
for (unsigned i=1;i<=5;i+=2) assert(c.vdp.vram[i]==0xcd);
assert(!c.fault);
''')

    def test_cpu_dma_fault_on_unmapped_source(self):
        self.check('''
reg(&c,1,0x10); reg(&c,15,2); reg(&c,19,1);
reg(&c,21,0); reg(&c,22,0); reg(&c,23,0x20);
command(&c,0,0x21);
assert(c.fault && c.fault_address==0x400000 && c.vdp.dma_bytes==0);
''')

    def test_translated_cpu_vdp_roundtrip_and_dump(self):
        dump=self.root/'vram.bin'
        code = "33fc 8f02 00c00004 23fc 40200000 00c00004 23fc 12345678 00c00000 23fc 00200000 00c00004 2039 00c00000 4e72 2700"
        result=self.execute(rom_with(code),['--dump-vram',str(dump)])
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertIn('D0=12345678',result.stdout)
        data=dump.read_bytes()
        self.assertEqual(len(data),65536)
        self.assertEqual(data[0x20:0x24],bytes.fromhex('12345678'))
