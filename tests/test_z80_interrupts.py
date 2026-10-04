"""Z80 VDP interrupts: vectors, bus ownership, real stacks and EI/HALT timing."""
import subprocess
from genesis_recompiler.decode import analyze
from genesis_recompiler.emit import emit
from genesis_recompiler.z80 import analyze_z80
from support import CompiledTestCase, rom_with


class Z80InterruptTests(CompiledTestCase):
    def check(self,body,code='fb 3e 12 76',handler='fb c9',entries=(0x38,)):
        image=bytearray(b'\x76'*0x300)
        raw=bytes.fromhex(code);image[:len(raw)]=raw
        raw=bytes.fromhex(handler);image[0x38:0x38+len(raw)]=raw
        p=analyze_z80([bytes(image)],entries=entries)
        self.assertEqual(p.errors,[])
        source='#define GENESIS_NO_MAIN\n'+emit(analyze(rom_with('4e72 2700'),[0x200]),p)+'''
#include <assert.h>
int main(void){
 CPU c={0};c.rom=rom_data;c.rom_size=sizeof rom_data;
 const uint8_t image[]={'''+','.join(str(b) for b in image)+'''};
 memcpy(c.z80_bus.ram,image,sizeof image);c.z80_bus.reset_released=1;
 Z80CPU*z=&c.z80_cpu;z->sp=0x1000;
'''+body+'\nreturn 0;}\n'
        result=subprocess.run([str(self.compile(source))],capture_output=True,text=True,timeout=10)
        self.assertEqual(result.returncode,0,result.stderr)

    def test_ei_delays_one_instruction_and_im1_saves_real_pc(self):
        self.check('''
 z->irq_line=1;z->im=1;
 z80_tick(&c,4);assert(!c.fault && z->pc==1 && z->ei_delay==1 && z->interrupts==0);
 z80_tick(&c,7);assert(z->pc==3 && z->a==0x12 && z->ei_delay==0 && z->steps==2);
 z80_tick(&c,13);assert(!c.fault && z->pc==0x38 && z->interrupts==1 && z->cycles==24);
 assert(!z->iff1 && !z->iff2 && z->sp==0xffe && z->wz==0x38 && z->r==3);
 assert(c.z80_bus.ram[0xffe]==3 && c.z80_bus.ram[0xfff]==0);
 assert(z->irq_line==1);z->irq_line=0;
 z80_tick(&c,4);assert(z->ei_delay==1 && z->iff1 && z->iff2);
 z80_tick(&c,10);assert(z->pc==3 && z->sp==0x1000 && !z->ei_delay);
 z80_tick(&c,4);assert(z->halted && z->pc==4 && z->interrupts==1);
''')

    def test_di_cancels_ei_delay_and_pending_interrupt(self):
        self.check('''
 z->irq_line=1;z80_tick(&c,4);assert(z->ei_delay==1);
 z80_tick(&c,4);assert(!z->iff1 && !z->iff2 && !z->ei_delay);
 z80_tick(&c,20);assert(!c.fault && z->halted && !z->interrupts);
''',code='fb f3 76')

    def test_im0_rst_ff_and_halt_wake_resume_after_halt(self):
        self.check('''
 z80_tick(&c,8);assert(z->halted && z->pc==2 && !z->ei_delay);
 z->irq_line=1;z80_tick(&c,13);assert(!z->halted && z->pc==0x38 && z->interrupts==1);
 assert(c.z80_bus.ram[0xffe]==2);z->irq_line=0;
 z80_tick(&c,14);assert(z->pc==2 && z->sp==0x1000);
 z80_tick(&c,7);assert(z->a==0x42 && z->pc==4);
''',code='fb 76 3e 42 76',entries=(0x38,2))

    def test_im2_uses_little_endian_ff_vector_and_costs_19_cycles(self):
        self.check('''
 z->iff1=z->iff2=1;z->im=2;z->i=1;z->irq_line=1;
 c.z80_bus.ram[0x1ff]=0x38;c.z80_bus.ram[0x200]=0;
 z80_tick(&c,19);assert(!c.fault && z->pc==0x38 && z->cycles==19 && z->steps==0);
 assert(z->sp==0xffe && z->wz==0x38 && z->interrupts==1);
 z->irq_line=0;z80_tick(&c,14);assert(z->pc==0 && z->sp==0x1000 && !z->iff1);
''',handler='ed 4d')

    def test_interrupt_respects_bus_reset_and_byte_guards(self):
        self.check('''
 z->iff1=z->iff2=1;z->irq_line=1;c.z80_bus.requested=1;
 z80_tick(&c,100);assert(z->steps==0 && z->cycles==0 && z->interrupts==0);
 c.z80_bus.requested=0;c.z80_bus.reset_released=0;
 z80_tick(&c,100);assert(z->interrupts==0);
 c.z80_bus.reset_released=1;z80_reset(&c);assert(z->irq_line==1 && !z->iff1 && !z->ei_delay);
 z->iff1=z->iff2=1;c.z80_bus.ram[0x38]=0;
 z80_tick(&c,14);assert(c.fault && z->interrupts==1 && c.fault_address==0xa00038);
''')

    def test_missing_handler_is_not_interpreted_or_silently_skipped(self):
        self.check('''
 z->iff1=z->iff2=1;z->irq_line=1;z80_tick(&c,14);
 assert(c.fault && z->interrupts==1 && c.fault_address==0xa00038);
''',entries=())

    def test_vdp_irq_pulse_is_independent_of_68000_enable_and_ack(self):
        self.check('''
 for(unsigned pal=0;pal<2;++pal)for(unsigned mode=0;mode<2;++mode){
  memset(&c.vdp,0,sizeof c.vdp);c.vdp.pal=(uint8_t)pal;c.vdp.registers[12]=(uint8_t)mode;
  z->irq_line=0;unsigned start=vdp_visible_lines(&c.vdp)*3420+vdp_vint_clock(&c.vdp);
  vdp_advance(&c,start-1);assert(!z->irq_line);
  vdp_advance(&c,1);assert(z->irq_line && c.vdp.irq_v && vdp_irq_level(&c.vdp)==0);
  vdp_irq_ack(&c.vdp,6);assert(z->irq_line);
  unsigned remaining=3420-c.vdp.line_clock;
  vdp_advance(&c,remaining-1);assert(z->irq_line);
  vdp_advance(&c,1);assert(!z->irq_line && c.vdp.line==225);
 }
''')
