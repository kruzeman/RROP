"""Wide gameplay footer relocation, live font coordinates and saved snapshots."""
import os
from pathlib import Path
import subprocess

from genesis_recompiler.decode import analyze
from genesis_recompiler.emit import emit
from support import CompiledTestCase, rom_with
from test_rings_zoom import ZOOM_SCENE
import test_rings_wide as wide_tests


HUD_SCENE=ZOOM_SCENE+r'''
static void hud_word(VDP *v,unsigned at,unsigned value) {
 v->vram[at]=(uint8_t)(value>>8);v->vram[at+1]=(uint8_t)value;
}
static void hud_line(VDP *v,unsigned x,unsigned y,const char *text,unsigned run) {
 (void)run;
 for(unsigned i=0;text[i];++i) {
  unsigned ch=(unsigned char)text[i],entry=0x8100+ch-32,at=0x1000+((y/8)*64+x/8+i)*2;
  hud_word(v,at,entry);memset(v->vram+(entry&0x7ff)*32,ch==' ' ? 0:0x11,32);
#ifdef GENESIS_RINGS_MENU_FONT
  RingsTextMark *m=&v->font_marks[at/2];m->ch=(uint8_t)ch;m->entry=(uint16_t)entry;
  m->run=run;m->pattern=rings_text_pattern(v,entry&0x7ff);
#endif
 }
}
static void hud_scene(CPU *c,RingsWide *w) {
 zoom_scene(c,w);VDP *v=&c->vdp;v->wide_enabled=1;v->registers[5]=0x60;
 v->cram[20]=0x0e00;v->cram[50]=0x00e0;v->cram[17]=0x0eee;
 for(unsigned i=0;i<4;++i) {
  unsigned at=0xc000+i*8,x=246+(i%2)*32,y=152+(i/2)*32;
  unsigned pattern=0x26ca+(i%2)*48+(i/2)*0x1000;
  hud_word(v,at,128+y);hud_word(v,at+2,0x0f00+(i==3 ? 0:i+1));
  hud_word(v,at+4,pattern);hud_word(v,at+6,128+x);
 }
 for(unsigned bank=0;bank<2;++bank)for(unsigned i=0;i<16;++i)
  memset(v->vram+(0x6ca+bank*48+i)*32,0x44,32);
 for(unsigned y=0;y<6;++y)for(unsigned x=0;x<6;++x) {
  unsigned tile=0x36a+y*6+x;memset(v->vram+tile*32,0x22,32);
  hud_word(v,0x1000+((20+y)*64+32+x)*2,0xe000|tile);
 }
 memset(v->vram+0x300*32,0x11,32);hud_word(v,0xa000+(21*64+26)*2,0x2300);
 hud_line(v,48,160,"Gold",1);hud_line(v,56,168,"$1000",2);
 hud_line(v,80,176,"Time",3);hud_line(v,88,184,"5 AM",4);
 hud_line(v,112,192,"F/W",5);
}
'''


class RingsHudTests(CompiledTestCase):
    def check(self,body):
        source='#define GENESIS_NO_MAIN\n#define GENESIS_RINGS_WIDE\n#define GENESIS_RINGS_SAVES\n'+emit(analyze(rom_with('4e72 2700'),[0x200]))
        source+='\n#include <assert.h>\n'+HUD_SCENE+r'''
int main(void) {
 CPU *c=calloc(1,sizeof *c);assert(c);RingsWide w={0};hud_scene(c,&w);VDP *v=&c->vdp;
'''+body+'\nfree(c);return 0;}\n'
        result=subprocess.run([str(self.compile(source))],capture_output=True,text=True,timeout=15)
        self.assertEqual(result.returncode,0,result.stderr)

    def test_column_portrait_and_compass_move_while_native_state_stays_intact(self):
        self.check(r'''
vdp_render(c);assert(rings_hud_layout(v));uint8_t before[65536];memcpy(before,v->vram,sizeof before);
vdp_render(c);assert(v->wide_hud_active && v->zoom_world_visible);
unsigned old=(160*400+48+40)*3,now=(96*400+20)*3;
assert(v->wide_frame[old+1]==255 && !v->wide_frame[old]); /* Old gold reveals world. */
assert(v->wide_frame[now]==255 && !v->wide_frame[now+1]); /* Live gold is relocated. */
assert(v->wide_frame[(160*400+342)*3+1]==255); /* Face: 256 -> 342. */
assert(v->wide_frame[(171*400+57)*3]==255 && v->wide_frame[(171*400+57)*3+2]==255); /* N. */
assert(!v->zoom_mask[96*400+20] && v->zoom_mask[160*400+88]);
assert(!v->zoom_mask[160*400+342] && v->zoom_mask[160*400+296]);
assert(!memcmp(before,v->vram,sizeof before));
uint8_t native[320*240*3];memcpy(native,v->frame,sizeof native);
v->wide_enabled=0;vdp_render(c);assert(!v->wide_hud_active && !memcmp(native,v->frame,sizeof native));
assert(!c->steps && !c->cycles && !c->master_cycles && !c->pad_buttons[0]);
''')

    def test_dialogues_missing_frame_and_fallback_keep_the_original_layout(self):
        self.check(r'''
vdp_render(c);assert(v->wide_hud_active);
hud_word(v,0x1000+(20*64+6)*2,0);vdp_render(c);assert(!v->wide_hud_active);
hud_line(v,48,160,"Gold",1);hud_word(v,0xc002,0x0f00);vdp_render(c);assert(!v->wide_hud_active);
hud_word(v,0xc002,0x0f01);vdp_render(c);assert(v->wide_hud_active);
v->registers[17]=0;vdp_render(c);assert(!v->wide_hud_active && !v->wide_world_visible);
for(unsigned y=0;y<224;++y)assert(!memcmp(v->wide_frame+(y*400+40)*3,v->frame+y*320*3,320*3));
''')

    def test_current_values_follow_live_tiles_without_cached_strings(self):
        self.check(r'''
vdp_render(c);uint8_t before[400*240*3];memcpy(before,v->wide_frame,sizeof before);
/* Repaint only the amount's glyph tile; relocation uses its new live pixels. */
unsigned tile=vdp_word(v,0x1000+(21*64+7)*2)&0x7ff;
memset(v->vram+tile*32,0x22,32);vdp_render(c);
assert(v->wide_hud_active && memcmp(before+(104*400+28)*3,v->wide_frame+(104*400+28)*3,3));
assert(v->wide_frame[(104*400+28)*3+1]==255);
''')

    def test_save_metadata_is_optional_validated_and_round_trips_frozen_layout(self):
        self.check(r'''
vdp_render(c);assert(v->wide_hud_active);SaveCodec s={0};assert(save_encode(c,&s));
v->wide_hud_active=0;assert(save_decode(c,s.data,s.pos));assert(c->vdp.wide_hud_active);
size_t at=0;while(at+8<s.pos && save_get(s.data+at,4)!=6)at+=8+(size_t)save_get(s.data+at+4,4);
assert(at+9<s.pos && save_get(s.data+at+4,4)==1);
s.data[at+8]=2;c->d[0]=123;assert(!save_decode(c,s.data,s.pos));assert(c->d[0]==123 && c->vdp.wide_hud_active);
s.data[at+8]=1;memmove(s.data+at,s.data+at+9,s.pos-at-9);s.pos-=9;
assert(save_decode(c,s.data,s.pos));assert(!c->vdp.wide_hud_active);
vdp_render(c);assert(c->vdp.wide_hud_active);free(s.data);
''')


class RingsHudSDLTests(CompiledTestCase):
    @classmethod
    def setUpClass(cls):
        wide_tests.RingsWideSDLTests.setUpClass.__func__(cls)

    def test_bitmap_and_external_text_remain_on_paper_at_all_zooms_and_after_resize(self):
        source='#define GENESIS_NO_MAIN\n'+emit(analyze(rom_with('4e72 2700'),[0x200]))
        source+='\n#include <assert.h>\n'+HUD_SCENE+r'''
static void hud_read(SDLHost *h,uint8_t *out) {
 assert(!SDL_RenderReadPixels(h->renderer,NULL,SDL_PIXELFORMAT_RGB24,out,1200*3));
}
int main(int argc,char **argv) {
 assert(argc==2);CPU *c=calloc(1,sizeof *c);assert(c);RingsWide w={0};hud_scene(c,&w);
 SDLHost h={0};h.no_throttle=1;h.wide_window=1;assert(sdl_host_open(&h));
 uint8_t *before=malloc(1200*672*3),*after=malloc(1200*672*3);assert(before && after);
 for(unsigned font=0;font<2;++font) {
  if(font) {assert(rings_font_open(&h.font,argv[1]));c->vdp.font_enabled=1;memset(c->vdp.font_supported,1,128);}
  vdp_render(c);assert(c->vdp.wide_hud_active);h.zoom_percent=100;assert(sdl_host_draw(&h,&c->vdp));hud_read(&h,before);
  for(unsigned percent=50;percent<=100;percent+=10) {
   h.zoom_percent=percent;assert(sdl_host_draw(&h,&c->vdp));hud_read(&h,after);
   for(unsigned y=252;y<648;++y)assert(!memcmp(before+(y*1200+12)*3,after+(y*1200+12)*3,80*3*3));
   for(unsigned y=456;y<648;++y)assert(!memcmp(before+(y*1200+996)*3,after+(y*1200+996)*3,64*3*3));
  }
  unsigned red=0;
  for(unsigned y=288;y<312;++y)for(unsigned x=60;x<156;++x)red+=before[(y*1200+x)*3]==255;
  assert(red>20); /* Letters live in the new left column, including TTF mode. */
  if(font) {
   assert(c->vdp.font_count>0);int x,y;
   assert(rings_hud_text_position(&c->vdp,48,160,&x,&y) && x==20 && y==96);
   unsigned old=(160*400+88)*3;assert(c->vdp.wide_font_frame[old+1]==255);

   /* A leftward relocation must clip exactly like drawing the same text at
      its destination directly, including a fractional desktop scale. */
   hud_line(&c->vdp,56,168,"j1000",6);vdp_render(c);
   SDL_SetWindowSize(h.window,1280,720);assert(sdl_host_draw(&h,&c->vdp));
   uint8_t *actual=malloc(1280*720*3),*direct=malloc(1280*720*3);assert(actual && direct);
   assert(!SDL_RenderReadPixels(h.renderer,NULL,SDL_PIXELFORMAT_RGB24,actual,1280*3));
   RingsTextVisible saved[1200];memcpy(saved,c->vdp.font_cells,sizeof saved);
   for(unsigned i=0;i<c->vdp.font_count;++i) {
    RingsTextVisible *m=&c->vdp.font_cells[i];int dx,dy;
    if(rings_hud_text_position(&c->vdp,m->x,m->y,&dx,&dy)) {m->x=(uint16_t)dx;m->y=(uint16_t)dy;}
   }
   c->vdp.wide_hud_active=0;SDL_SetRenderDrawColor(h.renderer,0,0,255,255);assert(!SDL_RenderClear(h.renderer));
   SDL_Rect full={0,1,1280,717};assert(rings_font_draw(&h.font,h.renderer,&c->vdp,&full,3.2));
   assert(!SDL_RenderReadPixels(h.renderer,NULL,SDL_PIXELFORMAT_RGB24,direct,1280*3));
   for(unsigned y=308;y<333;++y)assert(!memcmp(actual+(y*1280+62)*3,direct+(y*1280+62)*3,107*3));
   for(unsigned y=334;y<360;++y)assert(!memcmp(actual+(y*1280+88)*3,direct+(y*1280+88)*3,165*3));
   memcpy(c->vdp.font_cells,saved,sizeof saved);c->vdp.wide_hud_active=1;
   SDL_SetRenderDrawColor(h.renderer,0,0,0,255);free(actual);free(direct);
   int size=h.font.pixels;SDL_SetWindowSize(h.window,1600,896);assert(sdl_host_draw(&h,&c->vdp));assert(h.font.pixels>size);
  }
 }
 assert(!c->steps && !c->master_cycles && !SDL_RenderIsClipEnabled(h.renderer));
 free(before);free(after);sdl_host_close(&h);free(c);return 0;
}
'''
        path=self.root/'hud.c';path.write_text(source);binary=self.root/'hud'
        result=subprocess.run(['cc','-std=c11','-O2','-Wall','-Wextra','-Werror','-Wno-unused-function',
            '-DGENESIS_SDL2','-DGENESIS_RINGS_WIDE','-DGENESIS_RINGS_MENU_FONT',*self.flags,str(path),'-o',str(binary),*self.libs],capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stderr)
        result=subprocess.run([str(binary),self.font],env=dict(os.environ,SDL_VIDEODRIVER='dummy',SDL_RENDER_DRIVER='software'),capture_output=True,text=True,timeout=20)
        self.assertEqual(result.returncode,0,result.stderr)
