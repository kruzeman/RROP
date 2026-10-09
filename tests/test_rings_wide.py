"""Presentation-only expanded scene checks; synthetic ROM data is not a game."""
import os
import hashlib
from pathlib import Path
import subprocess
import unittest

from genesis_recompiler.build import BuildError, sdl2_flags, sdl2_ttf_flags
from genesis_recompiler.cli import main
from genesis_recompiler.decode import analyze
from genesis_recompiler.emit import emit
from support import CompiledTestCase, rom_with
from test_rings_fonts import LIVE_TEXT


SCENE = r'''
static void scene(CPU *c,RingsWide *w) {
 c->wide=w;c->vdp.wide_enabled=1;w->valid=1;w->bank=128;
 VDP *v=&c->vdp;v->registers[1]=0x44;v->registers[12]=1;
 v->registers[3]=4;v->registers[17]=0x80;v->registers[4]=5;v->registers[16]=1;
 v->cram[1]=0x000e;v->cram[2]=0x00e0;v->cram[3]=0x0e00;v->cram[4]=0x0eee;
 memset(v->vram+32,0x33,32);memset(v->vram+64,0x44,32);
 for(unsigned x=2;x<38;++x) {
  unsigned value=128+x-2,at=0x1000+x*2;
  v->vram[at]=(uint8_t)(value>>8);v->vram[at+1]=(uint8_t)value;
  memset(v->vram+value*32,0x11,32);
 }
 memset(w->scene,2,sizeof w->scene);
 w->zoom_valid=1;memset(w->zoom_scene,2,sizeof w->zoom_scene);
}
'''


class RingsWideTests(CompiledTestCase):
    def check(self, body, resource=False, looping=False, smooth=False):
        rom=bytearray(0x100000 if resource else 0x1b960 if looping else 0x400)
        rom[:0x400]=rom_with('4e72 2700')
        if resource:
            rom[0x603e4:0x603eb]=bytes([0x21,0x10,0x23,0x12,0x04,0,0])
        if looping:rom[0x1b950:0x1b952]=bytes.fromhex('60fe')
        p=analyze(bytes(rom),[0x200,*([0x1b950] if looping else [])])
        source='#define GENESIS_NO_MAIN\n#define GENESIS_RINGS_WIDE\n'+('#define GENESIS_RINGS_SMOOTH_CAMERA\n' if smooth else '')+emit(p)
        source+='\n#include <assert.h>\n'+SCENE+'\nint main(void) { CPU *c=calloc(1,sizeof *c);assert(c);RingsWide w={0};(void)w;c->rom=rom_data;c->rom_size=sizeof rom_data;\n'+body+'\nfree(c);return 0;}'
        binary=self.compile(source)
        result=subprocess.run([str(binary)],capture_output=True,text=True,timeout=15)
        self.assertEqual(result.returncode,0,result.stderr)

    def test_packed_resource_transparency_mirror_shift_and_clipping(self):
        self.check(r'''
uint8_t *data=malloc(368*184+2);assert(data);memset(data,7,368*184+2);
uint8_t *out=data+1;
assert(rings_wide_resource(c,out,368,184,0,64,0,0,40));
assert(out[42]==1 && out[43]==7 && out[44]==2 && out[45]==3);
assert(out[368+44]==7 && out[368+45]==4);
assert(rings_wide_resource(c,out,368,184,0,64,2,1,0));
assert(out[2*368+24]==7 && out[2*368+25]==1);
assert(out[2*368+22]==3 && out[2*368+23]==2);
assert(rings_wide_resource(c,out,368,184,0,60,-1,0,0));
assert(out[1]==4);assert(data[0]==7 && data[368*184+1]==7);
assert(rings_wide_resource(c,out,368,184,0,400,0,0,0));
assert(data[0]==7 && data[368*184+1]==7 && !c->fault);
free(data);
''',resource=True)

    def test_elevation_tracks_opaque_writer_and_clears_when_ground_covers_it(self):
        self.check(r'''
c->wide=&w;w.replaying=1;w.grid=32;w.resource_ground=14;
memset(w.lift_work,7,sizeof w.lift_work);
assert(rings_wide_resource(c,w.zoom_work,RINGS_ZOOM_WIDTH,RINGS_ZOOM_HEIGHT,0,64,0,0,0));
assert(w.lift_work[2]==14 && w.lift_work[3]==7 && w.lift_work[4]==14);
/* Zero nibbles preserve the earlier owner, opaque floor clears elevation. */
w.resource_ground=0;
assert(rings_wide_resource(c,w.zoom_work,RINGS_ZOOM_WIDTH,RINGS_ZOOM_HEIGHT,0,64,0,0,0));
assert(w.lift_work[2]==0 && w.lift_work[3]==7 && w.lift_work[4]==0);
w.resource_actor=1;w.resource_ground=4;
assert(rings_wide_resource(c,w.zoom_work,RINGS_ZOOM_WIDTH,RINGS_ZOOM_HEIGHT,0,64,0,0,0));
assert(w.lift_work[2]==4 && w.lift_work[RINGS_ZOOM_WIDTH+5]==3);
/* Wide rendering never uses the native aperture's height metadata. */
w.grid=80;w.resource_ground=50;
assert(rings_wide_resource(c,w.zoom_work,RINGS_ZOOM_WIDTH,RINGS_ZOOM_HEIGHT,0,64,0,0,0));
assert(w.lift_work[2]==4);
''',resource=True)

    def test_terrain_roofs_have_intrinsic_lift_above_the_flat_tile_footprint(self):
        self.check(r'''
assert(rings_resource_lift(0,0,0,1)==13);
assert(rings_resource_lift(0,0,13,1)==7);
assert(rings_resource_lift(14,0,27,1)==27);
assert(!rings_resource_lift(0,14,13,1));
assert(!rings_resource_lift(0,0,13,0));
assert(rings_resource_lift(300,0,0,1)==255);
/* Height belongs to the final writer; transparent nibbles retain ownership. */
c->wide=&w;w.replaying=1;w.grid=32;w.resource_actor=2;w.resource_ground=0;
memset(w.lift_work,5,sizeof w.lift_work);
assert(rings_wide_resource(c,w.zoom_work,960,704,0,64,0,0,0));
assert(w.lift_work[2]==12 && w.lift_work[3]==5 && w.lift_work[4]==11);
''',resource=True)

    def test_native_snapshot_is_published_with_the_same_completed_scene(self):
        self.check(r'''
scene(c,&w);c->vdp.wide_enabled=0;c->vdp.zoom_enabled=1;
c->ram[0x8674]=0;c->ram[0x8675]=128;
w.pending=w.zoom_pending=w.native_pending=1;
memset(w.zoom_work,2,sizeof w.zoom_work);memset(w.native_work,3,sizeof w.native_work);
memset(w.native_lift_work,17,sizeof w.native_lift_work);
rings_wide_commit(c);assert(w.native_valid && !w.native_pending);
vdp_render(c);assert(c->vdp.native_world_valid && c->vdp.native_world[0]==3);
assert(c->vdp.native_lift[0]==17 && c->vdp.zoom_scene[0]==2);
/* Mutable work and later scene RAM cannot change a paused frame. */
memset(w.native_work,1,sizeof w.native_work);memset(w.native_scene,4,sizeof w.native_scene);
assert(c->vdp.native_world[0]==3);
rings_scene_discard(c);vdp_render(c);assert(!c->vdp.native_world_valid);
''')

    def test_player_layer_retains_terrain_and_later_foreground_through_resource_writes(self):
        self.check(r'''
c->wide=&w;w.replaying=1;w.grid=32;w.resource_actor=1;w.resource_ground=360;
memset(w.zoom_work,7,sizeof w.zoom_work);memset(w.lift_work,5,sizeof w.lift_work);
rings_hero_begin(&w,194,83,0);assert(w.hero_work.valid && w.hero_work.x==416 && w.hero_work.y==260);
w.tracking_player=1;
assert(rings_wide_resource(c,w.zoom_work,960,704,0,64,356,0,416));
unsigned p=96*128+2,q=356*960+418;
assert(w.hero_work.ink[p]==1 && w.hero_work.under[p]==7 && !w.hero_work.cover[p]);
assert(w.hero_work.under_lift[p]==5 && w.zoom_work[q]==1 && w.lift_work[q]==4);
/* A later foreground writer covers the actor and becomes its true underlay. */
uint8_t *rom=malloc(sizeof rom_data);assert(rom);memcpy(rom,rom_data,sizeof rom_data);
rom[0x603e5]=0x56;c->rom=rom;w.tracking_player=0;w.resource_actor=0;w.resource_ground=0;
assert(rings_wide_resource(c,w.zoom_work,960,704,0,64,356,0,416));
assert(w.hero_work.ink[p]==1 && w.hero_work.under[p]==5 && w.hero_work.cover[p]);
assert(!w.hero_work.under_lift[p] && w.zoom_work[q]==5);
assert(!w.hero_work.ink[p+1] && w.hero_work.under[p+1]==6 && w.hero_work.cover[p+1]);
assert(w.hero_work.under[p+6]==7); /* Transparent pixels preserve prior terrain. */
free(rom);
''',resource=True,smooth=True)

    def test_packed_resource_rounds_odd_x_down_like_the_original_writer(self):
        self.check(r'''
uint8_t first[368*184]={0},second[368*184]={0};
assert(rings_wide_resource(c,first,368,184,0,65,0,0,0));
assert(rings_wide_resource(c,second,368,184,0,64,0,0,0));
assert(!memcmp(first,second,sizeof first));
''',resource=True)

    def test_invalid_and_unterminated_resources_are_rejected(self):
        self.check(r'''
assert(!rings_wide_resource(c,w.work,368,184,944,64,0,0,0) && !c->fault);
uint8_t *copy=malloc(sizeof rom_data);assert(copy);memcpy(copy,rom_data,sizeof rom_data);c->rom=copy;
memset(copy+0x603e4,1,65);
assert(!rings_wide_resource(c,w.work,368,184,0,64,0,0,0) && !c->fault);
copy[0x5f524]=0xff;copy[0x5f525]=0xff;copy[0x5f526]=0xff;copy[0x5f527]=0xff;
assert(!rings_wide_resource(c,w.work,368,184,0,64,0,0,0) && !c->fault);free(copy);
''',resource=True)

    def test_wide_scene_preserves_native_frame_ram_and_ui(self):
        self.check(r'''
scene(c,&w);
/* A high-priority UI cell and a sprite override the expanded world. */
c->vdp.vram[0x1000+10*2]=0x80;c->vdp.vram[0x1000+10*2+1]=1;
c->vdp.registers[5]=0x60;
c->vdp.vram[0xc001]=128;c->vdp.vram[0xc005]=2;c->vdp.vram[0xc007]=128+112;
uint8_t saved[65536];memcpy(saved,c->ram,sizeof saved);
vdp_render(c);assert(c->vdp.wide_world_visible);
unsigned wide=(40*400+20)*3;
assert(!c->vdp.wide_frame[wide] && c->vdp.wide_frame[wide+1]==255);
unsigned ui=(40+80)*3;
assert(c->vdp.wide_frame[ui+2]==255 && !c->vdp.wide_frame[ui+1]);
unsigned sprite=(40+112)*3;
assert(c->vdp.wide_frame[sprite]==255 && c->vdp.wide_frame[sprite+1]==255);
uint8_t *native=malloc(sizeof c->vdp.frame);assert(native);memcpy(native,c->vdp.frame,sizeof c->vdp.frame);
c->vdp.wide_enabled=0;vdp_render(c);
assert(!memcmp(native,c->vdp.frame,sizeof c->vdp.frame) && !memcmp(saved,c->ram,sizeof saved));
assert(c->steps==0 && c->cycles==0);free(native);
''')

    def test_menu_and_unsupported_modes_keep_the_centered_native_frame(self):
        self.check(r'''
scene(c,&w);vdp_render(c);assert(c->vdp.wide_world_visible);
c->vdp.registers[17]=0;vdp_render(c);assert(!c->vdp.wide_world_visible);
for(unsigned y=0;y<224;++y)assert(!memcmp(c->vdp.wide_frame+(y*400+40)*3,c->vdp.frame+y*320*3,320*3));
c->vdp.registers[17]=0x80;c->vdp.registers[12]|=8;vdp_render(c);
assert(!c->vdp.wide_world_visible);
''')

    def test_full_wide_world_replaces_decorations_and_keeps_only_interface_ink(self):
        self.check(r'''
scene(c,&w);c->vdp.registers[5]=0x60;
/* Low-priority plane B is decorative; transparent priority A is not an opaque HUD. */
for(unsigned y=0;y<32;++y)for(unsigned x=0;x<64;++x)
 c->vdp.vram[0xa000+(y*64+x)*2+1]=1;
unsigned at=0x1000+(25*64+10)*2;c->vdp.vram[at]=0x80;
c->vdp.vram[at+1]=0; /* transparent priority cell over the world */
at=0x1000+(25*64+11)*2;c->vdp.vram[at]=0x80;c->vdp.vram[at+1]=2;
c->vdp.vram[0xc000]=1;c->vdp.vram[0xc001]=80;
c->vdp.vram[0xc005]=2;c->vdp.vram[0xc007]=128+112;
vdp_render(c);assert(c->vdp.wide_world_visible && c->vdp.zoom_world_visible);
for(unsigned y=0;y<224;++y)for(unsigned x=0;x<400;++x) {
 unsigned p=y*400+x;
 int hud=(y>=200 && y<208 && x>=128 && x<136) || (y>=208 && y<216 && x>=152 && x<160);
 assert(c->vdp.zoom_mask[p]==!hud);
 assert(c->vdp.wide_frame[p*3+1]==255 && c->vdp.wide_frame[p*3]==(hud ? 255:0));
}
assert(!c->vdp.zoom_enabled); /* Full wide view works without enabling wheel zoom. */
c->vdp.pal=1;c->vdp.registers[1]|=8;vdp_render(c);
assert(c->vdp.frame_height==240 && c->vdp.wide_frame[(239*400+399)*3+1]==255);
assert(!c->steps && !c->cycles && !c->fault);
''')

    def test_wide_snapshot_does_not_read_future_scene_data(self):
        self.check(r'''
scene(c,&w);vdp_render(c);
unsigned at=(40*400+20)*3;assert(c->vdp.wide_frame[at+1]==255);
memset(w.zoom_scene,1,sizeof w.zoom_scene);assert(c->vdp.wide_frame[at+1]==255);
vdp_render(c);assert(c->vdp.wide_frame[at]==255 && !c->vdp.wide_frame[at+1]);
''')

    def test_failed_traversal_changes_only_presentation_state(self):
        self.check(r'''
assert(rings_wide_open(c,&w));c->pc=0x1b950;c->a[7]=0xffff00;c->d[4]=0x12345678;c->ram[0x98]=1;
uint8_t saved[65536];memcpy(saved,c->ram,sizeof saved);
assert(!rings_wide_replay(c,14));
assert(w.failures==1 && !w.replaying && !c->fault && c->pc==0x1b950);
assert(c->d[4]==0x12345678 && c->a[7]==0xffff00 && c->steps==0 && c->cycles==0);
assert(!memcmp(saved,c->ram,sizeof saved));rings_wide_close(c);
''')

    def test_extra_cells_cannot_read_actor_indices_outside_the_original_caches(self):
        self.check(r'''
c->wide=&w;w.replaying=1;
unsigned pcs[]={0x1bcd2,0x1bd1e},bases[]={0xffb36c,0xffb76c};
for(unsigned grid=14;grid<=32;grid+=18)for(unsigned i=0;i<2;++i) {
 w.grid=(uint8_t)grid;
 c->pc=pcs[i];c->d[0]=1023;c->d[1]=31;c->ram[(bases[i]+1023)&65535]=7;
 assert(read_mem(c,bases[i]+1023,1)==7);
 assert(read_mem(c,bases[i]-1,1)==255 && read_mem(c,bases[i]+1024,1)==255);
 c->d[0]=32;c->d[1]=32;assert(read_mem(c,bases[i]+32,1)==255);
 c->d[0]=31;c->d[1]=0xffffffff;assert(read_mem(c,bases[i]+31,1)==255);
 w.replaying=0;assert(read_mem(c,bases[i]+1024,1)==0);w.replaying=1;
}
assert(!c->fault);
''')

    def test_traversal_budget_stops_an_unfinished_scene(self):
        self.check(r'''
assert(rings_wide_open(c,&w));c->pc=0x1b950;
assert(!rings_wide_replay(c,14) && w.failures==1);
assert(!c->fault && c->pc==0x1b950 && !c->steps && !c->cycles);rings_wide_close(c);
''',looping=True)

    def test_cli_requires_verified_rom_and_compiled_runtime_support(self):
        rom=self.root/'demo.bin';rom.write_bytes(rom_with('4e72 2700'))
        self.assertEqual(main([str(rom),'--build','--rings-widescreen','-o',str(self.root/'demo')]),1)
        result=self.execute(rom.read_bytes(),['--widescreen'])
        self.assertEqual(result.returncode,64)
        self.assertIn('widescreen support is not compiled in',result.stderr)


class RingsWideROMTests(CompiledTestCase):
    """Optional ABI comparison against a user-supplied, verified game ROM."""

    def test_resource_pixels_match_statically_translated_original_writer(self):
        candidate=Path(os.environ.get('GENESIS_TEST_RINGS_ROM',
            str(Path(__file__).resolve().parents[1]/'build/rings-of-power/Rings of Power (UE) [!].gen')))
        if not candidate.is_file():self.skipTest('local Rings ROM is not supplied')
        rom=candidate.read_bytes()
        if hashlib.sha256(rom).hexdigest()!='36303fc447c433ebc69c3d4df86c783c86b383e0acead1c19595f13269e248f5':
            self.skipTest('local Rings ROM revision does not match')
        entries={int.from_bytes(rom[at:at+4],'big') for at in range(0xdf58,0xe358,4)}
        program=analyze(rom,[0xe358,*entries]);self.assertEqual(program.errors,{})
        source='#define GENESIS_NO_MAIN\n#define GENESIS_RINGS_WIDE\n'+emit(program)+r'''
#include <assert.h>
int main(void) {
 CPU *c=calloc(1,sizeof *c);RingsWide *w=calloc(1,sizeof *w);assert(c && w);uint8_t expected[288*184];
 unsigned ids[]={0,1,17,125,560,750,943};int ys[]={-22,-7,0,146};
 for(unsigned id=0;id<sizeof ids/sizeof *ids;++id)
 for(unsigned flip=0;flip<2;++flip)
 for(unsigned yi=0;yi<sizeof ys/sizeof *ys;++yi)
 for(unsigned odd=0;odd<2;++odd) {
  memset(c,0,sizeof *c);c->rom=rom_data;c->rom_size=sizeof rom_data;c->sr=0x2700;
  c->a[7]=0xffff00;c->pc=0xe358;
  write_mem(c,c->a[7],4,0x400);write_mem(c,c->a[7]+4,2,ids[id]);
  write_mem(c,c->a[7]+6,2,96+odd);write_mem(c,c->a[7]+8,2,(uint16_t)ys[yi]);
  write_mem(c,c->a[7]+10,2,flip);
  unsigned steps=0;
  while(!c->fault && c->pc!=0x400 && ++steps<50000)translated_step(c);
  assert(!c->fault && c->pc==0x400);
  memset(expected,0,sizeof expected);
  assert(rings_wide_resource(c,expected,288,184,ids[id],96+odd,ys[yi],flip,0));
  c->wide=w;w->replaying=1;w->grid=10;memset(w->zoom_work,0,sizeof w->zoom_work);
  assert(rings_wide_resource(c,w->zoom_work,960,704,ids[id],96+odd,
      ys[yi]+RINGS_ZOOM_TOP,flip,RINGS_ZOOM_LEFT+40));
  for(unsigned y=0;y<184;++y)for(unsigned x=0;x<288;++x) {
   unsigned at=0x1ec0+((y/8)*36+x/8)*32+(y%8)*4+(x%8)/2;
   unsigned value=(c->ram[at]>>(x%2 ? 0:4))&15;
   unsigned native=w->zoom_work[(y+RINGS_ZOOM_TOP)*960+x+RINGS_ZOOM_LEFT+40];
   if(value!=expected[y*288+x] || value!=native) {
    fprintf(stderr,"id=%u flip=%u x=%u y=%d pixel=%u,%u original=%u wide=%u\n",
        ids[id],flip,96+odd,ys[yi],x,y,value,expected[y*288+x]);return 1;
   }
  }
 }
 free(w);free(c);return 0;
}
'''
        binary=self.compile(source)
        result=subprocess.run([str(binary)],capture_output=True,text=True,timeout=15)
        self.assertEqual(result.returncode,0,result.stderr)


class RingsWideSDLTests(CompiledTestCase):
    @classmethod
    def setUpClass(cls):
        try:
            cls.flags,cls.libs=sdl2_flags();flags,libs=sdl2_ttf_flags();cls.flags+=flags;cls.libs+=libs
        except BuildError as exc:raise unittest.SkipTest(str(exc))
        paths=[os.environ.get('GENESIS_TEST_FONT',''),'/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf','/usr/share/fonts/truetype/open-sans/OpenSans-Regular.ttf']
        cls.font=next((p for p in paths if p and Path(p).is_file()),None)
        if not cls.font:raise unittest.SkipTest('install a test font')

    def test_fonts_stay_aligned_and_resize_with_a_wide_canvas(self):
        p=analyze(rom_with('4e72 2700'),[0x200])
        source='#define GENESIS_NO_MAIN\n'+emit(p)+'\n#include <assert.h>\n'+LIVE_TEXT+r'''
int main(int argc,char **argv) {
 assert(argc==2);CPU *c=calloc(1,sizeof *c);assert(c);RingsWide w={0};live_text(c);
 c->wide=&w;c->vdp.wide_enabled=1;SDLHost h={0};h.wide_window=1;
 assert(sdl_host_open(&h) && rings_font_open(&h.font,argv[1]));
 vdp_render(c);assert(sdl_host_draw(&h,&c->vdp));assert(h.width==400 && h.height==224);
 int pixels=h.font.pixels;
 uint8_t *rgb=malloc(1200*672*3);assert(rgb);
 assert(!SDL_RenderReadPixels(h.renderer,NULL,SDL_PIXELFORMAT_RGB24,rgb,1200*3));
 unsigned ink=0;
 for(unsigned y=312;y<336;++y)for(unsigned x=528;x<552;++x)if(rgb[(y*1200+x)*3])++ink;
 assert(ink>20);free(rgb);
 SDL_SetWindowSize(h.window,1600,896);assert(sdl_host_draw(&h,&c->vdp));assert(h.font.pixels>pixels);
 assert(!SDL_RenderIsClipEnabled(h.renderer));sdl_host_close(&h);free(c);return 0;
}
'''
        path=self.root/'wide.c';path.write_text(source);binary=self.root/'wide'
        result=subprocess.run(['cc','-std=c11','-O2','-Wall','-Wextra','-Werror','-Wno-unused-function','-DGENESIS_SDL2','-DGENESIS_RINGS_MENU_FONT','-DGENESIS_RINGS_WIDE',*self.flags,str(path),'-o',str(binary),*self.libs],capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stderr)
        result=subprocess.run([str(binary),self.font],env=dict(os.environ,SDL_VIDEODRIVER='dummy',SDL_RENDER_DRIVER='software'),capture_output=True,text=True,timeout=15)
        self.assertEqual(result.returncode,0,result.stderr)
