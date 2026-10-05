"""Camera catch-up without modifying console clocks, input or save formats."""
import contextlib
import io
import os
from pathlib import Path
import subprocess

from genesis_recompiler.cli import main
from genesis_recompiler.decode import analyze
from genesis_recompiler.emit import emit
from support import CompiledTestCase, rom_with
from test_rings_zoom import ZOOM_SCENE
import test_rings_wide as wide_tests


class RingsCameraTests(CompiledTestCase):
    def check(self, body):
        source = '#define GENESIS_NO_MAIN\n#define GENESIS_RINGS_WIDE\n#define GENESIS_RINGS_SMOOTH_CAMERA\n#define GENESIS_RINGS_SAVES\n' + emit(analyze(rom_with('4e72 2700'), [0x200]))
        # The tween belongs to the host, which is absent in a headless build.
        source += '\n' + (Path(__file__).resolve().parents[1] / 'genesis_recompiler/rings_camera.h').read_text()
        source += '\n#include <assert.h>\n' + ZOOM_SCENE + r'''
int main(void) {
 CPU *c=calloc(1,sizeof *c);assert(c);RingsWide w={0};zoom_scene(c,&w);
 VDP *v=&c->vdp;v->zoom_world_visible=1;v->camera.valid=1;v->camera.identity=12;v->camera.generation=1;
 v->zoom_focus_x=480;v->zoom_focus_y=356;
 RingsCameraTween t={0};t.enabled=1;t.duration_ms=200;
 rings_camera_update(&t,v,1000,1000,100);
''' + body + '\nfree(c);return 0;}\n'
        result = subprocess.run([str(self.compile(source))], capture_output=True, text=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_finite_catchup_freezes_and_settles_without_prediction(self):
        self.check(r'''
v->camera.generation++;v->camera.x=28;v->camera.y=16;
rings_camera_update(&t,v,1100,1000,100);assert(t.x==28 && t.y==16 && t.active);
for(unsigned ms=1110;ms<1300;ms+=10) {
 rings_camera_update(&t,v,ms,1000,100);
 assert(rings_camera_abs(t.x-28*(1300-ms)/200.0)<0.000001);
}
double x=t.x,y=t.y;rings_camera_update(&t,v,1290,1000,100);assert(t.x==x && t.y==y);
rings_camera_update(&t,v,1300,1000,100);assert(!t.active && !t.x && !t.y);
rings_camera_update(&t,v,10000,1000,100);assert(!t.active && !t.x);
assert(t.transitions==1 && !c->steps && !c->master_cycles && !c->pad_buttons[0]);
''')

    def test_new_camera_step_continues_from_previous_visible_position(self):
        self.check(r'''
v->camera.generation++;v->camera.x=28;rings_camera_update(&t,v,1100,1000,100);
v->camera.generation++;v->camera.x=56;rings_camera_update(&t,v,1200,1000,100);
assert(t.x==42 && t.active && t.transitions==2);
rings_camera_update(&t,v,1400,1000,100);assert(!t.x && !t.active);
''')

    def test_zoom_anchor_compensation_and_discontinuous_scene_resets(self):
        self.check(r'''
rings_camera_update(&t,v,1000,1000,50);
v->camera.generation++;v->camera.x=28;v->camera.y=16;v->zoom_focus_x+=4;v->zoom_focus_y+=2;
rings_camera_update(&t,v,1100,1000,50);assert(t.x==12 && t.y==7);
v->camera.generation++;v->camera.identity++;rings_camera_update(&t,v,1150,1000,50);assert(!t.active && !t.x);
v->camera.generation++;v->camera.x+=14;rings_camera_update(&t,v,1200,1000,50);assert(t.active);
v->camera.generation++;v->camera.x+=1000;rings_camera_update(&t,v,1220,1000,50);assert(!t.active && !t.x);
v->camera.generation++;v->camera.x+=14;rings_camera_update(&t,v,1230,1000,50);assert(t.active);
rings_camera_update(&t,v,1240,1000,80);assert(!t.active && !t.x);
v->camera.generation++;v->camera.x+=14;rings_camera_update(&t,v,1250,1000,80);assert(t.active);
v->zoom_world_visible=0;rings_camera_update(&t,v,1260,1000,80);assert(!t.active && !t.ready);
v->zoom_world_visible=1;rings_camera_update(&t,v,1270,1000,80);assert(!t.active);
v->camera.valid=0;rings_camera_update(&t,v,1280,1000,80);assert(!t.ready);
''')

    def test_capture_and_commit_use_the_submitted_scene_and_skip_rooms(self):
        self.check(r'''
c->ram[0xa7fc]=0xff;c->ram[0xa7fd]=0xff;c->ram[0xa7fe]=0xb0;c->ram[0xa7ff]=0x8c;
c->ram[0xe8f]=111;c->ram[0xe91]=125;c->ram[0xb099]=1;
RingsCameraSnapshot a=rings_camera_capture(c);assert(a.valid && a.x==-196 && a.y==1888);
c->ram[0xb099]=0;assert(!rings_camera_capture(c).valid);c->ram[0xb099]=1;
c->ram[0x8674]=4;c->ram[0x8675]=0;w.camera_work=a;w.pending=1;c->pc=0x1b9ee;c->master_cycles=123456;
c->ram[0xe8f]=115;rings_wide_observe(c);
assert(w.camera.x==-196 && w.camera.generation==1 && w.camera.clocks==123456);
vdp_render(c);assert(v->camera.x==-196 && v->camera.generation==1);
''')

    def test_elevated_spill_uses_the_shifted_ground_position(self):
        self.check(r'''
unsigned sx=480,sy=344,p=sy*RINGS_ZOOM_WIDTH+sx;
v->frame_width=320;v->frame_height=224;v->zoom_scene[p]=2;v->zoom_lift[p]=12;
memset(v->zoom_mask,0,sizeof v->zoom_mask);v->zoom_mask[96*320+160]=1;
assert(rings_zoom_spill_shift(v,sx,sy,100,0,0));
assert(!rings_zoom_spill_shift(v,sx,sy,100,14,8));
v->zoom_mask[104*320+174]=1;assert(rings_zoom_spill_shift(v,sx,sy,100,14,8));
assert(!rings_zoom_spill_shift(v,sx,sy,100,400,0));
''')

    def test_save_load_discards_only_camera_presentation_history(self):
        self.check(r'''
c->a[7]=0xffff00;c->sr=0x2700;c->pc=0x200;c->rom=rom_data;c->rom_size=sizeof rom_data;
c->d[0]=123;c->pad_buttons[0]=PAD_RIGHT;w.camera=v->camera;
SaveCodec s={0};assert(save_encode(c,&s));c->d[0]=456;
assert(save_decode(c,s.data,s.pos));assert(c->d[0]==123);
assert(!c->vdp.camera.valid && !w.camera.valid && !w.camera_work.valid);
free(s.data);
''')

    def test_option_requires_sdl_and_verified_rom(self):
        rom=self.root/'demo.gen';rom.write_bytes(rom_with('4e72 2700'))
        with contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as exc:main([str(rom),'--rings-smooth-camera','-o',str(self.root/'game')])
            self.assertEqual(exc.exception.code,2)
            self.assertEqual(main([str(rom),'--build','--frontend','sdl2','--rings-smooth-camera','-o',str(self.root/'game')]),1)
        result=self.execute(rom.read_bytes(),['--smooth-camera'])
        self.assertEqual(result.returncode,64);self.assertIn('smooth camera support is not compiled in',result.stderr)


class RingsCameraSDLTests(CompiledTestCase):
    @classmethod
    def setUpClass(cls):
        wide_tests.RingsWideSDLTests.setUpClass.__func__(cls)

    def test_moving_world_keeps_hud_fixed_and_f6_leaves_pad_unchanged(self):
        source='#define GENESIS_NO_MAIN\n#define GENESIS_RINGS_SAVES\n'+emit(analyze(rom_with('4e72 2700'),[0x200]))
        source+='\n#include <assert.h>\n'+ZOOM_SCENE+r'''
int main(void) {
 CPU *c=calloc(1,sizeof *c);assert(c);RingsWide w={0};zoom_scene(c,&w);
 unsigned at=0x1000+(5*64+10)*2;c->vdp.vram[at]=0x80;c->vdp.vram[at+1]=1;
 w.camera.valid=1;w.camera.identity=3;w.camera.generation=1;
 SDLHost h={0};h.no_throttle=1;h.camera.enabled=1;assert(sdl_host_open(&h));
 for(unsigned wide=0;wide<2;++wide)for(unsigned percent=50;percent<=100;percent+=10) {
  c->vdp.wide_enabled=(uint8_t)wide;h.zoom_percent=percent;rings_camera_reset(&h.camera);
  vdp_render(c);assert(sdl_host_service(&h,c));assert(h.camera.ready);
  uint8_t before[1200*672*3],after[1200*672*3];int width,height;
  assert(!SDL_GetRendererOutputSize(h.renderer,&width,&height));
  assert(!SDL_RenderReadPixels(h.renderer,NULL,SDL_PIXELFORMAT_RGB24,before,width*3));
  w.camera.generation++;w.camera.x+=28;w.camera.y+=16;vdp_render(c);
  assert(sdl_host_service(&h,c));assert(h.camera.active);
  c->master_cycles+=vdp_master_frequency(&c->vdp)/10;vdp_render(c);assert(sdl_host_service(&h,c));
  assert(h.camera.x>0 && h.camera.x<=14.1);
  assert(!SDL_RenderReadPixels(h.renderer,NULL,SDL_PIXELFORMAT_RGB24,after,width*3));
  /* A priority HUD tile is protected in both layouts and at every zoom. */
  double scale=(double)width/h.width;if((double)height/h.height<scale)scale=(double)height/h.height;
  int left=(width-(int)(h.width*scale+0.5))/2,top=(height-(int)(h.height*scale+0.5))/2;
  unsigned ux=(unsigned)(left+(84+wide*40)*scale),uy=(unsigned)(top+44*scale);
  for(unsigned y=uy;y<uy+4;++y)for(unsigned x=ux;x<ux+4;++x)
   assert(!memcmp(before+(y*width+x)*3,after+(y*width+x)*3,3));
  assert(memcmp(before,after,width*height*3));
  c->master_cycles+=vdp_master_frequency(&c->vdp)/5;vdp_render(c);assert(sdl_host_service(&h,c));
  assert(!h.camera.active && !h.camera.x);
 }
 SDL_Event held={0};held.type=SDL_KEYDOWN;held.key.keysym.sym=SDLK_RIGHT;
 assert(SDL_PushEvent(&held)==1);assert(sdl_host_service(&h,c));uint64_t clocks=c->master_cycles;
 SDL_Event e={0};e.type=SDL_KEYDOWN;e.key.keysym.sym=SDLK_F6;assert(SDL_PushEvent(&e)==1);
 assert(sdl_host_service(&h,c));assert(!h.camera.enabled && c->pad_buttons[0]==PAD_RIGHT && c->master_cycles==clocks);
 assert(SDL_PushEvent(&e)==1);assert(sdl_host_service(&h,c));assert(h.camera.enabled);
 h.camera.active=1;h.camera.x=23;RingsSaves saves={0};h.saves=&saves;rings_save_host_loaded(&h,c);
 assert(!h.camera.ready && !h.camera.active && !h.camera.x);
 sdl_host_close(&h);free(c);return 0;
}
'''
        path=self.root/'camera.c';path.write_text(source);binary=self.root/'camera'
        result=subprocess.run(['cc','-std=c11','-O2','-Wall','-Wextra','-Werror','-Wno-unused-function',
            '-DGENESIS_SDL2','-DGENESIS_RINGS_WIDE','-DGENESIS_RINGS_SMOOTH_CAMERA','-DGENESIS_RINGS_MENU_FONT',
            *self.flags,str(path),'-o',str(binary),*self.libs],capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stderr)
        result=subprocess.run([str(binary)],env=dict(os.environ,SDL_VIDEODRIVER='dummy',SDL_RENDER_DRIVER='software'),capture_output=True,text=True,timeout=20)
        self.assertEqual(result.returncode,0,result.stderr)
