import os
import subprocess
import unittest
from examples.make_demo import make_demo
from genesis_recompiler.build import BuildError, sdl2_flags
from genesis_recompiler.cli import main
from genesis_recompiler.decode import analyze
from genesis_recompiler.emit import emit
from support import CompiledTestCase, rom_with


class SDLTests(CompiledTestCase):
    @classmethod
    def setUpClass(cls):
        try:
            cls.cflags, cls.libs = sdl2_flags()
        except BuildError as exc:
            raise unittest.SkipTest(str(exc))

    def compile_sdl(self, source):
        path = self.root / 'window.c'
        path.write_text(source)
        binary = self.root / 'window'
        result = subprocess.run(['cc', '-std=c11', '-O2', '-Wall', '-Wextra', '-Werror', '-Wno-unused-function',
                                 '-DGENESIS_SDL2', *self.cflags, str(path), '-o', str(binary), *self.libs], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        return binary

    def run_sdl(self, binary, args=()):
        environment = dict(os.environ, SDL_VIDEODRIVER='dummy', SDL_RENDER_DRIVER='software')
        return subprocess.run([str(binary), *args], env=environment, capture_output=True, text=True, timeout=10)

    def check(self, body):
        program = analyze(rom_with('4e72 2700'), [0x200])
        harness = '''
#include <assert.h>
static void key(Uint32 type, SDL_Keycode code, Uint8 repeat) {
    SDL_Event e={0}; e.type=type; e.key.keysym.sym=code; e.key.repeat=repeat;
    assert(SDL_PushEvent(&e)==1);
}
int main(void) {
    CPU c={0}; c.rom=rom_data; c.rom_size=sizeof rom_data;
    SDLHost h={0}; h.no_throttle=1;
    assert(sdl_host_open(&h));
''' + body + '\nsdl_host_close(&h); return 0; }\n'
        binary = self.compile_sdl('#define GENESIS_NO_MAIN\n' + emit(program) + harness)
        result = self.run_sdl(binary)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_keyboard_changes_bus_pins_and_keyup_releases(self):
        self.check('''
key(SDL_KEYDOWN,SDLK_UP,0); key(SDL_KEYDOWN,SDLK_z,0); key(SDL_KEYDOWN,SDLK_RETURN,0);
assert(sdl_host_service(&h,&c));
assert(c.pad_buttons[0]==(PAD_UP|PAD_A|PAD_START));
io_write(&c,4,0x40); io_write(&c,1,0x40); assert(io_read(&c,1)==0x7e);
io_write(&c,1,0); assert(io_read(&c,1)==2);
key(SDL_KEYUP,SDLK_UP,0); key(SDL_KEYUP,SDLK_z,0); key(SDL_KEYUP,SDLK_RETURN,0);
assert(sdl_host_service(&h,&c)); assert(!c.pad_buttons[0]);
''')

    def test_focus_loss_releases_pad_and_fast_forward(self):
        self.check('''
key(SDL_KEYDOWN,SDLK_RIGHT,0); key(SDL_KEYDOWN,SDLK_TAB,0);
assert(sdl_host_service(&h,&c)); assert(c.pad_buttons[0]==PAD_RIGHT && h.fast_forward);
SDL_Event e={0}; e.type=SDL_WINDOWEVENT; e.window.event=SDL_WINDOWEVENT_FOCUS_LOST;
assert(SDL_PushEvent(&e)==1); assert(sdl_host_service(&h,&c));
assert(!c.pad_buttons[0] && !h.fast_forward);
''')

    def test_pause_ignores_repeat_rebases_clock_and_escape_quits(self):
        self.check('''
c.master_cycles=53693175;
key(SDL_KEYDOWN,SDLK_SPACE,0); assert(sdl_host_service(&h,&c)); assert(h.paused);
assert(h.origin_master==c.master_cycles);
key(SDL_KEYDOWN,SDLK_SPACE,1); assert(sdl_host_service(&h,&c)); assert(h.paused);
key(SDL_KEYDOWN,SDLK_SPACE,0); assert(sdl_host_service(&h,&c)); assert(!h.paused);
key(SDL_KEYDOWN,SDLK_ESCAPE,0); assert(!sdl_host_service(&h,&c));
''')

    def test_rgb_texture_resolution_changes_and_redraw(self):
        self.check('''
assert(sdl_host_service(&h,&c)); assert(!h.texture);
c.vdp.frame_width=320; c.vdp.frame_height=224; c.vdp.rendered_frames=1;
for (unsigned p=0;p<320*224;++p) c.vdp.frame[p*3]=255;
assert(sdl_host_service(&h,&c)); assert(h.texture && h.last_frame==1);
int w=0,hg=0; SDL_RenderGetLogicalSize(h.renderer,&w,&hg); assert(w==320 && hg==224);
SDL_Rect pixel={480,336,1,1}; uint8_t rgb[3]={0};
assert(!SDL_RenderReadPixels(h.renderer,&pixel,SDL_PIXELFORMAT_RGB24,rgb,3));
assert(rgb[0]==255 && rgb[1]==0 && rgb[2]==0);
memset(c.vdp.frame,0,sizeof c.vdp.frame);
c.vdp.frame_width=256; c.vdp.frame_height=240; c.vdp.rendered_frames=2;
for (unsigned p=0;p<256*240;++p) c.vdp.frame[p*3+1]=255;
assert(sdl_host_service(&h,&c)); SDL_RenderGetLogicalSize(h.renderer,&w,&hg);
assert(w==256 && hg==240 && h.last_frame==2);
assert(!SDL_RenderReadPixels(h.renderer,&pixel,SDL_PIXELFORMAT_RGB24,rgb,3));
assert(rgb[0]==0 && rgb[1]==255 && rgb[2]==0);
SDL_Event e={0}; e.type=SDL_WINDOWEVENT; e.window.event=SDL_WINDOWEVENT_EXPOSED;
assert(SDL_PushEvent(&e)==1); assert(sdl_host_service(&h,&c)); assert(h.last_frame==2);
''')

    def test_cli_window_budget_halt_and_headless(self):
        rom = self.root / 'demo.bin'
        rom.write_bytes(make_demo())
        binary = self.root / 'sdl-demo'
        self.assertEqual(main([str(rom), '--build', '--frontend', 'sdl2', '-o', str(binary)]), 0)
        limited = self.run_sdl(binary, ['--window', '--no-throttle', '--limit', '1'])
        self.assertEqual(limited.returncode, 2, limited.stderr)
        self.assertIn('status=budget steps=1', limited.stdout)
        halted = self.run_sdl(binary, ['--window', '--limit', '100'])
        self.assertEqual(halted.returncode, 0, halted.stderr)
        self.assertIn('status=halted steps=18', halted.stdout)
        # With --headless even a window-enabled binary needs no display server.
        environment = dict(os.environ, SDL_VIDEODRIVER='nonexistent-video-driver')
        headless = subprocess.run([str(binary), '--headless'], env=environment, capture_output=True, text=True, timeout=10)
        self.assertEqual(headless.returncode, 0, headless.stderr)
        bad_video = subprocess.run([str(binary), '--window'], env=environment, capture_output=True, text=True, timeout=10)
        self.assertEqual(bad_video.returncode, 1)
        self.assertIn('SDL2 initialization failed', bad_video.stderr)

    def test_unlimited_window_quit_returns_zero_before_first_frame(self):
        program = analyze(make_demo(), [0x200])
        source = '#define main genesis_generated_main\n' + emit(program) + '''
#undef main
#include <assert.h>
int main(void) {
    assert(SDL_Init(SDL_INIT_EVENTS)==0);
    SDL_Event event={0}; event.type=SDL_QUIT;
    assert(SDL_PushEvent(&event)==1);
    char *args[]={"demo","--window",NULL};
    return run_main(2,args,rom_data,sizeof rom_data,0);
}
'''
        result = self.run_sdl(self.compile_sdl(source))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('status=closed steps=0', result.stdout)

    def test_explicit_window_budget_does_not_freeze_on_cpu_fault(self):
        program = analyze(rom_with('4ed0'), [0x200])  # JMP (A0) into undiscovered code.
        result = self.run_sdl(self.compile_sdl(emit(program)), ['--window', '--limit', '10'])
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertIn('status=fault steps=2', result.stdout)
        self.assertIn('PC has no translated instruction', result.stderr)
