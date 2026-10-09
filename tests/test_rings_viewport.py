"""Native aperture zoom checks using SDL2 without an optional font dependency."""
from genesis_recompiler.decode import analyze
from genesis_recompiler.emit import emit
from support import CompiledTestCase, rom_with
from test_rings_zoom import ZOOM_SCENE
import test_rings_zoom as zoom_tests
import test_sdl as sdl_tests


class RingsViewportSDLTests(CompiledTestCase):
    @classmethod
    def setUpClass(cls):sdl_tests.SDLTests.setUpClass.__func__(cls)
    compile_sdl=sdl_tests.SDLTests.compile_sdl
    run_sdl=sdl_tests.SDLTests.run_sdl

    def check_sdl(self,body):
        source='#define GENESIS_NO_MAIN\n#define GENESIS_RINGS_WIDE\n#define GENESIS_RINGS_SMOOTH_CAMERA\n'+emit(analyze(rom_with('4e72 2700'),[0x200]))
        source+='\n#include <assert.h>\n'+ZOOM_SCENE+r'''
static void wheel(int delta,unsigned direction) {
 SDL_Event e={0};e.type=SDL_MOUSEWHEEL;e.wheel.y=delta;e.wheel.direction=direction;
 assert(SDL_PushEvent(&e)==1);
}
int main(void) {
 CPU *c=calloc(1,sizeof *c);RingsWide *world=calloc(1,sizeof *world);assert(c && world);
 zoom_scene(c,world);RingsWide *wp=world;(void)wp;
 SDLHost h={0};h.no_throttle=1;assert(sdl_host_open(&h));
'''+body.replace('w.', 'wp->')+'\nsdl_host_close(&h);free(world);free(c);return 0;}\n'
        result=self.run_sdl(self.compile_sdl(source));self.assertEqual(result.returncode,0,result.stderr)

    def test_ground_is_clipped_at_all_zoom_steps_and_reset_restores_the_frame(self):
        zoom_tests.RingsZoomSDLTests.test_device_native_zoom_keeps_aperture_at_every_scale_and_removes_old_world_ghosts(self)

    def test_elevated_silhouettes_stay_in_front_of_frame_and_behind_ui_at_all_zoom_steps(self):
        zoom_tests.RingsZoomSDLTests.test_device_elevated_objects_spill_over_frame_but_stay_behind_ui(self)

    def test_moving_ground_and_roofs_use_the_fixed_aperture_at_every_zoom_step(self):
        self.check_sdl(r'''
unsigned at=0xa000+(5*64+10)*2;c->vdp.vram[at]=0;c->vdp.vram[at+1]=1;
at=0x1000+(5*64+12)*2;c->vdp.vram[at]=0x80;c->vdp.vram[at+1]=1;
w.camera.valid=1;w.camera.identity=9;h.camera.enabled=1;
uint8_t rgb[3];SDL_Rect frame={80*3+1,40*3+1,1,1},ui={96*3+1,40*3+1,1,1};
for(unsigned percent=50;percent<=100;percent+=10)for(unsigned elevated=0;elevated<2;++elevated) {
 memset(w.lift_scene,elevated ? 48:0,sizeof w.lift_scene);vdp_render(c);h.zoom_percent=percent;
 for(int direction=-1;direction<=1;++direction) {
  h.camera.x=direction*4;h.camera.y=direction*2;h.last_frame=UINT64_MAX;
  assert(sdl_host_draw(&h,&c->vdp));
  assert(!SDL_RenderReadPixels(h.renderer,&frame,SDL_PIXELFORMAT_RGB24,rgb,3));
  assert(!rgb[0] && rgb[1]==(elevated ? 255:0) && rgb[2]==(elevated ? 0:255));
  assert(!SDL_RenderReadPixels(h.renderer,&ui,SDL_PIXELFORMAT_RGB24,rgb,3));
  assert(!rgb[0] && !rgb[1] && rgb[2]==255);
 }
}
assert(!c->steps && !c->cycles && !c->fault && !SDL_RenderIsClipEnabled(h.renderer));
''')
