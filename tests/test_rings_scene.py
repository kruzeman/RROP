"""Fixed room/combat presentation, transitions and older save compatibility."""
import os
import subprocess

from genesis_recompiler.decode import analyze
from genesis_recompiler.emit import emit
from support import CompiledTestCase, rom_with
from test_rings_fonts import LIVE_TEXT
from test_rings_zoom import ZOOM_SCENE
import test_rings_wide as wide_tests


CONTEXT = r'''
static void context(CPU *c,unsigned at,unsigned kind,unsigned mode) {
 c->ram[0xa7fc]=0xff;c->ram[0xa7fd]=0xff;
 c->ram[0xa7fe]=(uint8_t)(at>>8);c->ram[0xa7ff]=(uint8_t)at;
 c->ram[(at+12)&65535]=(uint8_t)(kind>>8);c->ram[(at+13)&65535]=(uint8_t)kind;
 c->ram[0xae]=(uint8_t)(mode>>8);c->ram[0xaf]=(uint8_t)mode;
}
'''


class RingsSceneTests(CompiledTestCase):
    def check(self, body):
        source = ('#define GENESIS_NO_MAIN\n#define GENESIS_RINGS_WIDE\n'
                  '#define GENESIS_RINGS_SMOOTH_CAMERA\n#define GENESIS_RINGS_SAVES\n'
                  '#define GENESIS_RINGS_MENU_FONT\n' + emit(analyze(rom_with('4e72 2700'), [0x200])))
        source += '\n#include <assert.h>\n' + ZOOM_SCENE + CONTEXT + r'''
int main(void) {
 CPU *c=calloc(1,sizeof *c);assert(c);RingsWide w={0};zoom_scene(c,&w);
 c->pc=0x200;c->sr=0x2700;c->a[7]=0xffff00;
''' + body + '\nfree(c);return 0;}\n'
        result = subprocess.run([str(self.compile(source))], capture_output=True, text=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_rooms_and_battles_use_exact_native_frame_at_every_requested_zoom(self):
        self.check(r'''
uint8_t out[400*240*3],ram[65536];
for(unsigned wide=0;wide<2;++wide)for(unsigned battle=0;battle<2;++battle) {
 zoom_scene(c,&w);c->vdp.wide_enabled=(uint8_t)wide;
 context(c,battle ? 0xb0ac:0xb09c,battle ? 1:0,battle ? 2:1);
 memcpy(ram,c->ram,sizeof ram);w.pending=1;w.zoom_pending=1;w.camera.valid=1;
 vdp_render(c);VDP *v=&c->vdp;
 assert(v->native_scene && rings_view_width(v)==320 && rings_view_pixels(v,0)==v->frame);
 assert(v->wide_enabled==wide && v->zoom_enabled && !v->zoom_world_visible && !v->wide_hud_active);
 assert(!v->camera.valid && !w.valid && !w.pending && !w.zoom_valid && !w.zoom_pending);
 for(unsigned percent=50;percent<=100;percent+=10) {
  rings_zoom_pixels(v,percent,0,out);assert(!memcmp(out,v->frame,320*224*3));
 }
 /* External text uses the native frame and coordinates, too. */
 v->font_count=1;assert(rings_view_pixels(v,1)==v->font_frame);
 assert(!memcmp(ram,c->ram,sizeof ram) && c->pc==0x200 && !c->steps && !c->cycles && !c->fault);
}
''')

    def test_absent_invalid_and_outdoor_descriptors_are_not_rooms(self):
        self.check(r'''
assert(!rings_scene_native(c));
context(c,0xb08c,1,1);assert(!rings_scene_native(c));
c->ram[0xa7fc]=0;c->ram[0xa7fd]=0;assert(!rings_scene_native(c));
c->ram[0xa7fd]=0xff;c->ram[0xa7ff]|=1;assert(!rings_scene_native(c));
c->ram[0xaf]=2;assert(rings_scene_native(c));
''')

    def test_observer_skips_fixed_scenes_and_discards_unsubmitted_outdoor_work(self):
        self.check(r'''
context(c,0xb09c,0,1);c->pc=0x1b950;c->ram[0x98]=1;
w.valid=w.pending=w.zoom_valid=w.zoom_pending=1;
rings_wide_observe(c);assert(!w.valid && !w.pending && !w.zoom_valid && !w.zoom_pending && !w.failures);
/* Leaving the room must wait for a new completed outdoor scene, not reuse
   the old outdoor cache or a scene which crossed a room/combat transition. */
context(c,0xb08c,1,1);c->pc=0x1b9ee;rings_wide_observe(c);
assert(!w.valid && !w.zoom_valid && !w.scenes);
vdp_render(c);assert(!c->vdp.native_scene && !c->vdp.zoom_world_visible);
w.pending=w.zoom_pending=1;memset(w.work,2,sizeof w.work);memset(w.zoom_work,2,sizeof w.zoom_work);
c->ram[0x8674]=4;rings_wide_observe(c);vdp_render(c);
assert(w.scenes==1 && c->vdp.zoom_world_visible);
context(c,0xb08c,1,2);w.pending=w.zoom_pending=1;rings_wide_observe(c);
assert(!w.valid && !w.pending && !w.zoom_pending && w.scenes==1 && !w.failures);
''')

    def test_presentation_is_frozen_until_next_frame(self):
        self.check(r'''
context(c,0xb08c,1,1);c->vdp.wide_enabled=1;vdp_render(c);
assert(rings_view_width(&c->vdp)==400 && c->vdp.zoom_world_visible);
context(c,0xb09c,0,1);rings_wide_observe(c);
assert(rings_view_width(&c->vdp)==400 && c->vdp.zoom_world_visible);
vdp_render(c);assert(rings_view_width(&c->vdp)==320 && !c->vdp.zoom_world_visible);
context(c,0xb08c,1,1);assert(rings_view_width(&c->vdp)==320);
vdp_render(c);assert(rings_view_width(&c->vdp)==400 && !c->vdp.zoom_world_visible);
''')

    def test_old_room_and_combat_saves_are_native_before_first_redraw(self):
        self.check(r'''
for(unsigned battle=0;battle<2;++battle) {
 zoom_scene(c,&w);context(c,battle ? 0xb0ac:0xb09c,battle ? 1:0,battle ? 2:1);
 vdp_render(c);w.valid=w.zoom_valid=1;
 /* A pre-fix save may have all expanded caches marked valid. The derived
    native_scene field is deliberately absent from the save format. */
 c->vdp.wide_enabled=1;c->vdp.native_scene=0;c->vdp.zoom_world_visible=1;
 c->vdp.wide_world_visible=1;c->vdp.wide_hud_active=1;c->vdp.camera.valid=1;
 SaveCodec old={0};assert(save_encode(c,&old));
 context(c,0xb08c,1,1);assert(save_decode(c,old.data,old.size));free(old.data);
 assert(c->vdp.native_scene && rings_view_width(&c->vdp)==320);
 assert(c->vdp.wide_enabled && c->vdp.zoom_enabled && !c->vdp.zoom_world_visible && !c->vdp.wide_hud_active);
 assert(!w.valid && !w.zoom_valid && !w.pending && !c->vdp.camera.valid);
}
''')


class RingsSceneSDLTests(CompiledTestCase):
    @classmethod
    def setUpClass(cls):
        wide_tests.RingsWideSDLTests.setUpClass.__func__(cls)

    def test_fixed_scene_letterbox_wheel_camera_mouse_and_outdoor_zoom_restore(self):
        self.check(r'''
context(c,0xb08c,1,1);vdp_render(c);assert(sdl_host_service(&h,c));assert(h.width==400);
for(unsigned battle=0;battle<2;++battle) {
 context(c,battle ? 0xb0ac:0xb09c,battle ? 1:0,battle ? 2:1);
 h.camera.active=1;h.camera.x=28;h.mouse.left=1;h.mouse.pending=PAD_RIGHT;
 vdp_render(c);assert(sdl_host_service(&h,c));
 assert(h.width==320 && h.zoom_percent==50 && !h.camera.active && !h.mouse.left && !h.mouse.pending);
 SDL_Event e={0};e.type=SDL_MOUSEWHEEL;e.wheel.y=3;assert(SDL_PushEvent(&e)==1);
 assert(sdl_host_service(&h,c));assert(h.zoom_percent==50 && !c->pad_buttons[0]);
 assert(!SDL_RenderSetLogicalSize(h.renderer,0,0) && !SDL_RenderSetScale(h.renderer,1,1) && !SDL_RenderSetViewport(h.renderer,NULL));
 uint8_t *rgb=malloc(1200*672*3);assert(rgb);
 assert(!SDL_RenderReadPixels(h.renderer,NULL,SDL_PIXELFORMAT_RGB24,rgb,1200*3));
 for(unsigned y=0;y<672;++y)for(unsigned x=0;x<1200;++x) {
  const uint8_t *p=rgb+(y*1200+x)*3;
  if(x<120 || x>=1080)assert(!p[0] && !p[1] && !p[2]);
  else assert(!memcmp(p,c->vdp.frame+((y/3)*320+(x-120)/3)*3,3));
 }
 free(rgb);
}
context(c,0xb08c,1,1);w.valid=w.zoom_valid=1;vdp_render(c);
assert(sdl_host_service(&h,c));assert(h.width==400 && h.zoom_percent==50 && c->vdp.zoom_world_visible);
/* A policy/width change at a paused load must upload the recreated texture,
   even if the saved video frame counter equals the current one. */
context(c,0xb09c,0,1);rings_scene_snapshot(c);assert(sdl_host_draw(&h,&c->vdp));assert(h.width==320);
''')

    def test_room_external_font_matches_original_native_font_presentation(self):
        self.check(r'''
memset(&c->vdp,0,sizeof c->vdp);live_text(c);c->wide=&w;c->vdp.wide_enabled=1;c->vdp.zoom_enabled=1;
context(c,0xb09c,0,1);assert(rings_font_open(&h.font,argv[1]));
vdp_render(c);assert(c->vdp.font_count && sdl_host_draw(&h,&c->vdp));assert(h.width==320);
uint8_t *before=malloc(1200*672*3),*after=malloc(1200*672*3);assert(before && after);
assert(!SDL_RenderReadPixels(h.renderer,NULL,SDL_PIXELFORMAT_RGB24,before,1200*3));
c->vdp.wide_enabled=0;h.zoom_percent=100;vdp_render(c);assert(sdl_host_draw(&h,&c->vdp));
assert(!SDL_RenderReadPixels(h.renderer,NULL,SDL_PIXELFORMAT_RGB24,after,1200*3));
assert(!memcmp(before,after,1200*672*3) && !SDL_RenderIsClipEnabled(h.renderer));free(before);free(after);
''')

    def check(self, body):
        source = '#define GENESIS_NO_MAIN\n' + emit(analyze(rom_with('4e72 2700'), [0x200]))
        source += '\n#include <assert.h>\n' + ZOOM_SCENE + CONTEXT + LIVE_TEXT + r'''
int main(int argc,char **argv) {
 assert(argc==2);(void)argv;CPU *c=calloc(1,sizeof *c);assert(c);RingsWide w={0};zoom_scene(c,&w);
 c->vdp.wide_enabled=1;SDLHost h={0};h.wide_window=1;h.no_throttle=1;h.zoom_percent=50;
 h.camera.enabled=1;h.mouse.enabled=1;assert(sdl_host_open(&h));
''' + body + '\nsdl_host_close(&h);free(c);return 0;}\n'
        path = self.root/'scene.c';path.write_text(source);binary = self.root/'scene'
        result = subprocess.run(['cc', '-std=c11', '-O2', '-Wall', '-Wextra', '-Werror', '-Wno-unused-function',
                                 '-DGENESIS_SDL2', '-DGENESIS_RINGS_WIDE', '-DGENESIS_RINGS_SMOOTH_CAMERA',
                                 '-DGENESIS_RINGS_MENU_FONT', *self.flags, str(path), '-o', str(binary), *self.libs],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        result = subprocess.run([str(binary), self.font], env=dict(os.environ, SDL_VIDEODRIVER='dummy',
                                SDL_RENDER_DRIVER='software'), capture_output=True, text=True, timeout=20)
        self.assertEqual(result.returncode, 0, result.stderr)
