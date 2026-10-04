"""Rings sound build options and optional original-driver startup regression."""
import contextlib
import hashlib
import io
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from examples import build_rings_of_power as rings
from genesis_recompiler.decode import Program
from genesis_recompiler.emit import emit
from genesis_recompiler.z80 import analyze_z80
from support import CompiledTestCase

ROM = Path(__file__).resolve().parents[1] / 'build/rings-of-power/Rings of Power (UE) [!].gen'


class RingsSoundBuildTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.rom = self.root / 'Rings [!].gen'
        self.data = bytes(0x100000)
        self.rom.write_bytes(self.data)

    def tearDown(self):
        self.temp.cleanup()

    def invoke(self, *args):
        with patch.object(rings, 'ROOT', self.root), \
             patch.object(rings, 'ROM_SHA256', hashlib.sha256(self.data).hexdigest()), \
             patch('sys.argv', ['build_rings_of_power.py', str(self.rom), *args]), \
             patch.object(rings.subprocess, 'run') as run:
            run.return_value.returncode = 0
            status = rings.main()
        return status, run

    def test_default_build_includes_sound_and_original_driver_even_without_zoom(self):
        status, run = self.invoke('--frontend', 'headless')
        self.assertEqual(status, 0)
        command = run.call_args.args[0]
        self.assertEqual(command[command.index('--sound') + 1], 'ymfm')
        images = [Path(command[i+1]).read_bytes() for i, arg in enumerate(command) if arg == '--z80-image']
        self.assertEqual(images, list(rings.z80_images(self.data)))
        self.assertEqual(command[command.index('--z80-image-entry') + 1], '2:0x38')
        self.assertIn('ea-24c01', command)
        self.assertIn('--rings-saves', command)

    def test_silent_build_keeps_the_driver_and_forwards_sound_compiler(self):
        status, run = self.invoke('--sound', 'none', '--cxx', 'custom-c++', '--zoom', '--text-renderer', 'rings-text')
        self.assertEqual(status, 0)
        command = run.call_args.args[0]
        self.assertEqual(command[command.index('--sound') + 1], 'none')
        self.assertEqual(command[command.index('--cxx') + 1], 'custom-c++')
        self.assertEqual(command.count('--z80-image'), 3)
        self.assertIn('--rings-zoom', command)
        self.assertIn('rings-text', command)

    def test_driver_artifact_cannot_overwrite_input_rom(self):
        out = self.root / 'build/rings-of-power'
        out.mkdir(parents=True)
        (out / 'z80-driver.bin').hardlink_to(self.rom)
        with contextlib.redirect_stderr(io.StringIO()) as error, self.assertRaises(SystemExit):
            self.invoke()
        self.assertIn('different path', error.getvalue())
        self.assertEqual(self.rom.read_bytes(), self.data)
        self.assertFalse((out / 'z80-boot.bin').exists())

    def test_incomplete_uploads_are_rejected(self):
        with self.assertRaisesRegex(ValueError, 'incomplete'):
            rings.z80_images(bytes(0xED0E3))


class RingsSoundDriverTests(CompiledTestCase):
    @unittest.skipUnless(ROM.exists(), 'user-provided Rings of Power ROM is absent')
    def test_original_driver_is_translated_and_initializes_the_fm_mailbox_loop(self):
        rom = ROM.read_bytes()
        self.assertEqual(hashlib.sha256(rom).hexdigest(), rings.ROM_SHA256)
        images = rings.z80_images(rom)
        self.assertEqual(images[2][:8], bytes.fromhex('21ff1ff9c37d0100'))
        program = analyze_z80(images, image_entries=((2, 0x38),))
        self.assertEqual(program.errors, [])
        self.assertEqual(sum(map(len, program.instructions.values())), 1086)
        harness = r'''
#include <assert.h>
int main(void) {
    CPU *c=calloc(1,sizeof *c);assert(c);
    c->rom=rom_data;c->rom_size=sizeof rom_data;c->audio_mode=AUDIO_MUTE;
    memcpy(c->z80_bus.ram,c->rom+0xebb6e,0x1576);
    c->z80_bus.reset_released=1;z80_reset(c);
    for(unsigned i=0;i<10000;++i)z80_tick(c,15);
    assert(!c->fault && c->z80_cpu.steps>10000);
    assert(c->z80_cpu.pc>=0x188 && c->z80_cpu.pc<=0x1b1);
    assert(c->z80_cpu.sp==0x1fff && !c->z80_cpu.iff1);
    assert(c->ym2612_stub.writes==2 && c->ym2612_stub.registers[0][0x27]==0);
    assert(c->z80_bus.ram[0x0a]==0 && c->z80_bus.ram[0x0b]==0);
    free(c);return 0;
}
'''
        binary = self.compile('#define GENESIS_NO_MAIN\n' + emit(Program(rom), program) + harness)
        result = subprocess.run([str(binary)], capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
