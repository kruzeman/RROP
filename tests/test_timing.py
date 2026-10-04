import subprocess
import unittest
from genesis_recompiler.cycles import instruction_cycles
from genesis_recompiler.decode import Decoder, analyze
from genesis_recompiler.emit import emit
from support import CompiledTestCase, rom_with


class CycleTests(unittest.TestCase):
    def cycles(self, code):
        return instruction_cycles(Decoder(bytes.fromhex(code),0).decode())

    def test_instruction_and_effective_address_costs(self):
        for code,cycles in [('4e71',4),('7001',4),('3039 00c00004',16),('23fc 12345678 00c00000',28),('41f9 00001000',12),('4eb9 00001000',20),('4e73',20),('48e7 c080',32)]:
            with self.subTest(code=code): self.assertEqual(self.cycles(code),str(cycles))

    def test_branch_dbcc_and_shift_are_runtime_expressions(self):
        self.assertIn('condition',self.cycles('6602'))
        self.assertIn('12',self.cycles('6600 0002'))
        self.assertIn('0xffff',self.cycles('51c8 fffc'))
        self.assertIn('c->d[1]',self.cycles('e368'))


class TimingTests(CompiledTestCase):
    def check(self, body, code='4e72 2700', zprogram=None, entries=(), extra=b''):
        rom=bytearray(rom_with(code))
        if extra: rom[0x300:0x300+len(extra)]=extra
        program=analyze(bytes(rom),[0x200,*entries])
        self.assertEqual(program.errors,{})
        source='#define GENESIS_NO_MAIN\n'+emit(program,zprogram)+'''
#include <assert.h>
int main(void) {
 CPU c={0}; c.rom=rom_data; c.rom_size=sizeof rom_data;
 c.sr=0x2700; c.a[7]=0xffff00; c.ssp=c.a[7]; c.pc=0x200;
'''+body+'\nreturn 0; }\n'
        exe=self.compile(source)
        result=subprocess.run([str(exe)],capture_output=True,text=True,timeout=10)
        self.assertEqual(result.returncode,0,result.stderr)

    def test_instruction_loop_cycles_and_master_divider(self):
        self.check('''
 while (!c.halted && !c.fault) machine_step(&c);
 assert(c.steps==9 && c.cycles==58 && c.master_cycles==406);
 assert(c.z80_divider==1 && c.vdp.line_clock==406 && c.d[1]==3);
''',code='7002 7200 5241 51c8 fffc 4e72 2700')

    def test_vblank_active_lines_frame_wrap_and_display_disable(self):
        self.check('''
 assert(read_mem(&c,0xc00004,2)&8); c.vdp.registers[1]=0x40;
 assert(!(read_mem(&c,0xc00004,2)&8));
 vdp_advance(&c,224*3420-1); assert(c.vdp.line==223 && !vdp_vblank(&c.vdp));
 vdp_advance(&c,1); assert(c.vdp.line==224 && vdp_vblank(&c.vdp));
 assert(!c.vdp.irq_v && !c.vdp.vint_status);
 vdp_advance(&c,769); assert(!c.vdp.irq_v); vdp_advance(&c,1);
 assert(c.vdp.irq_v && c.vdp.vint_status);
 assert(read_mem(&c,0xc00004,2)&0x80); assert(read_mem(&c,0xc00004,2)&0x80);
 vdp_irq_ack(&c.vdp,6); assert(!(read_mem(&c,0xc00004,2)&0x80));
 vdp_advance(&c,38*3420-770); assert(c.vdp.frames==1 && c.vdp.line==0);
 c.vdp.registers[1]=0x48; vdp_advance(&c,239*3420); assert(!vdp_vblank(&c.vdp));
 vdp_advance(&c,3420); assert(vdp_vblank(&c.vdp));
''')

    def test_status_read_sees_vint_before_next_instruction_irq_ack(self):
        self.check('''
 c.vdp.registers[1]=0x60; c.vdp.registers[12]=1;
 c.vdp.line=224; c.vdp.line_clock=787;
 assert(!c.vdp.irq_v && !(read_mem(&c,0xc00004,2)&0x80));
 c.instruction_cycles=16;
 assert(read_mem(&c,0xc00004,2)&0x80);
 assert(!c.vdp.irq_v && !c.vdp.vint_status);
 c.instruction_cycles=0; vdp_advance(&c,1);
 assert(c.vdp.irq_v && c.vdp.vint_status);
 vdp_irq_ack(&c.vdp,6); assert(!(read_mem(&c,0xc00004,2)&0x80));
 vdp_advance(&c,100); assert(!c.vdp.irq_v && !c.vdp.vint_status);
''')

    def test_pal_version_status_frame_length_and_vertical_counter(self):
        self.check('''
 c.vdp.pal=1;c.vdp.registers[1]=0x40;
 assert(io_read(&c,0)==0xe1 && (read_mem(&c,0xc00004,2)&1));
 assert(vdp_master_frequency(&c.vdp)==53203424 && vdp_frame_lines(&c.vdp)==313);
 vdp_advance(&c,313*3420-1);assert(c.vdp.frames==0 && c.vdp.line==312);
 assert((vdp_counter(&c.vdp)>>8)==0xff);vdp_advance(&c,1);
 assert(c.vdp.frames==1 && c.vdp.line==0);
 c.vdp.line=258;assert((vdp_counter(&c.vdp)>>8)==2);
 c.vdp.line=259;assert((vdp_counter(&c.vdp)>>8)==0xca);
 c.vdp.registers[1]=0x48;c.vdp.line=266;assert((vdp_counter(&c.vdp)>>8)==0x0a);
 c.vdp.line=267;assert((vdp_counter(&c.vdp)>>8)==0xd2);
''')

    def test_counters_ntsc_discontinuity_and_horizontal_blank(self):
        self.check('''
 c.vdp.line=234; assert((read_mem(&c,0xc00008,2)>>8)==0xea);
 vdp_advance(&c,3420); assert((read_mem(&c,0xc0000c,2)>>8)==0xe5);
 c.vdp.line=261; assert((read_mem(&c,0xc00008,2)>>8)==0xff);
 c.vdp.line=0; c.vdp.line_clock=147*20; assert((vdp_counter(&c.vdp)&255)==0x93);
 vdp_advance(&c,20); assert((vdp_counter(&c.vdp)&255)==0xe9);
 c.vdp.line_clock=2559; assert(!vdp_hblank(&c.vdp)); vdp_advance(&c,1);
 assert(read_mem(&c,0xc00004,2)&4);
''')

    def test_irq_priority_masks_ack_and_stack_frame(self):
        self.check('''
 c.vdp.registers[0]=0x10; c.vdp.registers[1]=0x20;
 c.vdp.irq_h=c.vdp.irq_v=1; c.sr=0x2505; c.pc=0x234;
 uint8_t mutable_rom[1024]; memcpy(mutable_rom,rom_data,sizeof mutable_rom);
 mutable_rom[0x78]=0; mutable_rom[0x79]=0; mutable_rom[0x7a]=3; mutable_rom[0x7b]=0;
 c.rom=mutable_rom;
 assert(machine_interrupt(&c)); assert(!c.fault && c.pc==0x300 && c.sr==0x2605);
 assert(c.a[7]==0xfffefa && read_mem(&c,c.a[7],2)==0x2505);
 assert(read_mem(&c,c.a[7]+2,4)==0x234 && c.cycles==44);
 assert(!c.vdp.irq_v && c.vdp.irq_h && c.interrupts==1);
 assert(!machine_interrupt(&c)); translated_step(&c);
 assert(c.pc==0x234 && c.sr==0x2505 && c.a[7]==0xffff00);
''',entries=(0x300,),extra=bytes.fromhex('4e73'))

    def test_interrupt_switches_from_user_stack_and_rte_restores_it(self):
        self.check('''
 uint8_t mutable_rom[1024]; memcpy(mutable_rom,rom_data,sizeof mutable_rom);
 mutable_rom[0x7a]=3; c.rom=mutable_rom;
 c.sr=5; c.a[7]=0xffe000; c.ssp=0xfff000;
 c.vdp.registers[1]=0x20; c.vdp.irq_v=1;
 assert(machine_interrupt(&c)); assert(c.usp==0xffe000 && c.a[7]==0xffeffa);
 translated_step(&c); assert(c.a[7]==0xffe000 && c.ssp==0xfff000 && c.sr==5);
''',entries=(0x300,),extra=bytes.fromhex('4e73'))

    def test_horizontal_counter_reload_and_pending_disabled_interrupt(self):
        self.check('''
 c.vdp.registers[10]=2; c.vdp.hint_counter=2;
 vdp_advance(&c,2*3420); assert(!c.vdp.irq_h);
 vdp_advance(&c,3420); assert(c.vdp.irq_h && c.vdp.hint_counter==2);
 assert(vdp_irq_level(&c.vdp)==0); c.vdp.registers[0]=0x10;
 assert(vdp_irq_level(&c.vdp)==4); vdp_irq_ack(&c.vdp,4);
 assert(vdp_irq_level(&c.vdp)==0);
''')

    def test_stop_wakes_with_vdp_interrupt(self):
        self.check('''
 c.vdp.registers[1]=0x60;
 uint8_t mutable_rom[1024]; memcpy(mutable_rom,rom_data,sizeof mutable_rom);
 mutable_rom[0x7a]=3; c.rom=mutable_rom;
 machine_step(&c); assert(c.halted && c.pc==0x204 && machine_can_wake(&c));
 for(unsigned i=0;i<30000 && c.halted;++i) machine_step(&c);
 assert(!c.halted && c.pc==0x300 && c.interrupts==1 && c.steps==1);
 machine_step(&c); machine_step(&c); machine_step(&c); machine_step(&c);
 assert(!c.fault && c.halted && c.d[0]==1 && c.d[1]==1 && !machine_can_wake(&c));
''',code='4e72 2300 7001 4e72 2700',entries=(0x300,),extra=bytes.fromhex('5281 4e73'))

    def test_z80_uses_master_clock_division(self):
        from genesis_recompiler.z80 import analyze_z80
        self.check('''
 c.z80_bus.reset_released=1; memcpy(c.z80_bus.ram,"\\x00\\x18\\xfd",3);
 machine_advance(&c,15); assert(c.master_cycles==105 && c.z80_divider==0);
 assert(c.z80_cpu.steps==2 && c.z80_cpu.cycles==16 && c.z80_cpu.debt==-9);
 machine_advance(&c,15); assert(c.z80_cpu.steps==2 && c.z80_cpu.debt==-2);
 machine_advance(&c,15); assert(c.z80_cpu.steps==4 && c.z80_cpu.cycles==32);
''',zprogram=analyze_z80([bytes.fromhex('00 18 fd')]))

    def test_instruction_budget_at_wakeable_stop_returns_budget(self):
        result=self.execute(rom_with('33fc 8164 00c00004 4e72 2300 4e72 2700'),['--limit','2'])
        self.assertEqual(result.returncode,2,result.stderr)
        self.assertIn('status=budget steps=2',result.stdout)
