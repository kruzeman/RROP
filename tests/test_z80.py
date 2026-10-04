import subprocess
import unittest
from genesis_recompiler.decode import analyze
from genesis_recompiler.emit import emit
from genesis_recompiler.z80 import ZDecoder, analyze_z80
from support import CompiledTestCase, rom_with


class Z80DecodeTests(unittest.TestCase):
    def test_image_specific_entry_does_not_decode_other_images_padding(self):
        p=analyze_z80([bytes.fromhex('76'),bytes.fromhex('76 00 00 3e 12 76')],image_entries=[(1,3)])
        self.assertEqual(p.errors,[])
        self.assertEqual(set(p.instructions),{0,3,5})
        self.assertEqual([i.op for i in p.instructions[3]],['LD8_IMM'])
        for entry in ((2,3),(1,0x4000),(-1,0)):
            with self.assertRaisesRegex(ValueError,'image entry'):
                analyze_z80([b'\x76'],image_entries=[entry])

    def decode(self, code, pc=0):
        return ZDecoder(bytes.fromhex(code).ljust(8192,b'\0'),pc).decode()

    def test_little_endian_immediates_and_index_prefixes(self):
        i=self.decode('dd 21 34 12')
        self.assertEqual((i.op,i.args,i.end,i.cycles),('LD16',(4,0x1234),4,14))
        self.assertEqual(self.decode('fd e1').args,(5,))
        self.assertEqual(self.decode('ed 5f').args,(True,True))
        self.assertEqual(self.decode('ed b8').args,(-1,True))

    def test_relative_branch_targets_and_conditions(self):
        self.assertEqual(self.decode('20 fe').args,(0,0))
        self.assertEqual(self.decode('38 02').successors(),[2,4])
        self.assertEqual(self.decode('18 fe').successors(),[0])
        self.assertEqual(self.decode('10 fc').args,(0xfffe,))

    def test_guarded_overlay_variants_and_overlapping_instruction_streams(self):
        p=analyze_z80([bytes.fromhex('af e9')],overlays=[(0,b'\xe9')])
        self.assertEqual(p.errors,[])
        self.assertEqual([i.raw.hex() for i in p.instructions[0]],['af','e9'])
        self.assertEqual(len(p.instructions[1]),1)
        p=analyze_z80([bytes.fromhex('20 01 01 76 00 76')])
        self.assertEqual(p.errors, [])
        self.assertEqual(p.instructions[2][0].op, 'LD16')
        self.assertEqual(p.instructions[3][0].op, 'HALT')

    def test_mutable_immediate_annotations_validate_instruction_boundaries(self):
        for pc in (1,2,0x4000):
            with self.assertRaisesRegex(ValueError,'mutable Z80 immediate'):
                analyze_z80([bytes.fromhex('3e 00 76')],mutable_immediates=[pc])
        p=analyze_z80([bytes.fromhex('3e 00 76')],mutable_immediates=[0,0])
        self.assertEqual(p.mutable_immediates,(0,))
        self.assertEqual(len(p.instructions[0]),256)


    def test_mutable_displacement_expands_only_indexed_address_byte(self):
        p=analyze_z80([bytes.fromhex('dd 7e 00 76')],mutable_displacements=(0,))
        self.assertEqual(p.errors,[])
        self.assertEqual(len(p.instructions[0]),256)
        self.assertEqual({i.args[1] for i in p.instructions[0]},set(range(-128,128)))
        self.assertTrue(all(i.raw[:2]==bytes.fromhex('dd 7e') for i in p.instructions[0]))
        p=analyze_z80([bytes.fromhex('fd cb 00 46 76')],mutable_displacements=(0,))
        self.assertEqual(len(p.instructions[0]),256)
        self.assertTrue(all(i.raw[3]==0x46 for i in p.instructions[0]))
        for raw,pc in (('76',0),('3e 00 76',0),('dd 21 00 00 76',0),('dd 7e 00 76',1)):
            with self.assertRaisesRegex(ValueError,'mutable Z80 displacement'):
                analyze_z80([bytes.fromhex(raw)],mutable_displacements=(pc,))

    def test_unsupported_and_outside_ram_are_reported(self):
        self.assertIn('unsupported',analyze_z80([bytes.fromhex('ed 00')]).errors[0]['message'])
        self.assertIn('outside',analyze_z80([bytes.fromhex('c3 00 80')]).errors[0]['message'])
        for image in (b'',b'\0'*8193):
            with self.assertRaises(ValueError): analyze_z80([image])


class Z80ExecutionTests(CompiledTestCase):
    def run_harness(self, code, body, overlays=(), entries=(), extra_images=(), mutable_immediates=(), mutable_displacements=()):
        image=bytes.fromhex(code)
        p=analyze_z80([image,*extra_images],entries=entries,overlays=overlays,mutable_immediates=mutable_immediates,mutable_displacements=mutable_displacements)
        self.assertEqual(p.errors,[])
        source=emit(analyze(rom_with('4e72 2700'),[0x200]),p)
        init=','.join(str(b) for b in image)
        harness='''
#include <assert.h>
int main(void) {
 CPU c={0}; c.rom=rom_data; c.rom_size=sizeof rom_data;
 const uint8_t initial[]={'''+init+'''};
 memcpy(c.z80_bus.ram,initial,sizeof initial);
 c.z80_bus.reset_released=1;
'''+body+'''
 return 0;
}
'''
        exe=self.compile('#define GENESIS_NO_MAIN\n'+source+harness)
        result=subprocess.run([str(exe)],capture_output=True,text=True,timeout=10)
        self.assertEqual(result.returncode,0,result.stderr)

    def test_self_modifying_code_uses_explicit_variant(self):
        self.run_harness('21 00 00 36 e9 e9','''
 z80_tick(&c,100); assert(!c.fault);
 assert(c.z80_bus.ram[0]==0xe9 && c.z80_cpu.pc==0);
 assert(c.z80_cpu.cycles==100 && c.z80_cpu.steps==22);
''',overlays=[(0,b'\xe9')])

    def test_mutable_displacement_executes_signed_offsets_and_keeps_opcode_guard(self):
        self.run_harness('dd 7e 00 76', '''
 c.z80_cpu.ix=0x100;c.z80_bus.ram[0x102]=0x42;c.z80_bus.ram[0xff]=0x21;
 c.z80_bus.ram[2]=2;assert(translated_z80_step(&c)==19 && c.z80_cpu.a==0x42);
 c.z80_cpu.pc=0;c.z80_bus.ram[2]=0xff;
 assert(translated_z80_step(&c)==19 && c.z80_cpu.a==0x21 && c.z80_cpu.wz==0xff);
 c.z80_cpu.pc=0;c.z80_bus.ram[1]=0x77;
 assert(translated_z80_step(&c)==0 && c.fault && c.z80_bus.ram[0xff]==0x21);
''',mutable_displacements=(0,))

    def test_overlapping_streams_execute_both_paths_and_keep_byte_guards(self):
        self.run_harness('20 01 01 76 00 76', '''
 c.z80_cpu.f=0; assert(translated_z80_step(&c)==12 && c.z80_cpu.pc==3);
 assert(translated_z80_step(&c)==4 && c.z80_cpu.halted);
 c.z80_cpu.pc=0;c.z80_cpu.halted=0;c.z80_cpu.f=Z_Z;
 assert(translated_z80_step(&c)==7 && c.z80_cpu.pc==2);
 assert(translated_z80_step(&c)==10 && z80_pair(&c,0)==0x76 && c.z80_cpu.pc==5);
 c.z80_cpu.pc=2;c.z80_bus.ram[3]=0;
 assert(translated_z80_step(&c)==0 && c.fault);
''')

    def test_memory_bit_uses_memptr_and_indexed_bit_uses_effective_address(self):
        self.run_harness('21 00 01 cb 7e fd cb ff 47 76', '''
 c.z80_cpu.wz=0x0800;c.z80_cpu.f=0xff;c.z80_bus.ram[0x100]=0x80;
 c.z80_cpu.iy=0x2901;c.z80_bus.ram[0x900]=0;c.z80_cpu.a=0xff;
 assert(translated_z80_step(&c)==10 && c.z80_cpu.wz==0x0800);
 assert(translated_z80_step(&c)==12 && c.z80_cpu.f==(Z_S|Z_H|Z_X|Z_C));
 assert(translated_z80_step(&c)==20 && c.z80_cpu.wz==0x2900);
 assert(c.z80_cpu.f==(Z_H|Z_X|Z_Y|Z_Z|Z_PV|Z_C) && c.z80_cpu.a==0xff);
 assert(c.z80_cpu.r==5 && !c.fault);
''')

    def test_accumulator_rotate_negate_and_carry_flags(self):
        self.run_harness('1f ed 44 37 3f 76', '''
 c.z80_cpu.a=0x81;c.z80_cpu.f=0xff;
 assert(translated_z80_step(&c)==4 && c.z80_cpu.a==0xc0 && c.z80_cpu.f==(Z_S|Z_Z|Z_PV|Z_C));
 c.z80_cpu.a=0x80;
 assert(translated_z80_step(&c)==8 && c.z80_cpu.a==0x80 && c.z80_cpu.f==(Z_S|Z_PV|Z_N|Z_C));
 c.z80_cpu.a=0x28;
 assert(translated_z80_step(&c)==4 && c.z80_cpu.f==(Z_S|Z_PV|Z_X|Z_Y|Z_C));
 assert(translated_z80_step(&c)==4 && c.z80_cpu.f==(Z_S|Z_PV|Z_X|Z_Y|Z_H));
''')

    def test_adc_sbc_hl_pair_flags_cycles_and_memptr(self):
        self.run_harness('ed 4a ed 42 76', '''
 c.z80_cpu.f=Z_C;z80_set_pair(&c,2,0x7fff);z80_set_pair(&c,0,0);
 assert(translated_z80_step(&c)==15 && z80_pair(&c,2)==0x8000);
 assert(c.z80_cpu.f==(Z_S|Z_H|Z_PV) && c.z80_cpu.wz==0x8000);
 z80_set_pair(&c,0,1);
 assert(translated_z80_step(&c)==15 && z80_pair(&c,2)==0x7fff);
 assert(c.z80_cpu.f==(Z_X|Z_Y|Z_H|Z_PV|Z_N) && c.z80_cpu.wz==0x8001);
 c.z80_cpu.pc=0;z80_set_pair(&c,2,0xffff);z80_set_pair(&c,0,0);c.z80_cpu.f=Z_C;
 assert(translated_z80_step(&c)==15 && z80_pair(&c,2)==0 && c.z80_cpu.f==(Z_Z|Z_H|Z_C));
 assert(translated_z80_step(&c)==15 && z80_pair(&c,2)==0xffff && c.z80_cpu.f==(Z_S|Z_X|Z_Y|Z_H|Z_N|Z_C));
''')

    def test_retn_and_reti_restore_iff_and_return_address(self):
        self.run_harness('ed 45', '''
 for(unsigned reti=0;reti<2;reti++){
  c.z80_bus.ram[1]=reti?0x4d:0x45;c.z80_cpu.pc=0;c.z80_cpu.sp=0x200;
  c.z80_bus.ram[0x200]=0x34;c.z80_bus.ram[0x201]=0x12;
  c.z80_cpu.iff1=0;c.z80_cpu.iff2=1;
  assert(translated_z80_step(&c)==14 && c.z80_cpu.pc==0x1234 && c.z80_cpu.wz==0x1234);
  assert(c.z80_cpu.sp==0x202 && c.z80_cpu.iff1 && !c.fault);
 }
''',extra_images=[bytes.fromhex('ed 4d')])

    def test_all_mutable_operand_values_execute_but_opcode_changes_fault(self):
        self.run_harness('3e 00 76', '''
 for(unsigned value=0;value<256;value++){
  c.z80_cpu.pc=0;c.z80_bus.ram[1]=(uint8_t)value;
  assert(translated_z80_step(&c)==7 && c.z80_cpu.a==value && c.z80_cpu.pc==2 && !c.fault);
 }
 c.z80_cpu.pc=0;c.z80_bus.ram[0]=0x06;
 assert(translated_z80_step(&c)==0 && c.fault);
''',mutable_immediates=[0])

    def test_unknown_modification_and_immediate_mismatch_fault(self):
        self.run_harness('21 00 00 36 e9 e9','''
 z80_tick(&c,100); assert(c.fault && c.fault_address==0xa00000);
 assert(strstr(c.reason,"differs from compiled"));
''')
        self.run_harness('3e 12 76','''
 c.z80_bus.ram[1]=0x34; z80_tick(&c,10);
 assert(c.fault && c.z80_cpu.a==0);
''')

    def test_compiled_image_does_not_initialize_ram(self):
        self.run_harness('3e 12 76','''
 memset(c.z80_bus.ram,0,sizeof c.z80_bus.ram); z80_tick(&c,10);
 assert(c.fault && c.z80_cpu.a==0);
''')

    def test_multiple_images_have_guarded_alternatives(self):
        self.run_harness('3e 12 76','''
 c.z80_bus.ram[1]=0x34; z80_tick(&c,7);
 assert(!c.fault && c.z80_cpu.a==0x34 && c.z80_cpu.pc==2);
''',extra_images=[bytes.fromhex('3e 34 76')])

    def test_bus_ownership_freezes_cpu_and_reset_preserves_ram(self):
        self.run_harness('00 18 fd','''
 c.z80_bus.requested=1; z80_tick(&c,20); assert(c.z80_cpu.steps==0);
 z80_bus_write(&c,0xa11100,0); z80_tick(&c,1);
 assert(c.z80_cpu.pc==1 && c.z80_cpu.debt==-3);
 z80_bus_write(&c,0xa11100,1); z80_tick(&c,100);
 assert(c.z80_cpu.pc==1 && c.z80_cpu.debt==-3);
 z80_bus_write(&c,0xa11200,0);
 assert(c.z80_cpu.pc==0 && c.z80_cpu.debt==0 && c.z80_bus.ram[1]==0x18);
 z80_bus_write(&c,0xa11100,0); z80_tick(&c,100); assert(c.z80_cpu.steps==1);
 z80_bus_write(&c,0xa11200,1); z80_tick(&c,4);
 assert(!c.fault && c.z80_cpu.pc==1 && c.z80_cpu.steps==2);
''')

    def test_stack_index_and_call_return(self):
        self.run_harness('31 00 10 dd 21 34 12 dd e5 fd e1 cd 11 00 76 00 00 3e ab c9','''
 z80_tick(&c,100); assert(!c.fault && c.z80_cpu.halted);
 assert(c.z80_cpu.ix==0x1234 && c.z80_cpu.iy==0x1234);
 assert(c.z80_cpu.a==0xab && c.z80_cpu.sp==0x1000);
 assert(c.z80_cpu.pc==15);
''')

    def test_overlapping_ldir_and_cycle_accounting(self):
        self.run_harness('ed b0 76','''
 z80_set_pair(&c,0,3); z80_set_pair(&c,1,0x101); z80_set_pair(&c,2,0x100);
 c.z80_bus.ram[0x100]=0x42; c.z80_cpu.a=1; c.z80_cpu.f=Z_C|Z_Z|Z_S;
 assert(translated_z80_step(&c)==21 && c.z80_cpu.pc==0);
 assert(z80_pair(&c,0)==2 && c.z80_cpu.f==(Z_C|Z_Z|Z_S|Z_PV|Z_Y));
 assert(translated_z80_step(&c)==21);
 assert(translated_z80_step(&c)==16 && c.z80_cpu.pc==2);
 for(unsigned i=0;i<4;++i) assert(c.z80_bus.ram[0x100+i]==0x42);
 assert(z80_pair(&c,0)==0 && z80_pair(&c,1)==0x104 && z80_pair(&c,2)==0x103);
 assert(!(c.z80_cpu.f&Z_PV));
''')

    def test_conditional_control_flow_and_refresh(self):
        self.run_harness('06 03 3e 01 3c 10 fd fe 04 20 01 76 76','''
 c.z80_cpu.r=0xfe; z80_tick(&c,100);
 assert(!c.fault && c.z80_cpu.a==4 && c.z80_cpu.halted);
 assert(c.z80_cpu.pc==12 && (c.z80_cpu.f&Z_Z));
 assert(c.z80_cpu.r&0x80);
''')

    def test_conditional_call_return_and_restart_stack_cycles(self):
        self.run_harness('c4 05 00 76 00 c0 76', '''
 c.z80_cpu.sp=0x1000; c.z80_cpu.f=Z_Z;
 assert(translated_z80_step(&c)==10 && c.z80_cpu.pc==3 && c.z80_cpu.sp==0x1000);
 c.z80_cpu.pc=0; c.z80_cpu.f=0;
 assert(translated_z80_step(&c)==17 && c.z80_cpu.pc==5 && c.z80_cpu.sp==0xffe);
 assert(c.z80_bus.ram[0xffe]==3 && c.z80_bus.ram[0xfff]==0);
 c.z80_cpu.f=Z_Z;
 assert(translated_z80_step(&c)==5 && c.z80_cpu.pc==6 && c.z80_cpu.sp==0xffe);
 c.z80_cpu.pc=5; c.z80_cpu.f=0;
 assert(translated_z80_step(&c)==11 && c.z80_cpu.pc==3 && c.z80_cpu.sp==0x1000);
''')
        self.run_harness('cf 76 00 00 00 00 00 00 c9', '''
 c.z80_cpu.sp=0x1000;
 assert(translated_z80_step(&c)==11 && c.z80_cpu.pc==8 && c.z80_cpu.sp==0xffe);
 assert(c.z80_bus.ram[0xffe]==1 && c.z80_bus.ram[0xfff]==0);
 assert(translated_z80_step(&c)==10 && c.z80_cpu.pc==1 && c.z80_cpu.sp==0x1000);
''')

    def test_rotate_memory_flags_refresh_and_bank_bootstrap_ack(self):
        self.run_harness('cb 1e 76', '''
 z80_set_pair(&c,2,0x100); c.z80_bus.ram[0x100]=0x81; c.z80_cpu.f=0xff;
 assert(translated_z80_step(&c)==15 && c.z80_cpu.pc==2);
 assert(c.z80_bus.ram[0x100]==0xc0 && c.z80_cpu.f==(Z_S|Z_PV|Z_C));
 assert(c.z80_cpu.r==2 && !c.fault);
''')
        self.run_harness('f3 af 32 00 10 11 2d 01 06 09 7b e6 01 32 00 60 cb 1a cb 1b 10 f4 3e ff 32 00 10 76', '''
 c.audio_mode=AUDIO_MUTE; z80_tick(&c,1000);
 assert(!c.fault && c.z80_cpu.halted && c.z80_bus.bank==0x12d);
 assert(c.z80_bus.ram[0x1000]==0xff && c.z80_cpu.steps>60);
''')

    def test_exhaustive_cb_rotate_shift_flags(self):
        self.run_harness('76', '''
 for(unsigned kind=0;kind<8;kind++)for(unsigned value=0;value<256;value++)for(unsigned ci=0;ci<2;ci++) {
  unsigned expected,co;
  switch(kind) {
   case 0: expected=(value*2+value/128)%256;co=value/128;break;
   case 1: expected=value/2+(value%2)*128;co=value%2;break;
   case 2: expected=(value*2+ci)%256;co=value/128;break;
   case 3: expected=value/2+ci*128;co=value%2;break;
   case 4: expected=(value*2)%256;co=value/128;break;
   case 5: expected=value/2+(value>=128?128:0);co=value%2;break;
   case 6: expected=(value*2+1)%256;co=value/128;break;
   default: expected=value/2;co=value%2;break;
  }
  unsigned bits=0;for(unsigned n=0;n<8;n++)bits+=(expected>>n)&1;
  unsigned flags=(expected&0xa8)|(expected==0?Z_Z:0)|(bits%2==0?Z_PV:0)|co;
  c.z80_cpu.f=(uint8_t)(0xfe|ci);
  assert(z80_rotate(&c,value,kind)==expected && c.z80_cpu.f==flags);
 }
''')

    def test_indexed_memory_uses_signed_displacements_and_real_hl_registers(self):
        self.run_harness('dd 21 01 01 26 44 dd 74 ff dd 6e ff dd 23 dd 36 fe 7f dd 34 fe dd 86 fe fd 21 ff ff fd cb 02 f0 76', '''
 z80_tick(&c,200); assert(!c.fault && c.z80_cpu.halted);
 assert(c.z80_cpu.ix==0x102 && c.z80_cpu.r8[4]==0x44 && c.z80_cpu.r8[5]==0x44);
 assert(c.z80_bus.ram[0x100]==0x80 && c.z80_cpu.a==0x80);
 assert(c.z80_cpu.r8[0]==(c.z80_bus.ram[1]) && (c.z80_bus.ram[1]&64));
 assert(c.z80_cpu.f==Z_S);
''')

    def test_index_add_pair_memory_bit_and_complement_flags(self):
        self.run_harness('dd 21 ff ff 01 01 00 dd 09 ed 43 00 01 ed 5b 00 01 3e 80 cb 7f 2f 76', '''
 c.z80_cpu.f=Z_Z|Z_PV; z80_tick(&c,140);
 assert(!c.fault && c.z80_cpu.halted && c.z80_cpu.ix==0);
 assert(z80_pair(&c,1)==1 && c.z80_bus.ram[0x100]==1 && c.z80_bus.ram[0x101]==0);
 assert(c.z80_cpu.a==0x7f && c.z80_cpu.f==(Z_S|Z_C|Z_X|Z_Y|Z_H|Z_N));
''')

    def test_psg_register_latches_on_both_buses(self):
        self.run_harness('3e bf 32 11 7f 76','''
 write_mem(&c,0xc00011,1,0x85); write_mem(&c,0xc00011,1,0x2a);
 write_mem(&c,0xc00011,1,0x9f); write_mem(&c,0xc00011,1,0xe7);
 z80_tick(&c,24); assert(!c.fault);
 assert(c.psg.tone[0]==0x2a5 && c.psg.volume[0]==15 && c.psg.volume[1]==15);
 assert(c.psg.noise==7 && c.psg.noise_lfsr==0x8000 && c.psg.writes==5);
''')

    def test_exhaustive_alu_flags(self):
        self.run_harness('76','''
 for(unsigned kind=0;kind<8;++kind) for(unsigned a=0;a<256;++a)
 for(unsigned b=0;b<256;++b) for(unsigned carry=0;carry<2;++carry) {
   unsigned ci=(kind==1 || kind==3)?carry:0;
   int sub=kind==2 || kind==3 || kind==7;
   int sum=sub ? (int)a-(int)b-(int)ci:(int)a+(int)b+(int)ci;
   uint8_t r=(uint8_t)sum;
   if(kind==4) r=a&b; else if(kind==5) r=a^b; else if(kind==6) r=a|b;
   unsigned bits=0; for(unsigned n=0;n<8;++n) bits+=(r>>n)&1;
   unsigned f=(r&0xa8)|(r==0?Z_Z:0);
   if(kind>=4 && kind<=6) f|=(bits%2==0?Z_PV:0)|(kind==4?Z_H:0);
   else {
     int sa=(int8_t)a,sb=(int8_t)b;
     int signed_sum=sub?sa-sb-(int)ci:sa+sb+(int)ci;
     f|=(sum<0 || sum>255?Z_C:0)|(signed_sum< -128 || signed_sum>127?Z_PV:0);
     int nibble=sub?(int)(a&15)-(int)(b&15)-(int)ci:(int)(a&15)+(int)(b&15)+(int)ci;
     f|=(nibble<0 || nibble>15?Z_H:0)|(sub?Z_N:0);
     if(kind==7) f=(f&~0x28)|(b&0x28);
   }
   c.z80_cpu.a=a; c.z80_cpu.f=carry; z80_alu(&c,kind,b);
   assert(c.z80_cpu.a==(kind==7?a:r) && c.z80_cpu.f==f);
 }
''')
