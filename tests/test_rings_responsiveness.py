"""Earlier resolved scenes and live direction intent with stock game scheduling."""
import subprocess
from genesis_recompiler.decode import analyze
from genesis_recompiler.emit import emit
from support import CompiledTestCase, rom_with
from test_rings_zoom import ZOOM_SCENE
from test_rings_hud import HUD_SCENE
import test_sdl as sdl_tests

class RingsEarlySceneTests(CompiledTestCase):
    def check(self,body):
        source=('#define GENESIS_NO_MAIN\n#define GENESIS_RINGS_WIDE\n#define GENESIS_RINGS_SMOOTH_CAMERA\n'
                +emit(analyze(rom_with('4e72 2700'),[0x200])))
        source+='\n#include <assert.h>\n'+ZOOM_SCENE+r'''
int main(void) {
 CPU *c=calloc(1,sizeof *c);assert(c);RingsWide w={0};zoom_scene(c,&w);
 c->vdp.wide_enabled=1;vdp_render(c);assert(c->vdp.zoom_world_visible);
 c->ram[0x8674]=4;w.identity=w.identity_work=123;w.pending=w.zoom_pending=1;
 memset(w.zoom_work,1,sizeof w.zoom_work);w.camera_work.valid=1;w.camera_work.x=14;
 c->pc=0x1b950;c->master_cycles=700;c->cycles=100;
 uint8_t before[65536];memcpy(before,c->ram,sizeof before);
'''+body+r'''
 assert(!memcmp(before,c->ram,sizeof before));assert(c->master_cycles==700 && c->cycles==100 && !c->steps);
 free(c);return 0;
}
'''
        result=subprocess.run([str(self.compile(source))],capture_output=True,text=True,timeout=15)
        self.assertEqual(result.returncode,0,result.stderr)

    def test_resolved_scene_is_visible_before_upload_and_committed_only_once(self):
        self.check(r'''
assert(rings_wide_early_ready(c));rings_wide_observe(c);
assert(w.scenes==1 && !w.pending && w.camera.x==14);
/* The video snapshot changes on rendering; the original VRAM/RAM stays untouched. */
assert(c->vdp.wide_frame[(96*400+160)*3+1]==255);
vdp_render(c);assert(c->vdp.wide_frame[(96*400+160)*3]==255);
assert(c->vdp.camera.x==14 && c->vdp.camera.clocks==700);
c->pc=0x1b9ee;rings_wide_observe(c);assert(w.scenes==1);
''')

    def test_initial_changed_map_bank_dialogue_and_incomplete_replay_wait(self):
        self.check(r'''
for(unsigned reason=0;reason<7;++reason) {
 w.valid=w.zoom_valid=w.zoom_pending=1;w.identity=w.identity_work=123;w.bank=1024;
 if(reason==0)w.identity=0;
 if(reason==1)w.identity_work=124;
 if(reason==2)w.bank=1025;
 if(reason==3)c->ram[0xad]=1;
 if(reason==4)c->ram[0x111]=1;
 if(reason==5)c->ram[0x113]=1;
 if(reason==6)w.zoom_pending=0;
 assert(!rings_wide_early_ready(c));
 c->ram[0xad]=c->ram[0x111]=c->ram[0x113]=0;
}
w.bank=1024;w.zoom_pending=1;w.identity=0;c->pc=0x1b950;rings_wide_observe(c);
assert(w.pending && !w.scenes);c->pc=0x1b9ee;rings_wide_observe(c);assert(w.scenes==1);
''')

class RingsLiveDirectionTests(CompiledTestCase):
    @classmethod
    def setUpClass(cls):sdl_tests.SDLTests.setUpClass.__func__(cls)
    compile_sdl=sdl_tests.SDLTests.compile_sdl
    run_sdl=sdl_tests.SDLTests.run_sdl
    def check(self,body):
        source=('#define GENESIS_NO_MAIN\n#define GENESIS_RINGS_WIDE\n#define GENESIS_RINGS_SAVES\n'
                +emit(analyze(rom_with('4e72 2700'),[0x200])))
        source+='\n#include <assert.h>\n'+HUD_SCENE+r'''
static void event(Uint32 type,SDL_Keycode key) {
 SDL_Event e={0};e.type=type;e.key.keysym.sym=key;e.key.repeat=0;assert(SDL_PushEvent(&e)==1);
}
static unsigned decide(SDLHost *h,CPU *c,unsigned old) {
 c->pc=0x12ff8;c->d[0]=0x12340000|old;rings_pad_observe(h,c);return c->d[0];
}
int main(void) {
 CPU *c=calloc(1,sizeof *c);assert(c);RingsWide w={0};hud_scene(c,&w);vdp_render(c);
 SDLHost h={0};h.no_throttle=1;assert(sdl_host_open(&h));h.settings.ready=1;h.settings.enhanced=1;
 uint8_t before[65536];memcpy(before,c->ram,sizeof before);
'''+body+r'''
 assert(!memcmp(before,c->ram,sizeof before));assert(!c->steps && !c->cycles && !c->master_cycles);
 sdl_host_close(&h);free(c);return 0;
}
'''
        result=self.run_sdl(self.compile_sdl(source));self.assertEqual(result.returncode,0,result.stderr)

    def test_press_release_reversal_and_short_tap_are_not_delayed_or_repeated(self):
        self.check(r'''
event(SDL_KEYDOWN,SDLK_RIGHT);assert(sdl_host_service(&h,c));assert(decide(&h,c,0)==0x12340008);
event(SDL_KEYUP,SDLK_RIGHT);assert(sdl_host_service(&h,c));assert(decide(&h,c,8)==0x12340000);
event(SDL_KEYDOWN,SDLK_LEFT);event(SDL_KEYUP,SDLK_LEFT);assert(sdl_host_service(&h,c));
assert(!c->pad_buttons[0]);assert(decide(&h,c,0)==0x12340004);
assert(decide(&h,c,4)==0x12340000);assert(decide(&h,c,4)==0x12340000);
event(SDL_KEYDOWN,SDLK_UP);event(SDL_KEYUP,SDLK_UP);event(SDL_KEYDOWN,SDLK_DOWN);
assert(sdl_host_service(&h,c));assert(decide(&h,c,1)==0x12340002);
event(SDL_KEYUP,SDLK_DOWN);assert(sdl_host_service(&h,c));
rings_pad_sample(&h,c,PAD_LEFT);rings_pad_sample(&h,c,0);
assert(decide(&h,c,0x41)==0x12340041 && h.pad_intent.pending==PAD_LEFT);
assert(decide(&h,c,0)==0x12340004);assert(decide(&h,c,4)==0x12340000);
rings_pad_sample(&h,c,PAD_RIGHT);rings_pad_sample(&h,c,0);h.pad_intent.deadline=0;
c->master_cycles=1;assert(decide(&h,c,0)==0x12340000);c->master_cycles=0;
''')

    def test_classic_actions_menus_autowalk_and_other_decoders_keep_native_input(self):
        self.check(r'''
c->pad_buttons[0]=PAD_RIGHT;
for(unsigned reason=0;reason<10;++reason) {
 if(reason==0)h.settings.enhanced=0;
 if(reason==1)c->ram[0xad]=1;
 if(reason==2)c->ram[0x111]=1;
 if(reason==3)c->ram[0x113]=1;
 if(reason==4)c->ram[0x129]=1;
 if(reason==5)h.paused=1;
 if(reason==6)h.settings.menu=1;
 if(reason==7)c->ram[0xaf]=2;
 if(reason==8)c->pad_buttons[0]=PAD_A|PAD_RIGHT;
 if(reason==9)h.input.focused=0;
 assert(decide(&h,c,1)==0x12340001);
 h.settings.enhanced=1;c->ram[0xad]=c->ram[0x111]=c->ram[0x113]=c->ram[0x129]=c->ram[0xaf]=0;
 h.paused=h.settings.menu=0;c->pad_buttons[0]=PAD_RIGHT;h.input.focused=1;
}
assert(decide(&h,c,0x41)==0x12340041);assert(decide(&h,c,0x81)==0x12340081);
c->pc=0xd36c;c->d[0]=7;rings_pad_observe(&h,c);assert(c->d[0]==7);
c->pad_buttons[0]=0;
''')

    def test_load_focus_loss_pause_and_mouse_cancel_stale_keyboard_intent(self):
        self.check(r'''
RingsSaves saves={0};h.saves=&saves;
for(unsigned reason=0;reason<3;++reason) {
 rings_pad_sample(&h,c,PAD_RIGHT);rings_pad_sample(&h,c,0);assert(h.pad_intent.pending);
 if(reason==0)rings_save_host_loaded(&h,c);
 if(reason==1) {h.input.focused=0;rings_pad_sample(&h,c,0);h.input.focused=1;}
 if(reason==2) {h.paused=1;rings_pad_sample(&h,c,0);h.paused=0;}
 assert(decide(&h,c,8)==0x12340000);
}
w.motion.enabled=w.motion.active=1;w.motion.intent=&h.pad_intent;
h.mouse.enabled=1;h.mouse.left=1;h.mouse.direction=PAD_UP;
c->pc=0x12ff8;c->d[0]=PAD_RIGHT;rings_pad_observe(&h,c);rings_mouse_observe(&h,c);
assert(c->d[0]==PAD_UP);
''')

    def test_native_size_sdl_view_shows_completed_scene_without_smoothing_or_zoom(self):
        self.check(r'''c->vdp.wide_enabled=0;h.zoom_percent=100;SDL_SetWindowSize(h.window,320,224);
memset(c->vdp.vram+0xa000,0,4096);vdp_render(c);assert(sdl_host_service(&h,c));
uint8_t pixels[320*224*3];assert(!SDL_RenderReadPixels(h.renderer,NULL,SDL_PIXELFORMAT_RGB24,pixels,320*3));
unsigned at=(96*320+160)*3;assert(pixels[at+1]==255 && !pixels[at]);
w.pending=w.zoom_pending=1;w.identity=w.identity_work=1;c->ram[0x8674]=4;
memset(w.zoom_work,3,sizeof w.zoom_work);c->pc=0x1b950;rings_wide_observe(c);
vdp_render(c);assert(sdl_host_service(&h,c));
assert(!SDL_RenderReadPixels(h.renderer,NULL,SDL_PIXELFORMAT_RGB24,pixels,320*3));
assert(pixels[at+2]==255 && !pixels[at+1]);c->ram[0x8674]=0;
''')
