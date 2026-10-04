import subprocess
from genesis_recompiler.decode import analyze
from genesis_recompiler.emit import emit
from support import CompiledTestCase, rom_with

BUS_HELPERS='''
static void lines(CPU *c, unsigned clock, unsigned data) {
 write_mem(c,0x200000,2,(clock?0x40:0)|(data?0x80:0)); assert(!c->fault);
}
static void start(CPU *c) { lines(c,0,1); lines(c,1,1); lines(c,1,0); lines(c,0,0); }
static void stop(CPU *c) { lines(c,0,0); lines(c,1,0); lines(c,1,1); }
static void send(CPU *c, unsigned byte) {
 for (unsigned i=0;i<8;++i) { unsigned b=(byte>>(7-i))&1; lines(c,0,b); lines(c,1,b); lines(c,0,b); }
 lines(c,0,1); lines(c,1,1);
 assert(read_mem(c,0x200000,2)==0); /* device ACK, host released SDA */
 lines(c,0,1);
}
static unsigned receive(CPU *c, unsigned acknowledge) {
 unsigned result=0;
 for (unsigned i=0;i<8;++i) { lines(c,0,1); lines(c,1,1); result=(result<<1)|(read_mem(c,0x200000,2)>>7); lines(c,0,1); }
 lines(c,0,!acknowledge); lines(c,1,!acknowledge); lines(c,0,!acknowledge);
 return result;
}
'''


class EEPROMTests(CompiledTestCase):
    def harness(self, body):
        p=analyze(rom_with('4e72 2700'),[0x200])
        source='#define GENESIS_NO_MAIN\n'+emit(p)+ '\n#include <assert.h>\n'+BUS_HELPERS
        source+='\nint main(void) { CPU c={0}; c.rom=rom_data; c.rom_size=sizeof rom_data; c.eeprom.enabled=1;\n'+body+'\nreturn 0; }\n'
        exe=self.compile(source)
        r=subprocess.run([str(exe)],capture_output=True,text=True,timeout=10)
        self.assertEqual(r.returncode,0,r.stderr)

    def test_erased_data_and_sequential_read_wrap(self):
        self.harness('''
 assert(read_mem(&c,0x200000,2)==0x80); assert(c.eeprom.data[0]==0xff);
 c.eeprom.data[127]=0xa5; c.eeprom.data[0]=0x5a;
 start(&c); send(&c,(127<<1)|1);
 assert(receive(&c,1)==0xa5); assert(receive(&c,0)==0x5a); stop(&c);
 assert(c.eeprom.starts==1 && c.eeprom.reads==2 && c.eeprom.stops==1);
''')

    def test_page_write_commits_on_stop_and_wraps_four_bytes(self):
        self.harness('''
 start(&c); send(&c,3<<1); send(&c,0x12); send(&c,0x34);
 assert(c.eeprom.data[3]==0xff && c.eeprom.data[0]==0xff);
 stop(&c); assert(c.eeprom.data[3]==0x12 && c.eeprom.data[0]==0x34);
 assert(c.eeprom.data[4]==0xff && c.eeprom.writes==2);
 start(&c); send(&c,3*2+1); assert(receive(&c,0)==0x12); stop(&c);
''')

    def test_repeated_start_and_nack_wait(self):
        self.harness('''
 eeprom_init(&c); c.eeprom.data[7]=0x81;
 start(&c); send(&c,0); start(&c); send(&c,7*2+1);
 assert(receive(&c,0)==0x81 && c.eeprom.phase==EE_WAIT);
 lines(&c,0,1); lines(&c,1,1); assert(read_mem(&c,0x200000,2)==0x80);
 stop(&c); assert(c.eeprom.phase==EE_IDLE && c.eeprom.starts==2);
''')

    def test_bus_widths_and_unselected_profile_fault(self):
        self.harness('''
 write_mem(&c,0x200000,1,0); assert(c.eeprom.initialized==0);
 write_mem(&c,0x200001,1,0x80); assert(c.eeprom.initialized);
 assert(read_mem(&c,0x200000,1)==0 && read_mem(&c,0x200001,1)==0x80);
 c.eeprom.enabled=0; read_mem(&c,0x200000,2); assert(c.fault);
''')
