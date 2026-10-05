"""Native-room motion, original battle actors and elevated aperture ownership."""
import os
import subprocess
from pathlib import Path

from genesis_recompiler.decode import analyze
from genesis_recompiler.emit import emit
from support import CompiledTestCase, rom_with
from test_rings_scene import CONTEXT
from test_rings_zoom import ZOOM_SCENE
import test_rings_wide as wide_tests


def motion_source():
    rom = bytearray(0x100000)
    rom[:0x400] = rom_with('4e72 2700')
    # Synthetic packed resources: an actor and an overlapping wall.
    actor = bytes([0x20, 0x22, 0x22]) * 32 + b'\0'
    wall = bytes([0x20, 0x33, 0x33]) * 32 + b'\0'
    rom[0x603e4:0x603e4 + len(actor) + len(wall)] = actor + wall
    rom[0x5f528:0x5f52c] = len(actor).to_bytes(4, 'big')
    # Same calling convention as the verified indoor party writer. No shadow.
    code = bytes.fromhex('4e56 0000 4267 3f2e 000e 3f2e 000c 3f3c 0000 '
                         '4eb9 0000e358 508f 4ef9 00023624')
    rom[0x2343a:0x2343a + len(code)] = code
    rom[0x23624:0x23628] = bytes.fromhex('4e5e 4e75')
    rom[0xe358:0xe35a] = bytes.fromhex('4e75')
    source = ('#define GENESIS_NO_MAIN\n#define GENESIS_RINGS_WIDE\n'
              '#define GENESIS_RINGS_SMOOTH_CAMERA\n#define GENESIS_RINGS_SAVES\n'
              + emit(analyze(bytes(rom), [0x200, 0x2343a])))
    source += '\n' + (Path(__file__).resolve().parents[1] / 'genesis_recompiler/rings_camera.h').read_text()
    source += '\n#include <assert.h>\n' + ZOOM_SCENE + CONTEXT + r'''
static void native_scene(CPU *c,RingsWide *w) {
 zoom_scene(c,w);w->shadow=calloc(1,sizeof(CPU));assert(w->shadow);
 CPU *shadow=w->shadow;shadow->rom=c->rom;shadow->rom_size=c->rom_size;
 context(c,0xb09c,0,2);c->ram[0xe8f]=5;c->ram[0xe91]=6;
 w->native.valid=w->native.hero_valid=1;w->native.count=1;
 w->native.camera=rings_camera_capture(c);w->native.camera.generation=1;
 w->native.hero_x=208;w->native.hero_y=112;
 RingsNativeDraw *d=&w->native.draw[0];
 d->id=0;d->x=208;d->y=80;d->hero=1;d->actor=1;d->ground=112;
 /* A decorative aperture edge above the actor's ground footprint. */
 memset(c->vdp.vram+0xa000,0,0x1000);
 unsigned at=0xa000+(10*64+20)*2;c->vdp.vram[at+1]=2;
}
'''
    return source


class RingsNativeMotionTests(CompiledTestCase):
    def check(self, body):
        source = motion_source() + r'''
int main(void) {
 CPU *c=calloc(1,sizeof *c);RingsWide *w=calloc(1,sizeof *w);assert(c&&w);
 native_scene(c,w);
''' + body + '\nfree(w->shadow);free(w);free(c);return 0;}\n'
        result = subprocess.run([str(self.compile(source))], capture_output=True, text=True, timeout=20)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_zero_type_indoor_map_camera_tracks_coordinates_not_data_origin(self):
        self.check(r'''
RingsCameraSnapshot a=rings_camera_capture(c);assert(a.valid && a.x==-14 && a.y==88);
VDP *v=&c->vdp;vdp_render(c);assert(v->native_motion.valid && v->camera.valid);
RingsCameraTween t={0};t.enabled=1;rings_camera_update(&t,v,1000,1000,50);
/* A larger indoor map scrolls, although its map-data origin is fixed. */
c->ram[0xe8f]=6;w->native.camera=rings_camera_capture(c);w->native.camera.generation=2;
vdp_render(c);rings_camera_update(&t,v,1100,1000,50);
assert(t.native && t.percent==100 && t.active && t.x==14 && t.y==8);
rings_camera_update(&t,v,1200,1000,50);assert(t.x==7 && t.y==4);
rings_camera_update(&t,v,1300,1000,50);assert(!t.active && !t.x && !t.y);
/* A fixed camera does not move when only the hero changes tiles. */
w->native.hero_x+=14;w->native.hero_y+=8;w->native.camera.generation++;
vdp_render(c);rings_camera_update(&t,v,1400,1000,50);
assert(!t.active && t.hero_active && t.hero_x==-14 && t.hero_y==-8);
''')

    def test_indoor_party_writer_without_shadow_is_captured_and_only_hero_moves(self):
        self.check(r'''
w->native_work.count=0;w->native_work.hero_valid=0;w->tile_ground_y=80;
c->pc=0x2343a;c->a[7]=0xfff000;c->sr=0x2700;
write_mem(c,c->a[7],4,0x1b9e8);write_mem(c,c->a[7]+4,4,0xffb0cc);
write_mem(c,c->a[7]+8,2,208);write_mem(c,c->a[7]+10,2,80);write_mem(c,c->a[7]+12,2,-7);
uint8_t ram[65536];memcpy(ram,c->ram,sizeof ram);uint64_t clocks=c->master_cycles;
assert(rings_wide_replay(c,10));assert(!memcmp(ram,c->ram,sizeof ram) && clocks==c->master_cycles);
assert(w->native_work.count==1 && w->native_work.draw[0].hero && w->native_work.hero_valid);
assert(w->native_work.hero_x==208 && w->native_work.hero_y==93);
write_mem(c,c->a[7]+4,4,0xffb0d8);memset(&w->native_work,0,sizeof w->native_work);
assert(rings_wide_replay(c,10));assert(!w->native_work.hero_valid && !w->native_work.draw[0].hero);
''')

    def test_native_elevation_spills_over_frame_and_moves_with_actor_not_wall(self):
        self.check(r'''
VDP *v=&c->vdp;vdp_render(c);assert(v->native_motion.valid);
unsigned p=(80+RINGS_ZOOM_TOP)*RINGS_ZOOM_WIDTH+160+RINGS_ZOOM_LEFT+24;
assert(v->zoom_scene[p]==2 && v->zoom_lift[p]==32);
assert(v->zoom_mask[80*320+160] && v->zoom_restore[80*320+160]);
/* Elevation is also retained for a masked spill layer and actor offsets. */
v->zoom_mask[80*320+160]=0;
assert(rings_zoom_spill(v,480,340,100));
uint8_t *pixels=malloc(RINGS_ZOOM_WIDTH*RINGS_ZOOM_HEIGHT),*lift=malloc(RINGS_ZOOM_WIDTH*RINGS_ZOOM_HEIGHT);
assert(pixels&&lift);assert(rings_native_pixels(c,v,14,8,pixels,lift));
unsigned moved=p+8*RINGS_ZOOM_WIDTH+14;assert(!pixels[p] && pixels[moved]==2 && lift[moved]==32);
assert(rings_zoom_spill_layer(v,pixels,lift,494,348,100,0,0));
/* Later opaque walls retain draw order and overwrite the actor's ownership. */
w->native.count=2;w->native.draw[1]=w->native.draw[0];
w->native.draw[1].id=1;w->native.draw[1].x+=14;w->native.draw[1].y+=8;
w->native.draw[1].hero=0;w->native.draw[1].actor=0;w->native.draw[1].ground=0;
vdp_render(c);assert(rings_native_pixels(c,v,14,8,pixels,lift));
assert(pixels[moved]==3 && !lift[moved]);free(pixels);free(lift);
''')

    def test_combat_discards_stale_native_motion_and_retains_original_actors(self):
        self.check(r'''
context(c,0xb0bc,0,2);assert(rings_scene_battle(c));
w->native.camera.identity=rings_scene_identity(c);w->native_pending=1;
vdp_render(c);assert(c->vdp.native_scene && !c->vdp.native_motion.valid && !c->vdp.camera.valid);
c->pc=0x1b950;c->ram[0x99]=1;rings_wide_observe(c);
assert(!w->native.valid && !w->native_pending && !w->failures);
/* Neither indoor descriptor is mistaken for combat. */
context(c,0xb0ac,0,2);assert(!rings_scene_battle(c));
context(c,0xb09c,0,2);assert(!rings_scene_battle(c));
''')


class RingsNativeMotionSDLTests(CompiledTestCase):
    @classmethod
    def setUpClass(cls):
        wide_tests.RingsWideSDLTests.setUpClass.__func__(cls)

    def test_native_spill_is_visible_and_battle_pixels_match_smoothing_off(self):
        source = motion_source() + r'''
int main(void) {
 CPU *c=calloc(1,sizeof *c);RingsWide *w=calloc(1,sizeof *w);assert(c&&w);native_scene(c,w);
 SDLHost h={0};h.no_throttle=1;h.camera.enabled=1;h.zoom_percent=50;assert(sdl_host_open(&h));
 vdp_render(c);assert(sdl_host_service(&h,c));assert(h.camera.native && h.actor_scene);
 int width,height;assert(!SDL_GetRendererOutputSize(h.renderer,&width,&height));
 uint8_t *pixels=malloc(width*height*3),*off=malloc(width*height*3);assert(pixels&&off);
 assert(!SDL_RenderReadPixels(h.renderer,NULL,SDL_PIXELFORMAT_RGB24,pixels,width*3));
 double scale=(double)width/320;if((double)height/224<scale)scale=(double)height/224;
 unsigned x=(width-(int)(320*scale))/2+(unsigned)(161*scale);
 unsigned y=(height-(int)(224*scale))/2+(unsigned)(81*scale),p=(y*width+x)*3;
 assert(pixels[p]==0 && pixels[p+1]==255 && pixels[p+2]==0);
 /* Move the actor across the aperture edge; the interpolated lift must follow. */
 h.camera.hero_x=14;h.camera.hero_y=8;assert(sdl_host_draw(&h,&c->vdp));
 assert(h.native_actor_x==14 && h.native_actor_y==8 && h.motion_lift[(348*960)+494]==32);
 for(unsigned wide=0;wide<2;++wide)for(unsigned zoom=50;zoom<=100;zoom+=10) {
  context(c,0xb0bc,0,2);w->native.valid=1;w->native.camera.identity=rings_scene_identity(c);
  c->vdp.wide_enabled=(uint8_t)wide;h.zoom_percent=zoom;
  /* Combat changes bitmap actors independently of the last captured room. */
  unsigned tile=w->bank+10*36+20-2;memset(c->vdp.vram+tile*32,0x33,32);
  h.camera.enabled=1;vdp_render(c);assert(sdl_host_service(&h,c));
  assert(!h.camera.ready && !h.last_smooth && !c->vdp.native_motion.valid);
  assert(!SDL_RenderReadPixels(h.renderer,NULL,SDL_PIXELFORMAT_RGB24,pixels,width*3));
  h.camera.enabled=0;assert(sdl_host_draw(&h,&c->vdp));
  assert(!SDL_RenderReadPixels(h.renderer,NULL,SDL_PIXELFORMAT_RGB24,off,width*3));
  assert(!memcmp(pixels,off,width*height*3));
 }
 free(off);free(pixels);sdl_host_close(&h);free(w->shadow);free(w);free(c);return 0;
}
'''
        path = self.root / 'motion.c';path.write_text(source);binary = self.root / 'motion'
        result = subprocess.run(['cc','-std=c11','-O2','-Wall','-Wextra','-Werror','-Wno-unused-function',
                                 '-DGENESIS_SDL2',*self.flags,str(path),'-o',str(binary),*self.libs],
                                capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stderr)
        result = subprocess.run([str(binary)],env=dict(os.environ,SDL_VIDEODRIVER='dummy',SDL_RENDER_DRIVER='software'),
                                capture_output=True,text=True,timeout=20)
        self.assertEqual(result.returncode,0,result.stderr)
