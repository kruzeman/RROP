"""Independent actor composition, clipping, zoom and settled-frame fidelity."""
from genesis_recompiler.decode import analyze
from genesis_recompiler.emit import emit
from support import CompiledTestCase, rom_with
from test_rings_zoom import ZOOM_SCENE
import test_sdl as sdl_tests


class RingsHeroSDLTests(CompiledTestCase):
    @classmethod
    def setUpClass(cls):sdl_tests.SDLTests.setUpClass.__func__(cls)
    compile_sdl=sdl_tests.SDLTests.compile_sdl
    run_sdl=sdl_tests.SDLTests.run_sdl

    def test_separate_actor_layer_keeps_settled_pixels_and_moves_without_camera_drag(self):
        source='#define GENESIS_NO_MAIN\n#define GENESIS_RINGS_WIDE\n#define GENESIS_RINGS_SMOOTH_CAMERA\n'+emit(analyze(rom_with('4e72 2700'),[0x200]))
        source+='\n#include <assert.h>\n'+ZOOM_SCENE+r'''
static void center(const uint8_t *pixels,int width,int height,double *x,double *y) {
 double sx=0,sy=0,n=0;
 for(int yy=0;yy<height;++yy)for(int xx=0;xx<width;++xx) {
  const uint8_t *p=pixels+(yy*width+xx)*3;
  if(p[0]==255 && p[1]==145 && !p[2]) {sx+=xx;sy+=yy;++n;}
 }
 assert(n>0);*x=sx/n;*y=sy/n;
}
int main(void) {
 CPU *c=calloc(1,sizeof *c);RingsWide *w=calloc(1,sizeof *w);assert(c && w);zoom_scene(c,w);
 w->camera.valid=1;w->camera.identity=9;w->camera.generation=1;c->vdp.cram[5]=0x008e;
 RingsHeroLayer *a=&w->hero;a->valid=1;a->x=416;a->y=260;a->ground_y=356;
 for(unsigned y=0;y<128;++y)memcpy(a->under+y*128,w->zoom_scene+(a->y+y)*960+a->x,128);
 for(unsigned y=70;y<100;++y)for(unsigned x=44;x<78;++x) {
  if((x*7+y*11)%9>=4)continue;
  unsigned p=y*128+x;a->ink[p]=5;w->zoom_scene[(a->y+y)*960+a->x+x]=5;
 }
 SDLHost h={0};h.no_throttle=1;assert(sdl_host_open(&h));
 int width,height;assert(!SDL_GetRendererOutputSize(h.renderer,&width,&height));
 uint8_t *before=malloc(width*height*3),*after=malloc(width*height*3);assert(before && after);
 for(unsigned wide=0;wide<2;++wide)for(unsigned zoom=50;zoom<=100;zoom+=50) {
  c->vdp.wide_enabled=(uint8_t)wide;h.zoom_percent=zoom;h.camera.enabled=0;
  vdp_render(c);assert(sdl_host_service(&h,c));
  assert(!SDL_RenderReadPixels(h.renderer,NULL,SDL_PIXELFORMAT_RGB24,before,width*3));
  h.camera.enabled=1;rings_camera_reset(&h.camera);assert(sdl_host_service(&h,c));
  assert(!SDL_RenderReadPixels(h.renderer,NULL,SDL_PIXELFORMAT_RGB24,after,width*3));
  assert(!memcmp(before,after,width*height*3));
  double x0,y0,x1,y1;center(before,width,height,&x0,&y0);
  h.camera.x=14*zoom/100.0;h.camera.y=8*zoom/100.0;h.camera.hx=-14;h.camera.hy=-8;
  assert(sdl_host_draw(&h,&c->vdp));
  assert(!SDL_RenderReadPixels(h.renderer,NULL,SDL_PIXELFORMAT_RGB24,after,width*3));
  center(after,width,height,&x1,&y1);assert(rings_camera_abs(x1-x0)<=1 && rings_camera_abs(y1-y0)<=1);
  /* A later opaque foreground removes the displaced player at its destination. */
  memset(c->vdp.hero.cover,1,sizeof c->vdp.hero.cover);h.last_frame=UINT64_MAX;
  assert(sdl_host_draw(&h,&c->vdp));
  assert(!SDL_RenderReadPixels(h.renderer,NULL,SDL_PIXELFORMAT_RGB24,after,width*3));
  for(int p=0;p<width*height;++p)assert(!(after[p*3]==255 && after[p*3+1]==145 && !after[p*3+2]));
 }
 assert(!c->master_cycles && !c->steps && !c->pad_buttons[0]);
 free(before);free(after);sdl_host_close(&h);free(w);free(c);return 0;
}
'''
        result=self.run_sdl(self.compile_sdl(source));self.assertEqual(result.returncode,0,result.stderr)

    def test_native_scene_preserves_boundary_cliffs_and_complete_roof_silhouettes(self):
        source='#define GENESIS_NO_MAIN\n#define GENESIS_RINGS_WIDE\n#define GENESIS_RINGS_SMOOTH_CAMERA\n'+emit(analyze(rom_with('4e72 2700'),[0x200]))
        source+='\n#include <assert.h>\n'+ZOOM_SCENE+r'''
int main(void) {
 CPU *c=calloc(1,sizeof *c);RingsWide *w=calloc(1,sizeof *w);assert(c && w);zoom_scene(c,w);
 w->camera.valid=1;w->camera.identity=9;w->native_valid=1;
 /* Expanded neighboring cells cover the native cliff, but must not replace it. */
 /* A roof crosses a decorative B cell; its ground lands on the opaque edge. */
 unsigned at=0xa000+(5*64+10)*2;c->vdp.vram[at]=0;c->vdp.vram[at+1]=1;
 for(unsigned y=40;y<48;++y)for(unsigned x=80;x<88;++x) {
  w->native_scene[y*288+x-16]=3;w->native_lift_scene[y*288+x-16]=(uint8_t)(47-y);
 }
 /* A real priority HUD remains in front of both scene versions. */
 at=0x1000+(12*64+20)*2;c->vdp.vram[at]=0x80;c->vdp.vram[at+1]=2;
 vdp_render(c);
 for(unsigned y=0;y<184;++y)for(unsigned x=16;x<304;++x)
  w->native_scene[y*288+x-16]=(uint8_t)(vdp_window_pixel(&c->vdp,x,y,1)&15);
 for(unsigned y=40;y<48;++y)for(unsigned x=80;x<88;++x)w->native_scene[y*288+x-16]=3;
 vdp_render(c);
 for(unsigned y=40;y<48;++y)for(unsigned x=80;x<88;++x) {
  unsigned p=y*320+x;c->vdp.frame[p*3]=c->vdp.frame[p*3+1]=0;c->vdp.frame[p*3+2]=255;
  assert(c->vdp.native_lift[y*288+x-16]==48-(int)y);
 }
 SDLHost h={0};h.no_throttle=1;assert(sdl_host_open(&h));
 int width,height;assert(!SDL_GetRendererOutputSize(h.renderer,&width,&height));
 uint8_t *before=malloc(width*height*3),*after=malloc(width*height*3);assert(before && after);
 c->vdp.zoom_enabled=0;h.camera.enabled=0;assert(sdl_host_draw(&h,&c->vdp));
 assert(!SDL_RenderReadPixels(h.renderer,NULL,SDL_PIXELFORMAT_RGB24,before,width*3));
 c->vdp.zoom_enabled=1;
 for(unsigned smooth=0;smooth<2;++smooth) {
  h.camera.enabled=smooth;h.last_frame=UINT64_MAX;assert(sdl_host_draw(&h,&c->vdp));
  assert(!SDL_RenderReadPixels(h.renderer,NULL,SDL_PIXELFORMAT_RGB24,after,width*3));
  assert(!memcmp(before,after,width*height*3));
 }
 /* Camera travel does not change the fixed aperture or priority UI. */
 h.camera.x=4;assert(sdl_host_draw(&h,&c->vdp));
 assert(!SDL_RenderReadPixels(h.renderer,NULL,SDL_PIXELFORMAT_RGB24,after,width*3));
 unsigned hud=(96*3*width+160*3)*3;assert(!memcmp(before+hud,after+hud,3));
 /* Wheel zoom and wide presentation still use the expanded map. */
 h.zoom_percent=50;h.camera.x=0;assert(!rings_native_view(&h,&c->vdp));
 assert(rings_world_ink(&h,&c->vdp,356*960+480)==2);
 h.zoom_percent=100;c->vdp.wide_enabled=1;assert(!rings_native_view(&h,&c->vdp));
 assert(rings_world_ink(&h,&c->vdp,356*960+480)==2);
 free(before);free(after);sdl_host_close(&h);free(w);free(c);return 0;
}
'''
        result=self.run_sdl(self.compile_sdl(source));self.assertEqual(result.returncode,0,result.stderr)
