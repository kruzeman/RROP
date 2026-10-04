"""Mouse intent reaches one native decision, never the interrupt's pad FIFO."""
import subprocess

from genesis_recompiler.decode import analyze
from genesis_recompiler.emit import emit
from support import CompiledTestCase, rom_with
import test_sdl as sdl_tests
from test_rings_hud import HUD_SCENE


class RingsMouseTests(CompiledTestCase):
    @classmethod
    def setUpClass(cls):
        sdl_tests.SDLTests.setUpClass.__func__(cls)

    compile_sdl = sdl_tests.SDLTests.compile_sdl
    run_sdl = sdl_tests.SDLTests.run_sdl

    def check(self, body):
        source = ('#define GENESIS_NO_MAIN\n#define GENESIS_RINGS_WIDE\n'
                  '#define GENESIS_RINGS_SAVES\n#define GENESIS_RINGS_SMOOTH_CAMERA\n'
                  + emit(analyze(rom_with('4e72 2700'), [0x200])))
        source += '\n#include <assert.h>\n' + HUD_SCENE + r'''
static void point(SDLHost *h,Uint32 type,int button,double x,double y) {
 int ww,wh,lw,lh;SDL_GetWindowSize(h->window,&ww,&wh);SDL_RenderGetLogicalSize(h->renderer,&lw,&lh);
 double scale=(double)ww/h->width;if((double)wh/h->height<scale)scale=(double)wh/h->height;
 if(!lw || !lh) {x=(ww-h->width*scale)*0.5+x*scale;y=(wh-h->height*scale)*0.5+y*scale;}
 SDL_Event e={0};e.type=type;
 if(type==SDL_MOUSEMOTION) {e.motion.x=(int)x;e.motion.y=(int)y;}
 else {e.button.button=(Uint8)button;e.button.x=(int)x;e.button.y=(int)y;}
 assert(SDL_PushEvent(&e)==1);
}
static unsigned decision(SDLHost *h,CPU *c,unsigned input) {
 c->pc=0x12ff8;c->d[0]=0x12340000|input;rings_mouse_observe(h,c);
 assert((c->d[0]&0xffffff00)==0x12340000);return c->d[0]&255;
}
int main(void) {
 CPU *c=calloc(1,sizeof *c);assert(c);RingsWide w={0};hud_scene(c,&w);vdp_render(c);
 SDLHost h={0};h.no_throttle=1;h.wide_window=1;h.mouse.enabled=1;assert(sdl_host_open(&h));
 assert(sdl_host_draw(&h,&c->vdp));
''' + body + r'''
 assert(!c->steps && !c->cycles && !c->master_cycles && !c->pad_buttons[0]);
 sdl_host_close(&h);free(c);return 0;
}
'''
        result = self.run_sdl(self.compile_sdl(source))
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_short_right_click_is_one_edge_and_never_restarts_while_held(self):
        self.check(r'''
uint8_t before[65536];memcpy(before,c->ram,sizeof before);
point(&h,SDL_MOUSEBUTTONDOWN,SDL_BUTTON_RIGHT,260,50);
point(&h,SDL_MOUSEBUTTONUP,SDL_BUTTON_RIGHT,260,50);
assert(sdl_host_service(&h,c));assert(h.mouse.pending==PAD_UP);
c->pc=0xd36c;c->d[0]=77;rings_mouse_observe(&h,c);assert(c->d[0]==77 && h.mouse.pending);
assert(decision(&h,c,0)==0x41 && h.mouse.starts==1 && !h.mouse.pending);
assert(decision(&h,c,0)==0 && !memcmp(before,c->ram,sizeof before));
point(&h,SDL_MOUSEBUTTONDOWN,SDL_BUTTON_RIGHT,260,50);assert(sdl_host_service(&h,c));
c->ram[0x244]=0x41;assert(decision(&h,c,0)==0 && h.mouse.pending); /* Release before another edge. */
c->ram[0x244]=0;assert(decision(&h,c,0)==0x41 && h.mouse.starts==2);
for(unsigned i=0;i<5;++i) {
 point(&h,SDL_MOUSEBUTTONDOWN,SDL_BUTTON_RIGHT,260,50);assert(sdl_host_service(&h,c));
 assert(decision(&h,c,0)==0 && h.mouse.starts==2);
}
''')

    def test_drag_samples_current_direction_and_release_has_no_future_steps(self):
        self.check(r'''
point(&h,SDL_MOUSEBUTTONDOWN,SDL_BUTTON_LEFT,260,50);assert(sdl_host_service(&h,c));
assert(decision(&h,c,0)==PAD_UP);
point(&h,SDL_MOUSEMOTION,0,260,130);assert(sdl_host_service(&h,c));assert(decision(&h,c,0)==PAD_RIGHT);
point(&h,SDL_MOUSEMOTION,0,200.5,130);assert(sdl_host_service(&h,c));assert(decision(&h,c,0)==PAD_RIGHT);
point(&h,SDL_MOUSEMOTION,0,150,130);assert(sdl_host_service(&h,c));assert(decision(&h,c,0)==PAD_DOWN);
point(&h,SDL_MOUSEBUTTONUP,SDL_BUTTON_LEFT,150,130);assert(sdl_host_service(&h,c));
for(unsigned i=0;i<8;++i)assert(decision(&h,c,0)==0);
assert(!h.mouse.left && !h.mouse.pending && !c->ram[0x1a] && !c->ram[0x1b]);
''')

    def test_ui_dead_zone_and_letterbox_ignore_clicks(self):
        self.check(r'''
double points[][2]={{20,100},{345,170},{200,96},{-5,96},{200,-5}};
for(unsigned i=0;i<5;++i) {
 point(&h,SDL_MOUSEBUTTONDOWN,SDL_BUTTON_RIGHT,points[i][0],points[i][1]);
 point(&h,SDL_MOUSEBUTTONUP,SDL_BUTTON_RIGHT,points[i][0],points[i][1]);
 assert(sdl_host_service(&h,c));assert(decision(&h,c,0)==0 && !h.mouse.pending);
}
assert(!h.mouse.starts);
point(&h,SDL_MOUSEBUTTONDOWN,SDL_BUTTON_LEFT,20,100);
point(&h,SDL_MOUSEMOTION,0,260,50);assert(sdl_host_service(&h,c));
assert(!h.mouse.left && decision(&h,c,0)==0); /* A HUD click cannot become a walking gesture. */
''')

    def test_zoom_resize_camera_and_native_logical_events_match_the_hero(self):
        self.check(r'''
/* Open the native plane-B aperture; synthetic tile patterns alias its map. */
memset(c->vdp.vram+0xa000,0,4096);
for(unsigned wide=0;wide<2;++wide)for(unsigned percent=50;percent<=100;percent+=50) {
 c->vdp.wide_enabled=(uint8_t)wide;h.zoom_percent=percent;vdp_render(c);
 SDL_SetWindowSize(h.window,1280,900);assert(sdl_host_draw(&h,&c->vdp));
 double hx=wide ? 200:160;
 point(&h,SDL_MOUSEBUTTONDOWN,SDL_BUTTON_LEFT,hx+50,50);assert(sdl_host_service(&h,c));
 assert(decision(&h,c,0)==PAD_UP);
 point(&h,SDL_MOUSEBUTTONUP,SDL_BUTTON_LEFT,hx+50,50);assert(sdl_host_service(&h,c));
}
c->vdp.wide_enabled=1;vdp_render(c);assert(sdl_host_draw(&h,&c->vdp));
point(&h,SDL_MOUSEBUTTONDOWN,SDL_BUTTON_LEFT,150,50);assert(sdl_host_service(&h,c));
assert(decision(&h,c,0)==PAD_LEFT);
h.camera.x=-100;h.camera.y=0;rings_mouse_update(&h,c);assert(decision(&h,c,0)==PAD_UP);
point(&h,SDL_MOUSEBUTTONUP,SDL_BUTTON_LEFT,150,50);assert(sdl_host_service(&h,c));
''')

    def test_pause_focus_menu_load_and_keyboard_cancel_pending_mouse_intent(self):
        self.check(r'''
for(unsigned mode=0;mode<6;++mode) {
 point(&h,SDL_MOUSEBUTTONDOWN,SDL_BUTTON_RIGHT,260,50);
 point(&h,SDL_MOUSEBUTTONUP,SDL_BUTTON_RIGHT,260,50);assert(sdl_host_service(&h,c));assert(h.mouse.pending);
 if(mode==0) {h.paused=1;rings_mouse_update(&h,c);h.paused=0;}
 if(mode==1) {SDL_Event e={0};e.type=SDL_WINDOWEVENT;e.window.event=SDL_WINDOWEVENT_FOCUS_LOST;SDL_PushEvent(&e);assert(sdl_host_service(&h,c));}
 if(mode==2) {RingsSaves saves={0};saves.menu=1;h.saves=&saves;rings_mouse_update(&h,c);h.saves=NULL;}
 if(mode==3) {c->ram[0x111]=1;rings_mouse_update(&h,c);c->ram[0x111]=0;}
 if(mode==4) {RingsSaves saves={0};h.saves=&saves;rings_save_host_loaded(&h,c);h.saves=NULL;}
 if(mode==5) {
  SDL_Event e={0};e.type=SDL_KEYDOWN;e.key.keysym.sym=SDLK_RIGHT;SDL_PushEvent(&e);assert(sdl_host_service(&h,c));
  assert(c->pad_buttons[0]==PAD_RIGHT && decision(&h,c,PAD_RIGHT)==PAD_RIGHT);
  e.type=SDL_KEYUP;SDL_PushEvent(&e);assert(sdl_host_service(&h,c));
 }
 assert(!h.mouse.pending && decision(&h,c,0)==0);
}
''')

    def test_disabled_mouse_and_pending_timeout_leave_native_input_untouched(self):
        self.check(r'''
h.mouse.enabled=0;point(&h,SDL_MOUSEBUTTONDOWN,SDL_BUTTON_LEFT,260,50);assert(sdl_host_service(&h,c));
assert(decision(&h,c,0x85)==0x85 && !h.mouse.left);
h.mouse.enabled=1;point(&h,SDL_MOUSEBUTTONDOWN,SDL_BUTTON_RIGHT,260,50);assert(sdl_host_service(&h,c));
assert(h.mouse.pending);h.mouse.deadline=0;c->master_cycles=1;rings_mouse_update(&h,c);c->master_cycles=0;
assert(!h.mouse.pending && decision(&h,c,0x85)==0x85);
''')
