"""Native room smoothing, occlusion and persistent outdoor layout preferences."""
from genesis_recompiler.decode import analyze
from genesis_recompiler.emit import emit
from support import CompiledTestCase, rom_with
from test_rings_zoom import ZOOM_SCENE
from test_rings_scene import CONTEXT
import test_sdl as sdl_tests


class RingsIndoorSDLTests(CompiledTestCase):
    @classmethod
    def setUpClass(cls):sdl_tests.SDLTests.setUpClass.__func__(cls)
    compile_sdl=sdl_tests.SDLTests.compile_sdl
    run_sdl=sdl_tests.SDLTests.run_sdl

    def test_native_room_actor_moves_and_wall_occludes_without_zooming_interface(self):
        source='#define GENESIS_NO_MAIN\n#define GENESIS_RINGS_WIDE\n#define GENESIS_RINGS_SMOOTH_CAMERA\n'+emit(analyze(rom_with('4e72 2700'),[0x200]))
        source+='\n#include <assert.h>\n'+ZOOM_SCENE+CONTEXT+r'''
static double center(const uint8_t *pixels,int width,int height,int axis) {
 double sum=0,count=0;
 for(int y=0;y<height;++y)for(int x=0;x<width;++x) {
  const uint8_t *p=pixels+(y*width+x)*3;
  if(p[0]==255 && p[1]==145 && !p[2]) {sum+=axis ? y:x;++count;}
 }
 assert(count>0);return sum/count;
}
int main(void) {
 CPU *c=calloc(1,sizeof *c);RingsWide *w=calloc(1,sizeof *w);assert(c && w);zoom_scene(c,w);
 context(c,0xb0ac,0,2);c->vdp.wide_enabled=1;c->vdp.cram[5]=0x008e;
 unsigned tile=w->bank+10*36+20-2;memset(c->vdp.vram+tile*32,0x55,32);
 w->identity=rings_scene_identity(c);w->native_valid=1;
 w->camera.valid=1;w->camera.identity=w->identity;w->camera.generation=1;
 for(unsigned y=0;y<184;++y)for(unsigned x=16;x<304;++x)
  w->native_scene[y*288+x-16]=(uint8_t)(vdp_window_pixel(&c->vdp,x,y,1)&15);
 RingsHeroLayer *a=&w->native_hero;a->valid=1;a->x=432;a->y=270;a->ground_y=356;
 memset(a->under,1,sizeof a->under);
 for(unsigned y=70;y<78;++y)for(unsigned x=48;x<56;++x)a->ink[y*128+x]=5;
 SDLHost h={0};h.no_throttle=1;h.wide_window=1;h.zoom_percent=50;assert(sdl_host_open(&h));
 vdp_render(c);assert(c->vdp.native_world_valid && !c->vdp.zoom_world_visible);
 int width,height;assert(!SDL_GetRendererOutputSize(h.renderer,&width,&height));
 uint8_t *before=malloc(width*height*3),*after=malloc(width*height*3);assert(before && after);
 assert(sdl_host_service(&h,c));assert(h.width==320 && h.zoom_percent==50);
 assert(!SDL_RenderSetLogicalSize(h.renderer,0,0) && !SDL_RenderSetScale(h.renderer,1,1) && !SDL_RenderSetViewport(h.renderer,NULL));
 assert(!SDL_RenderReadPixels(h.renderer,NULL,SDL_PIXELFORMAT_RGB24,before,width*3));
 h.camera.enabled=1;assert(sdl_host_service(&h,c));assert(h.camera.ready && h.camera.percent==100);h.last_frame=UINT64_MAX;assert(sdl_host_draw(&h,&c->vdp));
 assert(!SDL_RenderReadPixels(h.renderer,NULL,SDL_PIXELFORMAT_RGB24,after,width*3));
 assert(!memcmp(before,after,width*height*3));
 double x0=center(before,width,height,0),y0=center(before,width,height,1);
 h.camera.hx=14;h.camera.hy=8;assert(sdl_host_draw(&h,&c->vdp));
 assert(!SDL_RenderReadPixels(h.renderer,NULL,SDL_PIXELFORMAT_RGB24,after,width*3));
 assert(center(after,width,height,0)==x0+42 && center(after,width,height,1)==y0+24);
 memset(c->vdp.native_hero.cover,1,sizeof c->vdp.native_hero.cover);h.last_frame=UINT64_MAX;
 assert(sdl_host_draw(&h,&c->vdp));assert(!SDL_RenderReadPixels(h.renderer,NULL,SDL_PIXELFORMAT_RGB24,after,width*3));
 for(int p=0;p<width*height;++p)assert(!(after[p*3]==255 && after[p*3+1]==145 && !after[p*3+2]));
 SDL_Event e={0};e.type=SDL_KEYDOWN;e.key.keysym.sym=SDLK_0;assert(SDL_PushEvent(&e)==1);
 e.type=SDL_MOUSEBUTTONDOWN;e.button.button=SDL_BUTTON_MIDDLE;assert(SDL_PushEvent(&e)==1);
 e.type=SDL_MOUSEWHEEL;e.wheel.y=3;assert(SDL_PushEvent(&e)==1);
 assert(sdl_host_service(&h,c));assert(h.zoom_percent==50 && c->vdp.wide_enabled);
 context(c,0xb08c,1,1);w->valid=w->zoom_valid=1;vdp_render(c);assert(sdl_host_service(&h,c));
 assert(h.width==400 && h.zoom_percent==50 && !h.camera.native);
 assert(!c->master_cycles && !c->steps && !c->pad_buttons[0]);
 free(before);free(after);sdl_host_close(&h);free(w);free(c);return 0;
}
'''
        result=self.run_sdl(self.compile_sdl(source));self.assertEqual(result.returncode,0,result.stderr)
