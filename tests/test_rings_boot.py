"""Optional local game regression. CI and the source repo do not contain ROMs."""
import hashlib
from pathlib import Path
import subprocess
import unittest
from support import CompiledTestCase
from genesis_recompiler.decode import Decoder, Program, analyze
from genesis_recompiler.emit import emit
from genesis_recompiler.z80 import analyze_z80

ROM=Path(__file__).resolve().parents[1]/'build/rings-of-power/Rings of Power (UE) [!].gen'


class RingsBootTests(CompiledTestCase):
    @unittest.skipUnless(ROM.exists(),'user-provided Rings of Power [!] ROM is not present')
    def test_selected_rom_initialization_and_next_execution_blocker(self):
        rom=ROM.read_bytes()
        self.assertEqual(hashlib.sha256(rom).hexdigest(),'36303fc447c433ebc69c3d4df86c783c86b383e0acead1c19595f13269e248f5')
        program=Program(rom)
        # Only compile the linear reset routine for this targeted regression;
        # the normal CLI still compiles the entire discovered game graph.
        pc=0x200
        while pc<0x28c:
            inst=Decoder(rom,pc).decode()
            program.instructions[pc]=inst
            pc=inst.end
        harness='''
#include <assert.h>
int main(void) {
    CPU c={0}; c.rom=rom_data; c.rom_size=sizeof rom_data; c.sr=0x2700;
    c.a[7]=read_mem(&c,0,4); c.pc=read_mem(&c,4,4);
    memset(c.vdp.vram,0xa5,sizeof c.vdp.vram);
    memset(c.vdp.cram,0xa5,sizeof c.vdp.cram);
    memset(c.vdp.vsram,0xa5,sizeof c.vdp.vsram);
    memset(c.ram,0xa5,sizeof c.ram);
    memset(c.z80_bus.ram,0xa5,sizeof c.z80_bus.ram);
    while (!c.fault && !c.halted && c.steps<100000) machine_step(&c);
    assert(c.fault && c.steps==33088 && c.pc==0x28c && c.fault_address==0x28c);
    assert(strstr(c.reason,"PC has no translated instruction"));
    assert(c.vdp.registers[0]==4 && c.vdp.registers[1]==4 && c.vdp.registers[15]==2);
    assert(c.vdp.data_writes==105 && c.vdp.dma_bytes==65535);
    for (unsigned i=0;i<65536;++i) assert(c.vdp.vram[i]==0);
    for (unsigned i=0;i<64;++i) assert(c.vdp.cram[i]==0);
    for (unsigned i=0;i<40;++i) assert(c.vdp.vsram[i]==0);
    for (unsigned i=0;i<65536;++i) assert(c.ram[i]==0);
    assert(c.z80_bus.ram_writes==38 && c.z80_bus.ram[0]==0xaf);
    unsigned end=z80_pair(&c,1);
    assert(end>8000 && end<8192);
    for (unsigned i=38;i<end;++i) assert(c.z80_bus.ram[i]==0);
    for (unsigned i=end;i<8192;++i) assert(c.z80_bus.ram[i]==0xa5);
    assert(c.z80_cpu.steps>7900 && c.z80_cpu.sp==0x26 && z80_pair(&c,0)>0);
    assert(c.psg.writes==4);
    for (unsigned i=0;i<4;++i) assert(c.psg.volume[i]==15);
    assert(!c.z80_bus.reset_released && !c.z80_bus.requested);
    assert(!memcmp(c.tmss,"SEGA",4));
    return 0;
}
'''
        zprogram=analyze_z80([rom[0x2c4:0x2ea]],overlays=[(0,b'\xe9')])
        self.assertEqual(zprogram.errors,[])
        exe=self.compile('#define GENESIS_NO_MAIN\n'+emit(program,zprogram)+harness)
        result=subprocess.run([str(exe)],capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stderr)

    @unittest.skipUnless(ROM.exists(),'user-provided Rings of Power [!] ROM is not present')
    def test_game_eeprom_read_routine_and_address_wrap(self):
        program=analyze(ROM.read_bytes(),[0x43012])
        self.assertEqual(program.errors,{})
        harness='''
#include <assert.h>
int main(void) {
    CPU c={0}; c.rom=rom_data; c.rom_size=sizeof rom_data; c.sr=0x2700;
    c.eeprom.enabled=1; eeprom_init(&c);
    c.eeprom.data[126]=0xa5; c.eeprom.data[127]=0x5a; c.eeprom.data[0]=0x42;
    c.pc=0x43012; c.a[7]=0xffec1e; push32(&c,0x400);
    c.d[0]=126; c.d[1]=3; c.a[0]=0xff0200;
    while (!c.fault && c.pc!=0x400 && c.steps<200000) { translated_step(&c); ++c.steps; }
    assert(!c.fault && c.pc==0x400);
    assert(read_mem(&c,0xff0200,1)==0xa5);
    assert(read_mem(&c,0xff0201,1)==0x5a);
    assert(read_mem(&c,0xff0202,1)==0x42);
    assert(read_mem(&c,0xff014e,2)==0 && c.eeprom.reads==3);
    return 0;
}
'''
        exe=self.compile('#define GENESIS_NO_MAIN\n'+emit(program)+harness)
        result=subprocess.run([str(exe)],capture_output=True,text=True,timeout=10)
        self.assertEqual(result.returncode,0,result.stderr)
