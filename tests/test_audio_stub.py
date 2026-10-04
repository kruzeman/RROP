import subprocess
from genesis_recompiler.decode import analyze
from genesis_recompiler.emit import emit
from genesis_recompiler.z80 import analyze_z80
from support import CompiledTestCase, rom_with


class AudioStubTests(CompiledTestCase):
    def test_mute_runs_guarded_z80_and_preserves_bus_ownership(self):
        image=bytes.fromhex('3e 22 32 00 40 3e 11 32 01 40 3e aa 32 00 10 76')
        code='33fc 0100 00a11100 '
        for at in range(0,len(image),4):
            code+='23fc '+image[at:at+4].hex()+' '+(0xa00000+at).to_bytes(4,'big').hex()+' '
        code+='33fc 0100 00a11200 33fc 0000 00a11100 7064 51c8 fffe 4e72 2700'
        p=analyze(rom_with(code),[0x200]); z=analyze_z80([image])
        self.assertEqual((p.errors,z.errors),({},[]))
        exe=self.compile(emit(p,z))
        for mode,mailbox,ym in [('mute',0xaa,2),('stub',0,0)]:
            path=self.root/(mode+'.bin')
            result=subprocess.run([str(exe),'--audio',mode,'--dump-z80',str(path)],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)
            self.assertEqual(path.read_bytes()[0x1000],mailbox)
            self.assertIn('ym_writes='+str(ym),result.stdout)
            self.assertIn('z80_execution='+('enabled' if mode=='mute' else 'disabled'),result.stdout)
        strict=subprocess.run([str(exe),'--audio','strict'],capture_output=True,text=True)
        self.assertEqual(strict.returncode,1)
        self.assertIn('Z80 peripheral write not implemented',strict.stderr)

    def test_stub_release_without_translation_preserves_upload(self):
        code='33fc 0100 00a11100 23fc 12345678 00a00000 33fc 0100 00a11200 33fc 0000 00a11100 4e72 2700'
        path=self.root/'z80.bin'
        result=self.execute(rom_with(code),['--audio','stub','--dump-z80',str(path)])
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertIn('audio mode=stub z80_execution=disabled',result.stdout)
        self.assertIn('z80 steps=0 cycles=0',result.stdout)
        self.assertEqual(path.read_bytes()[:4],bytes.fromhex('12345678'))
        strict=self.execute(rom_with(code),['--audio','strict'])
        self.assertEqual(strict.returncode,1)
        self.assertIn('no static translation',strict.stderr)

    def test_stub_ym_ports_have_ready_status(self):
        code='33fc 0100 00a11100 13fc 002a 00a04000 13fc 0080 00a04001 1039 00a04000 4e72 2700'
        result=self.execute(rom_with(code),['--audio','stub'])
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertIn('D0=00000000',result.stdout)
        self.assertIn('ym_writes=2',result.stdout)
        strict=self.execute(rom_with(code))
        self.assertEqual(strict.returncode,1)
        self.assertIn('peripheral write not implemented',strict.stderr)

    def test_stub_still_requires_bus_grant(self):
        result=self.execute(rom_with('1039 00a04000 4e72 2700'),['--audio','stub'])
        self.assertEqual(result.returncode,1)
        self.assertIn('bus has not been granted',result.stderr)

    def test_stub_does_not_suppress_other_hardware_faults(self):
        result=self.execute(rom_with('3039 00400000 4e72 2700'),['--audio','stub'])
        self.assertEqual(result.returncode,1)
        self.assertIn('unmapped read',result.stderr)

    def test_audio_mode_arguments_are_validated(self):
        for args in (['--audio'],['--audio','muted']):
            with self.subTest(args=args):
                result=self.execute(rom_with('4e72 2700'),args)
                self.assertEqual(result.returncode,64)

    def test_stub_register_banks_mirrors_and_inactive_cpu_mailbox(self):
        p=analyze(rom_with('4e72 2700'),[0x200])
        source='#define GENESIS_NO_MAIN\n'+emit(p)+'''
#include <assert.h>
int main(void) {
 CPU c={0}; c.rom=rom_data; c.rom_size=sizeof rom_data;
 c.audio_mode=1; c.z80_bus.requested=1;
 write_mem(&c,0xa04000,1,0x22); write_mem(&c,0xa04001,1,0x11);
 write_mem(&c,0xa05002,1,0x22); write_mem(&c,0xa05003,1,0x77);
 assert(c.ym2612_stub.registers[0][0x22]==0x11 && c.ym2612_stub.registers[1][0x22]==0x77);
 z80_write(&c,0x4000,0x2a); z80_write(&c,0x4001,0xff);
 assert(c.ym2612_stub.registers[0][0x2a]==0xff);
 for(unsigned i=0;i<4;++i) assert(z80_read(&c,0x4000+i)==0);
 c.z80_bus.requested=0; c.z80_bus.reset_released=1;
 c.z80_bus.ram[0]=0xff; c.z80_bus.ram[0x1700]=0xa5;
 machine_advance(&c,1000);
 assert(!c.fault && c.z80_cpu.steps==0 && c.z80_cpu.cycles==0);
 assert(c.z80_bus.ram[0x1700]==0xa5 && c.cycles==1000);
 c.audio_mode=0; z80_tick(&c,1); assert(c.fault);
 return 0;
}
'''
        exe=self.compile(source)
        result=subprocess.run([str(exe)],capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stderr)
