"""68000 software exceptions: real frames, vectors and inline handler parameters."""
import argparse
import contextlib
import io
import json
import subprocess
import unittest
from genesis_recompiler.cli import main, trap_data
from genesis_recompiler.decode import Decoder, RamCodeCopy, analyze
from genesis_recompiler.emit import emit
from support import CompiledTestCase, rom_with


class TrapTests(CompiledTestCase):
    def image(self, code='4e41 4e72 2700', handler='7207 4e73'):
        rom=bytearray(rom_with(code))
        rom[0x84:0x88]=(0x300).to_bytes(4,'big')
        raw=bytes.fromhex(handler);rom[0x300:0x300+len(raw)]=raw
        return bytes(rom)

    def check_native(self, body, rom=None, **options):
        p=analyze(rom or self.image(),[0x200],**options)
        self.assertEqual(p.errors,{})
        source='#define GENESIS_NO_MAIN\n'+emit(p)+'''
#include <assert.h>
int main(void) {
 CPU c={0}; c.rom=rom_data; c.rom_size=sizeof rom_data;
 c.pc=0x200; c.sr=0xa51f; c.a[7]=0xffff00; c.ssp=c.a[7];
'''+body+'\nreturn 0; }\n'
        result=subprocess.run([str(self.compile(source))],capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stderr)

    def test_all_vectors_decode_and_only_reached_handlers_discovered(self):
        for number in range(16):
            i=Decoder((0x4e40+number).to_bytes(2,'big'),0).decode()
            self.assertEqual((i.op,i.value,i.end),('TRAP',number,2))
        rom=bytearray(self.image());rom[0x80:0x84]=(0x350).to_bytes(4,'big')
        p=analyze(bytes(rom),[0x200])
        self.assertEqual(p.trap_targets,{1:0x300})
        self.assertIn(0x300,p.instructions);self.assertNotIn(0x350,p.instructions)

    def test_supervisor_frame_trace_mask_and_rte_return(self):
        self.check_native('''
 machine_step(&c);
 assert(!c.fault && c.pc==0x300 && c.sr==0x251f && c.a[7]==0xfffefa);
 assert(read_mem(&c,c.a[7],2)==0xa51f && read_mem(&c,c.a[7]+2,4)==0x202);
 assert(c.steps==1 && c.cycles==34 && c.master_cycles==238 && c.interrupts==0);
 translated_step(&c); translated_step(&c);
 assert(!c.fault && c.pc==0x202 && c.a[7]==0xffff00 && c.sr==0xa51f && c.d[1]==7);
''')

    def test_user_stack_switch_and_restoration(self):
        self.check_native('''
 c.sr=0x851f; c.a[7]=0xffe000; c.ssp=0xffff00;
 translated_step(&c);
 assert(!c.fault && c.usp==0xffe000 && c.a[7]==0xfffefa && c.sr==0x251f);
 assert(read_mem(&c,c.a[7],2)==0x851f);
 translated_step(&c);translated_step(&c);
 assert(!c.fault && c.pc==0x202 && c.sr==0x851f && c.a[7]==0xffe000 && c.ssp==0xffff00);
''')

    def test_inline_data_is_skipped_by_original_handler(self):
        rom=self.image('4e41 4e70 4e72 2700','54af 0002 4e73')
        p=analyze(rom,[0x200],trap_data=((1,2),))
        self.assertEqual(p.errors,{})
        self.assertNotIn(0x202,p.instructions);self.assertIn(0x204,p.instructions)
        self.check_native('''
 translated_step(&c);assert(read_mem(&c,c.a[7]+2,4)==0x202);
 translated_step(&c);assert(read_mem(&c,c.a[7]+2,4)==0x204);
 translated_step(&c);assert(!c.fault && c.pc==0x204);
''',rom,trap_data=((1,2),))

    def test_invalid_vector_remains_a_runtime_fault(self):
        self.check_native('''
 write_mem(&c,0xffff00,4,0x1234);
 c.rom_size=0x84;
 translated_step(&c);assert(c.fault && c.fault_address==0x84);
''')
        rom=bytearray(self.image());rom[0x84:0x88]=(0x400000).to_bytes(4,'big')
        self.check_native('''
 translated_step(&c);assert(!c.fault && c.pc==0x400000);
 translated_step(&c);assert(c.fault && c.fault_address==0x400000);
''',bytes(rom))

    def test_declared_ram_handler_discovered_but_not_uploaded(self):
        rom=bytearray(self.image());rom[0x84:0x88]=(0xff1000).to_bytes(4,'big')
        p=analyze(bytes(rom),[0x200],[RamCodeCopy(0x300,0xff1000,4)])
        self.assertEqual(p.errors,{})
        self.assertIn(0xff1000,p.instructions)
        self.check_native('''
 translated_step(&c);assert(!c.fault && c.pc==0xff1000);
 translated_step(&c);assert(c.fault);
''',bytes(rom),ram_copies=(RamCodeCopy(0x300,0xff1000,4),))

    def test_cli_report_and_annotation_validation(self):
        rom=self.root/'rom.bin';rom.write_bytes(self.image('4e41 4e70 4e72 2700','54af 0002 4e73'))
        output=self.root/'game.c';report=self.root/'analysis.json'
        with contextlib.redirect_stdout(io.StringIO()):
            result=main([str(rom),'-o',str(output),'--report',str(report),'--trap-data','1:2'])
        self.assertEqual(result,0)
        data=json.loads(report.read_text())
        self.assertEqual(data['trap_targets'],{'1':0x300})
        self.assertEqual(data['trap_inline_data'],[{'number':1,'bytes':2}])
        for raw in ('16:2','-1:2','1:3','1:258','x:2','1'):
            with self.assertRaises(argparse.ArgumentTypeError):trap_data(raw)
        for value in (((1,3),),((16,2),),((1,2),(1,4))):
            with self.assertRaises(ValueError):analyze(self.image(),[0x200],trap_data=value)


if __name__=='__main__':unittest.main()
