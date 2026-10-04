"""External resources must preserve ROM reads and actual VDP graphics loading."""
import contextlib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import unittest
from genesis_recompiler.cli import main
from genesis_recompiler.decode import analyze, RamCodeCopy
from genesis_recompiler.emit import emit
from genesis_recompiler.resources import GraphicsRange, plan_resources, write_resources
from support import CompiledTestCase, rom_with


class ResourceTests(CompiledTestCase):
    def fixture(self, color=1):
        rom=bytearray(rom_with('4e72 2700'))
        rom[0x300:0x320]=bytes([color*17])*32
        rom[0x330:0x340]=bytes(range(16))
        rom[0x360:0x362]=b'\x4e\x75'
        program=analyze(bytes(rom),[0x200],[RamCodeCopy(0x360,0xff0100,2)])
        plan=plan_resources(program,[GraphicsRange('patterns',0x300,32)])
        return program,plan

    def invoke(self, rom, output, resources, *args):
        with contextlib.redirect_stdout(io.StringIO()),contextlib.redirect_stderr(io.StringIO()) as err:
            status=main([str(rom),'--build','-o',str(output),'--resources-dir',str(resources),
                         '--graphics-range','patterns:0x300:32','--m68k-copy','0x360:0xff0100:2',*args])
        return status,err.getvalue()

    def test_lossless_partition_keeps_ram_copy_and_classifies_graphics(self):
        program,plan=self.fixture()
        reconstructed=bytearray(len(program.rom));covered=bytearray(len(program.rom))
        pieces=[(plan.code,plan.code_spans),*((r.data,r.spans) for r in plan.resources)]
        for data,spans in pieces:
            for address,offset,size in spans:
                self.assertFalse(any(covered[address:address+size]))
                reconstructed[address:address+size]=data[offset:offset+size]
                covered[address:address+size]=b'\1'*size
        self.assertTrue(all(covered));self.assertEqual(bytes(reconstructed),program.rom)
        self.assertEqual(plan.resources[0].data,b'\x11'*32)
        self.assertTrue(any(a<=0x360<a+n for a,_,n in plan.code_spans))
        self.assertLess(len(plan.code),len(program.rom))
        source=emit(program,resources=plan)
        self.assertNotIn('static const uint8_t rom_data[]',source)
        self.assertNotIn(','.join(['0x11']*16),source)
        write_resources(plan,self.root/'resources')
        manifest=json.loads((self.root/'resources/manifest.json').read_text())
        self.assertEqual(manifest,plan.manifest())
        self.assertEqual(manifest['embedded_bytes']+manifest['external_bytes'],len(program.rom))

    def test_invalid_ranges_never_extract_code_or_traverse_paths(self):
        program,_=self.fixture()
        invalid=[(GraphicsRange('a',0x200,2),),(GraphicsRange('a',0x360,2),),
                 (GraphicsRange('a',0,1),),(GraphicsRange('a',-1,10),),
                 (GraphicsRange('a',0x300,0),),(GraphicsRange('a',0x3ff,2),),
                 (GraphicsRange('../bad',0x300,32),),
                 (GraphicsRange('a',0x300,32),GraphicsRange('a',0x330,16)),
                 (GraphicsRange('a',0x300,32),GraphicsRange('b',0x310,32))]
        for ranges in invalid:
            with self.subTest(ranges=ranges),self.assertRaises(ValueError):plan_resources(program,ranges)

    def test_external_bytes_feed_bus_dma_render_and_ram_byte_guards(self):
        for color in (1,2):
            program,plan=self.fixture(color)
            directory=self.root/f'resources-{color}';write_resources(plan,directory)
            source='#define GENESIS_NO_MAIN\n'+emit(program,resources=plan)+'''
#include <assert.h>
int main(int argc,char**argv){
 assert(argc==2);
 uint8_t *rom=resource_load(argv[1],1024,rom_code,rom_code_spans,
 sizeof rom_code_spans/sizeof rom_code_spans[0],rom_resources,sizeof rom_resources/sizeof rom_resources[0]);
 assert(rom);CPU c={0};c.rom=rom;c.rom_size=1024;
 assert(read_mem(&c,0x330,4)==0x00010203);
 assert(z80_read(&c,0x8300)==COLOR*17);
 VDP*v=&c.vdp;v->registers[1]=0x44;v->registers[2]=0x30;v->registers[4]=5;
 v->registers[3]=0x2c;v->registers[5]=0x6c;v->registers[13]=0x38;
 v->cram[1]=0x000e;v->cram[2]=0x00e0;
 v->registers[15]=2;v->registers[19]=16;v->registers[21]=0x80;v->registers[22]=1;
 v->address=32;v->code=1;vdp_start_dma(&c);
 assert(!c.fault && v->dma_bytes==32);
 for(unsigned i=0;i<32;++i)assert(v->vram[32+i]==COLOR*17);
 v->vram[0xc001]=1;vdp_render(&c);
 assert(v->frame[0]==RED && v->frame[1]==GREEN && v->frame[2]==0);
 c.a[7]=0xffff00;push32(&c,0x200);c.ram[0x100]=0x4e;c.ram[0x101]=0x75;c.pc=0xff0100;
 translated_step(&c);assert(!c.fault && c.pc==0x200);
 c.ram[0x100]=0;c.pc=0xff0100;translated_step(&c);assert(c.fault);
 free(rom);return 0;}
'''.replace('COLOR',str(color)).replace('RED',str(255 if color==1 else 0)).replace('GREEN',str(255 if color==2 else 0))
            binary=self.compile(source)
            result=subprocess.run([str(binary),str(directory)],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)

    def game(self):
        program,plan=self.fixture();rom=self.root/'game.bin';rom.write_bytes(program.rom)
        directory=self.root/'bundle/resources';binary=self.root/'bundle/game'
        status,error=self.invoke(rom,binary,directory)
        self.assertEqual(status,0,error)
        return binary,directory,plan,rom

    def test_missing_wrong_size_and_changed_resources_fault_before_cpu(self):
        binary,directory,plan,_=self.game();resource=directory/plan.resources[0].path
        original=resource.read_bytes()
        for data in (None,original[:-1],original+b'\0',b'\x12'+original[1:]):
            if data is None:resource.unlink()
            else:resource.write_bytes(data)
            result=subprocess.run([str(binary)],capture_output=True,text=True)
            self.assertEqual(result.returncode,1,result.stdout+result.stderr)
            self.assertIn('resource',result.stderr);self.assertNotIn('status=',result.stdout)
            resource.write_bytes(original)
        self.assertEqual(subprocess.run([str(binary)],capture_output=True).returncode,0)

    def test_relocation_other_cwd_path_and_directory_override(self):
        binary,directory,_,_=self.game()
        moved=self.root/'moved bundle';shutil.move(binary.parent,moved)
        binary=moved/'game';self.assertFalse(directory.exists())
        for command in ([str(binary)],['game']):
            result=subprocess.run(command,cwd=self.root,env={**os.environ,'PATH':str(moved)+os.pathsep+os.environ['PATH']},capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)
            self.assertIn('status=halted',result.stdout)
        alternative=self.root/'alternative resources';shutil.move(moved/'resources',alternative)
        result=subprocess.run([str(binary),'--resources-dir',str(alternative)],cwd=self.root,capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stderr)
        for options in (['--resources-dir'],['--resources-dir','']):
            result=subprocess.run([str(binary),*options],capture_output=True,text=True)
            self.assertEqual(result.returncode,64)

    def test_protected_inputs_and_manifest_cannot_be_overwritten(self):
        program,plan=self.fixture();directory=self.root/'resources';directory.mkdir()
        original=self.root/'original.bin';original.write_bytes(program.rom)
        os.link(original,directory/'manifest.json')
        with self.assertRaises(ValueError):write_resources(plan,directory,[original])
        self.assertEqual(original.read_bytes(),program.rom)
        self.assertEqual(sorted(p.name for p in directory.iterdir()),['manifest.json'])

    def test_failed_recompile_preserves_old_binary_manifest_and_resources(self):
        binary,directory,plan,rom=self.game();previous=binary.read_bytes()
        manifest=(directory/'manifest.json').read_bytes()
        changed=bytearray(rom.read_bytes());changed[0x300]=0x22;rom.write_bytes(changed)
        status,error=self.invoke(rom,binary,directory,'--cc','missing-genesis-resource-compiler')
        self.assertEqual(status,1);self.assertIn('compiler not found',error)
        self.assertEqual(binary.read_bytes(),previous)
        self.assertEqual((directory/'manifest.json').read_bytes(),manifest)
        for resource in plan.resources:self.assertEqual((directory/resource.path).read_bytes(),resource.data)
        self.assertEqual(subprocess.run([str(binary)],capture_output=True).returncode,0)

    def test_graphics_option_requires_external_resources(self):
        rom=self.root/'rom.bin';rom.write_bytes(rom_with('4e72 2700'))
        with contextlib.redirect_stderr(io.StringIO()),self.assertRaises(SystemExit) as error:
            main([str(rom),'--graphics-range','tile:0x300:32','-o',str(self.root/'game.c')])
        self.assertEqual(error.exception.code,2)

    def test_raw_tile_preview_preserves_nibbles_without_guessing_palette(self):
        program,_=self.fixture()
        plan=plan_resources(program,[GraphicsRange('tiles',0x300,32,'genesis-4bpp')])
        directory=self.root/'tiles';write_resources(plan,directory)
        r=plan.resources[0]
        preview=(directory/Path(r.path).with_suffix('.ppm')).read_bytes()
        self.assertEqual(preview,b'P6\n8 8\n255\n'+b'\x11'*8*8*3)
        self.assertEqual((directory/r.path).read_bytes(),program.rom[0x300:0x320])
        with self.assertRaises(ValueError):
            plan_resources(program,[GraphicsRange('tiles',0x300,31,'genesis-4bpp')])
