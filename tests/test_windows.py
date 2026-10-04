"""Real MinGW executables: binary/Unicode saves and all-feature SDL builds.

Run on Windows with MSYS2 Python/GCC, or on Linux with MinGW and Wine.
WINDOWS_CC/CXX/OBJDUMP and WINE may select an installed toolchain/runner.
"""
import io
import os
from pathlib import Path
import shutil
import subprocess
import tarfile
import tempfile
import unittest
from unittest.mock import patch
from genesis_recompiler.build import build_executable, BuildError, compiler_target
from genesis_recompiler.decode import analyze
from genesis_recompiler.emit import emit
from genesis_recompiler.windows import bundle_dlls, imported_dlls, prepare_sdk, sdk_environment
from support import CompiledTestCase, rom_with
from test_rings_zoom import ZOOM_SCENE
from test_rings_scene import CONTEXT


class WindowsSDKTests(unittest.TestCase):
    def test_package_finds_runtime_dll_beside_msys_compiler(self):
        with tempfile.TemporaryDirectory() as work:
            root = Path(work)
            toolchain = root / 'compiler'; toolchain.mkdir()
            compiler = toolchain / 'gcc.exe'; compiler.touch()
            runtime = toolchain / 'libwinpthread-1.dll'; runtime.write_bytes(b'runtime')
            binary = root / 'game.exe'; binary.touch()
            def imports(path, objdump):
                return ['libwinpthread-1.dll'] if path==binary else ['KERNEL32.dll']
            with patch('genesis_recompiler.windows.imported_dlls', side_effect=imports):
                names = bundle_dlls(binary, root / 'package', root / 'sdk', str(compiler), 'objdump')
            self.assertEqual(names, ['libwinpthread-1.dll'])
            self.assertEqual((root / 'package' / names[0]).read_bytes(), b'runtime')

    def test_sdk_rejects_bad_checksum_without_extracting(self):
        with tempfile.TemporaryDirectory() as work:
            root = Path(work)
            (root / 'SDL2-devel-2.32.10-mingw.tar.gz').write_bytes(b'corrupt download')
            with self.assertRaisesRegex(BuildError, 'checksum mismatch'):
                prepare_sdk(root)
            self.assertFalse((root / 'x86_64-w64-mingw32').exists())

    def test_archive_rejects_parent_escape_and_links(self):
        import hashlib
        for name, link in [('SDL2-test/x86_64-w64-mingw32/../../escape', False),
                           ('SDL2-test/x86_64-w64-mingw32/include/alias', True)]:
            with self.subTest(name=name), tempfile.TemporaryDirectory() as work:
                root = Path(work)
                archive = root / 'SDL2-devel-test-mingw.tar.gz'
                with tarfile.open(archive, 'w:gz') as out:
                    member = tarfile.TarInfo(name)
                    if link:
                        member.type = tarfile.SYMTYPE; member.linkname = '/etc/passwd'
                        out.addfile(member)
                    else:
                        member.size = 1; out.addfile(member, io.BytesIO(b'x'))
                digest = hashlib.sha256(archive.read_bytes()).hexdigest()
                with patch('genesis_recompiler.windows.SDK_PACKAGES', [('SDL2', 'test', 'SDL', digest)]):
                    with self.assertRaisesRegex(BuildError, 'unsafe SDK'):
                        prepare_sdk(root)


class WindowsRuntimeTests(CompiledTestCase):
    @classmethod
    def setUpClass(cls):
        native = os.name == 'nt'
        cls.cc = os.environ.get('WINDOWS_CC', 'gcc' if native else 'x86_64-w64-mingw32-gcc')
        cls.cxx = os.environ.get('WINDOWS_CXX', 'g++' if native else 'x86_64-w64-mingw32-g++')
        cls.objdump = os.environ.get('WINDOWS_OBJDUMP', 'objdump' if native else 'x86_64-w64-mingw32-objdump')
        if not shutil.which(cls.cc):
            raise unittest.SkipTest('MinGW not installed')
        if compiler_target(cls.cc) != 'x86_64-w64-mingw32':
            raise unittest.SkipTest('test requires a Windows x64 target')
        cls.runner = [] if native else [os.environ.get('WINE', 'wine')]
        if not native and not shutil.which(cls.runner[0]):
            raise unittest.SkipTest('Wine not installed')

    def run_windows(self, binary, args=()):
        env = dict(os.environ, WINEDEBUG='-all', SDL_VIDEODRIVER='dummy',
                   SDL_RENDER_DRIVER='software', SDL_AUDIODRIVER='dummy')
        return subprocess.run([*self.runner, str(binary), *args], cwd=self.root, env=env,
                              capture_output=True, text=True, timeout=90)

    def test_unicode_binary_saves_replacement_rotation_and_commit_failure(self):
        source = '#define GENESIS_NO_MAIN\n#define GENESIS_RINGS_SAVES\n' + emit(analyze(rom_with('5240 60fc'), [0x200]))
        source += r'''
#include <assert.h>
int main(void) {
    assert(SetEnvironmentVariableW(L"LOCALAPPDATA",L".\\state-кириллица"));
    CPU *c=calloc(1,sizeof *c);assert(c);
    c->rom=rom_data;c->rom_size=sizeof rom_data;c->pc=0x200;c->a[7]=0xffff00;c->sr=0x2700;
    c->audio_mode=AUDIO_STUB;c->eeprom.enabled=1;
    RingsSaves s={0};assert(rings_saves_open(&s,c,NULL,1));
    assert(strstr(s.directory,"state-кириллица"));
    /* CRT text mode would alter LF and truncate at Ctrl-Z in binary payloads. */
    for(unsigned i=0;i<65536;++i)c->ram[i]=(uint8_t)i;
    for(int i=0;i<5;++i) {c->d[3]=40+i;assert(rings_save_write(&s,c,i));}
    c->ram[10]=0;c->d[3]=0;assert(rings_save_load(&s,c,0));
    assert(c->ram[10]==10 && c->ram[13]==13 && c->ram[26]==26 && c->d[3]==40);
    c->d[3]=99;assert(rings_save_write(&s,c,0));c->d[3]=0;
    assert(rings_save_load(&s,c,0) && c->d[3]==99);
    char path[1100];wchar_t wide[1200];assert(rings_save_path(&s,0,path,sizeof path));
    assert(rings_save_wide(path,wide,1200));
    HANDLE held=CreateFileW(wide,GENERIC_READ,FILE_SHARE_READ,NULL,OPEN_EXISTING,0,NULL);
    assert(held!=INVALID_HANDLE_VALUE);uint64_t serial=s.serial;c->d[3]=123;
    assert(!rings_save_write(&s,c,0) && s.serial==serial && !c->fault);
    CloseHandle(held);assert(rings_save_load(&s,c,0) && c->d[3]==99);
    s.started=1;rings_save_tick(&s,c,0,1);
    for(int i=1;i<=7;++i) {c->d[3]=i;rings_save_tick(&s,c,(uint64_t)i*300000,1);}
    RingsSaves reopened={0};assert(rings_saves_open(&reopened,c,NULL,1));
    for(int i=0;i<10;++i)assert(reopened.slots[i].compatible);
    assert(rings_save_load(&reopened,c,5) && c->d[3]==6);
    assert(rings_save_load(&reopened,c,6) && c->d[3]==7);
    assert(rings_save_load(&reopened,c,7) && c->d[3]==3);
    free(c);return 0;
}
'''
        binary = self.root / 'saves.exe'
        build_executable(source, binary, self.cc)
        self.assertIn('KERNEL32.dll', imported_dlls(binary, self.objdump))
        result = self.run_windows(binary)
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        slots = list(self.root.rglob('*.grs'))
        self.assertEqual(len(slots), 10)
        self.assertTrue(all(p.read_bytes().startswith(b'GRPSAVE1') for p in slots))
        self.assertEqual(list(self.root.rglob('*.tmp.*')), [])

    def test_windows_stack_all_features_sdl_sound_and_complete_dll_package(self):
        sdk = os.environ.get('WINDOWS_SDK')
        if not sdk:
            self.skipTest('set WINDOWS_SDK to the prepared x86_64-w64-mingw32 prefix')
        prefix = Path(sdk)
        source = '#define GENESIS_RINGS_SAVES\n#define GENESIS_RINGS_SMOOTH_CAMERA\n' + emit(analyze(rom_with('5240 60fc'), [0x200]))
        binary = self.root / 'all-features.exe'
        with patch.dict(os.environ, sdk_environment(prefix)):
            build_executable(source, binary, self.cc, 'sdl2', 'ymfm', self.cxx, 'rings-text', True)
        bundle_dlls(binary, self.root, prefix, self.cc, self.objdump)
        font_args = []
        if os.name == 'nt':
            font = Path(os.environ['WINDIR']) / 'Fonts' / 'arial.ttf'
            self.assertTrue(font.is_file())
            font_args = ['--font', str(font)]
        else:
            for font in (Path('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'),
                         Path('/usr/share/fonts/truetype/open-sans/OpenSans-Regular.ttf')):
                if font.is_file():
                    font_args = ['--font', 'Z:' + font.as_posix()]
                    break
        result = self.run_windows(binary, ['--window', '--audio', 'on', '--no-throttle',
            '--limit', '10000', '--widescreen', '--zoom', '--mouse', '--smooth-camera',
            '--dump-audio', 'sound.wav', '--save-dir', 'saves', '--save-slot', 'manual-1', *font_args])
        self.assertEqual(result.returncode, 2, result.stderr + result.stdout)
        self.assertIn('status=budget steps=10000', result.stdout)
        self.assertTrue((self.root / 'saves' / 'manual-1.grs').exists())
        wave = (self.root / 'sound.wav').read_bytes()
        self.assertTrue(wave.startswith(b'RIFF') and len(wave)>44)
        self.assertTrue((self.root / 'SDL2.dll').exists())
        self.assertTrue((self.root / 'SDL2_ttf.dll').exists())

    def test_rooms_combat_and_old_saves_restore_native_presentation(self):
        sdk = os.environ.get('WINDOWS_SDK')
        if not sdk:
            self.skipTest('set WINDOWS_SDK to the prepared x86_64-w64-mingw32 prefix')
        prefix = Path(sdk)
        source = ('#define GENESIS_NO_MAIN\n#define GENESIS_RINGS_SAVES\n'
                  '#define GENESIS_RINGS_SMOOTH_CAMERA\n' + emit(analyze(rom_with('4e72 2700'), [0x200])))
        source += '\n#include <assert.h>\n' + ZOOM_SCENE + CONTEXT + r'''
int main(int argc,char **argv) {
 (void)argc;(void)argv;
 CPU *c=calloc(1,sizeof *c);RingsWide *w=calloc(1,sizeof *w);assert(c && w);
 zoom_scene(c,w);c->vdp.wide_enabled=1;c->pc=0x200;c->a[7]=0xffff00;c->sr=0x2700;
 SDLHost h={0};h.wide_window=1;h.no_throttle=1;h.zoom_percent=50;h.camera.enabled=1;
 assert(sdl_host_open(&h));context(c,0xb08c,1,1);vdp_render(c);
 assert(sdl_host_draw(&h,&c->vdp) && h.width==400);
 for(unsigned battle=0;battle<2;++battle) {
  context(c,battle ? 0xb0ac:0xb09c,battle ? 1:0,battle ? 2:1);
  vdp_render(c);assert(sdl_host_draw(&h,&c->vdp) && h.width==320 && h.zoom_percent==50);
  assert(!c->vdp.zoom_world_visible && !c->vdp.wide_hud_active && !c->vdp.camera.valid);
  /* The prior version persisted expanded caches even on a fixed map. */
  c->vdp.native_scene=0;c->vdp.zoom_world_visible=1;c->vdp.wide_world_visible=1;
  c->vdp.wide_hud_active=1;w->valid=w->pending=w->zoom_valid=w->zoom_pending=1;
  SaveCodec old={0};assert(save_encode(c,&old));context(c,0xb08c,1,1);
  assert(save_decode(c,old.data,old.size));free(old.data);
  assert(c->vdp.native_scene && c->vdp.wide_enabled && c->vdp.zoom_enabled);
  assert(!w->valid && !w->pending && !w->zoom_valid && !w->zoom_pending);
  assert(sdl_host_draw(&h,&c->vdp) && h.width==320);
  uint8_t *rgb=malloc(1200*672*3);assert(rgb);
  assert(!SDL_RenderSetLogicalSize(h.renderer,0,0) && !SDL_RenderSetScale(h.renderer,1,1) && !SDL_RenderSetViewport(h.renderer,NULL));
  assert(!SDL_RenderReadPixels(h.renderer,NULL,SDL_PIXELFORMAT_RGB24,rgb,1200*3));
  for(unsigned y=0;y<672;++y)for(unsigned x=0;x<1200;++x) {
   const uint8_t *p=rgb+(y*1200+x)*3;
   if(x<120 || x>=1080)assert(!p[0] && !p[1] && !p[2]);
   else assert(!memcmp(p,c->vdp.frame+((y/3)*320+(x-120)/3)*3,3));
  }
  free(rgb);
 }
 context(c,0xb08c,1,1);w->valid=w->zoom_valid=1;vdp_render(c);
 assert(sdl_host_draw(&h,&c->vdp) && h.width==400 && h.zoom_percent==50);
 sdl_host_close(&h);free(w);free(c);return 0;
}
'''
        binary = self.root / 'fixed-scenes.exe'
        with patch.dict(os.environ, sdk_environment(prefix)):
            build_executable(source, binary, self.cc, 'sdl2', 'ymfm', self.cxx, 'rings-text', True)
        bundle_dlls(binary, self.root, prefix, self.cc, self.objdump)
        result = self.run_windows(binary)
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
