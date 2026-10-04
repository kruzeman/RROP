import os
from pathlib import Path
import subprocess
import unittest

from genesis_recompiler.build import BuildError, sdl2_flags, sdl2_ttf_flags
from genesis_recompiler.cli import main
from genesis_recompiler.decode import analyze
from genesis_recompiler.emit import emit
from support import CompiledTestCase, rom_with


LIVE_TEXT = r'''
static void word(VDP *v,unsigned at,unsigned value) {
 v->vram[at]=(uint8_t)(value>>8);v->vram[at+1]=(uint8_t)value;
}
static unsigned cell(unsigned row,unsigned column) {
 return 0x2000+((13+row)*64+17+column)*2;
}
static void character(CPU *c,unsigned at,unsigned ch,unsigned caller) {
 c->pc=0xd9f2;c->a[7]=0xfffe00;c->a[6]=0xfffd00;c->a[0]=0xfffc00;c->d[4]=0;
 write_mem(c,c->a[7],4,caller);write_mem(c,c->a[6]+22,2,0x8000);
 write_mem(c,0xff8640,2,0x294);write_mem(c,c->a[0],1,ch);
 unsigned delta=ch-32;
 if(caller!=0x11192) {
  delta=ch-64;
  if(ch==32)delta=0;else if(ch=='.')delta=0x1b;
  else if(ch==',')delta=0x1c;else if(ch=='-')delta=0x1d;
 }
 unsigned entry=(uint16_t)(0x8294+delta);
 if(ch!=32)memset(c->vdp.vram+(entry&0x7ff)*32,0x11,32);
 c->vdp.address=(uint16_t)at;c->vdp.code=1;vdp_store_word(c,(uint16_t)entry);
}
static void text_line(CPU *c,unsigned row,unsigned column,const char *text) {
 c->pc=0xd9f2;c->a[7]=0xfffe00;c->a[6]=0xfffd00;c->a[0]=0xfffa00;
 write_mem(c,c->a[7],4,0x11192);write_mem(c,c->a[6]+22,2,0x8000);
 write_mem(c,0xff8640,2,0x294);
 for(unsigned i=0;text[i];++i) {
  unsigned ch=(unsigned char)text[i],entry=0x8294+ch-32;
  write_mem(c,c->a[0]+i,1,ch);c->d[4]=i;
  memset(c->vdp.vram+(entry&0x7ff)*32,ch==' ' ? 0:0x11,32);
  c->vdp.address=(uint16_t)cell(row,column+i);c->vdp.code=1;
  vdp_store_word(c,(uint16_t)entry);
 }
}
static void live_text(CPU *c) {
 c->rom=rom_data;c->rom_size=sizeof rom_data;
 VDP *v=&c->vdp;
 v->registers[1]=0x44;v->registers[2]=8;v->registers[4]=5;
 v->registers[12]=1;v->registers[13]=0x38;v->registers[16]=1;v->registers[15]=2;
 v->font_enabled=1;memset(v->font_supported,1,sizeof v->font_supported);
 v->cram[1]=0x000e;v->cram[2]=0x00e0;
 memset(v->vram+32,0x22,32);
 const char *text="Coins:42";
 text_line(c,0,0,text);
 for(unsigned col=0;text[col];++col) {
  word(v,0xa000+(13*64+17+col)*2,1);
 }
}
'''


class RingsTextTests(CompiledTestCase):
    def check(self, body):
        p = analyze(rom_with('4e72 2700'), [0x200])
        source = '#define GENESIS_NO_MAIN\n#define GENESIS_RINGS_MENU_FONT\n' + emit(p)
        source += '\n#include <assert.h>\n' + LIVE_TEXT + '\nint main(void) { CPU c={0}; live_text(&c); VDP *v=&c.vdp;\n' + body + '\nreturn 0; }'
        binary = self.compile(source)
        result = subprocess.run([str(binary)], capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_background_is_recomposited_and_console_state_preserved(self):
        self.check(r'''
uint8_t before[65536];memcpy(before,v->vram,sizeof before);
vdp_render(&c);assert(v->font_count && !v->font_hide);
unsigned at=(104*320+136)*3;
assert(v->frame[at]==255 && !v->frame[at+1]);
assert(!v->font_frame[at] && v->font_frame[at+1]==255);
assert(!memcmp(before,v->vram,sizeof before));
assert(!memcmp(v->frame,v->font_frame,104*320*3));
assert(v->rendered_frames==1 && c.steps==0 && c.cycles==0);
assert(v->font_cells[0].rgb[0]==255 && !v->font_cells[0].rgb[1]);
assert(v->font_count==8 && v->font_cells[7].ch=='2');
v->font_enabled=0;vdp_render(&c);assert(!v->font_count);
assert(v->frame[at]==255 && v->rendered_frames==2);
''')

    def test_writes_clear_cells_even_when_the_word_is_identical(self):
        self.check(r'''
vdp_render(&c);assert(v->font_count==8);
unsigned entry=vdp_word(v,cell(0,0));
c.pc=0x200;v->address=cell(0,0);vdp_store_word(&c,(uint16_t)entry);
vdp_render(&c);assert(v->font_count==7 && !v->font_marks[cell(0,0)/2].ch);
character(&c,cell(0,0),'C',0x11192);vdp_render(&c);assert(v->font_count==8);
c.pc=0x200;v->address=(0x294+'C'-32)*32;vdp_store_word(&c,0x3333);
vdp_render(&c);assert(v->font_count==7);
''')

    def test_scroll_window_and_sprites_require_verified_visible_mapping(self):
        self.check(r'''
vdp_render(&c);assert(v->font_count==8);
word(v,0xe000,8);vdp_render(&c);assert(v->font_count==8 && v->font_cells[0].x==144);
word(v,0xe000,0);v->registers[18]=14;v->registers[3]=0x0c;
vdp_render(&c);assert(!v->font_count);
v->registers[18]=0;v->registers[5]=0x60;
word(v,0xc000,128+104);word(v,0xc004,1);word(v,0xc006,128+136);
vdp_render(&c);assert(v->font_count);
word(v,0xc004,0x8001);
vdp_render(&c);assert(v->font_count==7);
''')

    def test_cli_rejects_unverified_rom_and_headless_build(self):
        rom = self.root / 'demo.bin';rom.write_bytes(rom_with('4e72 2700'))
        output = self.root / 'demo'
        self.assertEqual(main([str(rom),'--build','--frontend','sdl2','--text-renderer','rings-menu','-o',str(output)]),1)
        self.assertFalse(output.exists())
        with self.assertRaises(SystemExit) as error:
            main([str(rom),'--build','--text-renderer','rings-menu','-o',str(output)])
        self.assertEqual(error.exception.code,2)

    def test_ram_and_rom_characters_are_observed_without_phrase_matching(self):
        self.check(r'''
character(&c,cell(0,0),'7',0x11192);
c.a[0]=0xfffb00;c.d[4]=3;write_mem(&c,c.a[0]+3,1,'7');
v->address=cell(1,4);vdp_store_word(&c,0x8294+'7'-32);
assert(v->font_marks[cell(1,4)/2].ch=='7');
/* The synthetic ROM's STOP immediate contains ASCII 'r' at $201. */
c.a[0]=0x201;c.d[4]=0;
memset(v->vram+(0x294+'r'-32)*32,0x11,32);
v->address=cell(2,6);vdp_store_word(&c,0x8294+'r'-32);
assert(v->font_marks[cell(2,6)/2].ch=='r' && !c.fault);
vdp_render(&c);assert(v->font_count==10);
assert(v->font_cells[0].ch=='7');
''')

    def test_second_writer_handles_digits_lowercase_and_punctuation(self):
        self.check(r'''
const unsigned chars[]={'.',',','-',' ','0','a','!'};
const unsigned callers[]={0x11238,0x11252,0x1126c,0x1121c,0x11290,0x11290,0x11290};
for(unsigned i=0;i<7;++i) {
 character(&c,cell(1,i),chars[i],callers[i]);
 assert(v->font_marks[cell(1,i)/2].ch==chars[i]);
}
assert(v->font_captured[0]==8 && v->font_captured[1]==7);
vdp_render(&c);assert(v->font_count==15 && v->font_visible==14);
''')

    def test_unknown_callers_unmapped_sources_and_mismatches_are_not_guessed(self):
        self.check(r'''
character(&c,cell(0,0),'C',0x123456);
assert(!v->font_marks[cell(0,0)/2].ch);
character(&c,cell(0,0),'C',0x11192);
c.a[0]=0xc00000;v->address=cell(0,0);vdp_store_word(&c,0x82b7);
assert(!c.fault && !v->font_marks[cell(0,0)/2].ch && v->data_reads==0);
character(&c,cell(0,0),'C',0x11192);
v->address=cell(0,0);vdp_store_word(&c,0x82b8);
assert(!v->font_marks[cell(0,0)/2].ch);
''')

    def test_cpu_dma_vram_copy_and_fill_invalidate_old_characters(self):
        self.check(r'''
unsigned original=vdp_word(v,cell(0,0));
write_mem(&c,0xff0100,2,original);c.pc=0x200;
v->address=cell(0,0);v->registers[19]=1;v->registers[20]=0;
v->registers[21]=0x80;v->registers[22]=0x80;v->registers[23]=0x7f;
vdp_start_dma(&c);assert(!c.fault && !v->font_marks[cell(0,0)/2].ch);
assert(vdp_word(v,cell(0,0))==original);
character(&c,cell(0,0),'C',0x11192);c.pc=0x200;
v->address=cell(0,1);v->registers[15]=1;v->registers[19]=2;
v->registers[21]=(uint8_t)cell(0,0);v->registers[22]=cell(0,0)>>8;v->registers[23]=0xc0;
vdp_start_dma(&c);assert(!v->font_marks[cell(0,1)/2].ch);
assert(v->font_marks[cell(0,0)/2].ch=='C');
assert(vdp_word(v,cell(0,1))==original);
v->address=cell(0,0);v->registers[15]=1;v->registers[19]=16;
v->fill_pending=1;vdp_data_write(&c,0);
for(unsigned i=0;i<8;++i)assert(!v->font_marks[cell(0,i)/2].ch);
assert(!c.fault);
''')

    def test_missing_glyphs_and_multicolor_patterns_keep_bitmap_pixels(self):
        self.check(r'''
v->font_supported['C']=0;vdp_render(&c);assert(v->font_count==7);
unsigned at=(104*320+136)*3;
assert(v->font_frame[at]==255 && !v->font_frame[at+1]);
v->font_supported['C']=1;character(&c,cell(0,0),'C',0x11192);
v->vram[(0x294+'C'-32)*32]=0x12;
/* Even when freshly captured, a multicolor glyph uses the console renderer. */
v->address=cell(0,0);vdp_store_word(&c,0x82b7);
vdp_render(&c);assert(v->font_count==7);
''')

    def test_frame_metadata_is_frozen_until_next_snapshot(self):
        self.check(r'''
vdp_render(&c);assert(v->font_count==8 && v->font_cells[0].ch=='C');
character(&c,cell(0,0),'8',0x11192);
assert(v->font_cells[0].ch=='C' && v->rendered_frames==1);
v->cram[1]=0x0e00;vdp_render(&c);
assert(v->font_cells[0].ch=='8' && v->font_cells[0].rgb[2]==255 && !v->font_cells[0].rgb[0]);
''')

    def test_plane_b_and_priority_are_respected(self):
        self.check(r'''
v->registers[2]=0x30;
unsigned at=0xa000+(13*64+17)*2;
character(&c,at,'B',0x11192);
vdp_render(&c);assert(v->font_count==1 && v->font_cells[0].ch=='B');
assert(v->font_mask[104*320+136]==2);
word(v,0xc000+(13*64+17)*2,1);
vdp_render(&c);assert(v->font_count==1);
word(v,0xc000+(13*64+17)*2,0x8001);
vdp_render(&c);assert(!v->font_count);
''')


    def test_run_provenance_retains_spaces_and_distinguishes_adjacent_strings(self):
        self.check(r'''
text_line(&c,1,0,"A B");
uint32_t first=v->font_marks[cell(1,0)/2].run;
assert(first && v->font_marks[cell(1,1)/2].ch==' ');
assert(v->font_marks[cell(1,1)/2].run==first && v->font_marks[cell(1,2)/2].run==first);
text_line(&c,1,3,"CD");
uint32_t second=v->font_marks[cell(1,3)/2].run;
assert(second!=first && v->font_marks[cell(1,4)/2].run==second);
vdp_render(&c);assert(v->font_count==13 && v->font_visible==12);
assert(v->font_cells[9].ch==' ' && v->font_cells[9].run==first);
assert(v->font_cells[11].run==second && v->font_cells[11].x==160);
/* An unrelated write removes the space's permission to join its neighbors. */
c.pc=0x200;v->address=cell(1,1);vdp_store_word(&c,vdp_word(v,cell(1,1)));
vdp_render(&c);assert(v->font_count==12 && v->font_visible==12);
''')

    def test_source_gaps_frames_and_layout_changes_start_new_runs(self):
        self.check(r'''
text_line(&c,1,0,"ABC");
uint32_t initial=v->font_run;
/* Skip a source byte, retaining a valid character/tile write. */
c.d[4]=4;write_mem(&c,c.a[0]+4,1,'C');v->address=cell(1,3);vdp_store_word(&c,0x82b7);
assert(v->font_run!=initial);initial=v->font_run;
c.d[4]=5;c.a[6]-=32;write_mem(&c,c.a[6]+22,2,0x8000);
write_mem(&c,c.a[0]+5,1,'C');v->address=cell(1,4);vdp_store_word(&c,0x82b7);
assert(v->font_run!=initial);initial=v->font_run;
c.d[4]=6;write_mem(&c,c.a[6]+22,2,0xa000);write_mem(&c,c.a[0]+6,1,'C');
v->address=cell(1,5);vdp_store_word(&c,0xa2b7);
assert(v->font_run!=initial);
/* A changed source/layout cannot retroactively change a frozen frame. */
vdp_render(&c);uint32_t frozen=v->font_cells[8].run;
text_line(&c,1,0,"XYZ");assert(v->font_cells[8].run==frozen);
vdp_render(&c);assert(v->font_cells[8].run!=frozen && v->font_cells[8].ch=='X');
''')


class RingsFontSDLTests(CompiledTestCase):
    @classmethod
    def setUpClass(cls):
        try:
            cls.cflags,cls.libs=sdl2_flags()
            cflags,libs=sdl2_ttf_flags();cls.cflags+=cflags;cls.libs+=libs
        except BuildError as exc:
            raise unittest.SkipTest(str(exc))
        candidates = [os.environ.get('GENESIS_TEST_FONT',''),
                      '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',
                      '/usr/share/fonts/truetype/open-sans/OpenSans-Regular.ttf']
        cls.font=next((Path(p) for p in candidates if p and Path(p).is_file()),None)
        if cls.font is None:raise unittest.SkipTest('install fonts-dejavu-core or set GENESIS_TEST_FONT')

    def check(self,body):
        p=analyze(rom_with('4e72 2700'),[0x200])
        source='#define GENESIS_NO_MAIN\n'+emit(p)+'\n#include <assert.h>\n'+LIVE_TEXT
        source+='\nint main(int argc,char **argv) { assert(argc==2); CPU c={0};live_text(&c);SDLHost h={0};assert(sdl_host_open(&h));assert(rings_font_open(&h.font,argv[1]));\n'+body+'\nsdl_host_close(&h);return 0;}'
        path=self.root/'font.c';path.write_text(source);binary=self.root/'font'
        result=subprocess.run(['cc','-std=c11','-O2','-Wall','-Wextra','-Werror','-Wno-unused-function','-DGENESIS_SDL2','-DGENESIS_RINGS_MENU_FONT',*self.cflags,str(path),'-o',str(binary),*self.libs],capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stderr)
        result=subprocess.run([str(binary),str(self.font)],env=dict(os.environ,SDL_VIDEODRIVER='dummy',SDL_RENDER_DRIVER='software'),capture_output=True,text=True,timeout=10)
        self.assertEqual(result.returncode,0,result.stderr)

    def test_antialiasing_at_drawable_resolution_and_resize(self):
        self.check(r'''
vdp_render(&c);assert(sdl_host_draw(&h,&c.vdp));assert(h.font.glyphs['C'].texture);
assert(!SDL_RenderIsClipEnabled(h.renderer));
int original=h.font.pixels;assert(original>8);
uint8_t *pixels=malloc(960*672*3);assert(pixels);
assert(!SDL_RenderReadPixels(h.renderer,NULL,SDL_PIXELFORMAT_RGB24,pixels,960*3));
unsigned blended=0;
for(unsigned y=312;y<336;++y)for(unsigned x=408;x<432;++x) {
 unsigned at=(y*960+x)*3;
 if(pixels[at]>0 && pixels[at]<255 && pixels[at+1]>0 && pixels[at+1]<255)++blended;
}
assert(blended>10);free(pixels);
SDL_SetWindowSize(h.window,1280,896);assert(sdl_host_draw(&h,&c.vdp));
assert(h.font.pixels>original);
int stable=h.font.pixels;assert(sdl_host_draw(&h,&c.vdp));assert(h.font.pixels==stable);
int w,hg;SDL_RenderGetLogicalSize(h.renderer,&w,&hg);assert(!w && !hg);
word(&c.vdp,cell(0,0),0);
''')

    def test_menu_exit_removes_overlay_and_font_failure_is_clean(self):
        self.check(r'''
vdp_render(&c);assert(sdl_host_draw(&h,&c.vdp));
for(unsigned col=0;col<8;++col)word(&c.vdp,cell(0,col),0);
vdp_render(&c);assert(!c.vdp.font_count);
assert(sdl_host_draw(&h,&c.vdp));
SDL_Rect pixel={415,315,1,1};uint8_t rgb[3];
assert(!SDL_RenderReadPixels(h.renderer,&pixel,SDL_PIXELFORMAT_RGB24,rgb,3));
assert(!rgb[0] && rgb[1]==255 && !rgb[2]);
RingsFont bad={0};assert(!rings_font_open(&bad,"/missing/font.ttf"));rings_font_close(&bad);
''')

    def test_descenders_fit_the_original_cell(self):
        self.check(r'''
character(&c,cell(0,0),'g',0x11192);
vdp_render(&c);assert(sdl_host_draw(&h,&c.vdp));
RingsGlyph *g=&h.font.glyphs['g'];assert(g->texture && g->min_y<0);
int top=24+h.font.descent-g->max_y;
assert(top>=0 && top+g->ink.h<=24);
''')

    def test_new_characters_appear_after_a_fresh_frame(self):
        self.check(r'''
vdp_render(&c);assert(sdl_host_draw(&h,&c.vdp));
assert(h.font.glyphs['C'].texture && !h.font.glyphs['7'].texture);
character(&c,cell(0,0),'7',0x11192);
/* Expose/resize before a new console frame must retain the old text snapshot. */
assert(sdl_host_draw(&h,&c.vdp));assert(!h.font.glyphs['7'].texture);
vdp_render(&c);assert(sdl_host_draw(&h,&c.vdp));
assert(h.font.glyphs['7'].texture && c.vdp.font_cells[0].ch=='7');
''')

    def test_proportional_spacing_uses_advances_spaces_and_kerning(self):
        self.check(r'''
text_line(&c,1,0,"Wi iAV");vdp_render(&c);assert(sdl_host_draw(&h,&c.vdp));
unsigned first=8,end=rings_font_run_end(&c.vdp,first);assert(end==14);
RingsLineLayout layout;assert(rings_font_layout(&h.font,h.renderer,&c.vdp,first,end,144,&layout));
assert(h.font.glyphs['W'].advance>h.font.glyphs['i'].advance);
assert(layout.x[1]-layout.x[0]>layout.x[2]-layout.x[1]);
assert(h.font.glyphs[' '].ready && !h.font.glyphs[' '].texture);
assert(layout.x[3]>layout.x[2] && layout.fit==1 && layout.width<144);
int kern=TTF_GetFontKerningSizeGlyphs(h.font.font,'A','V');
assert(layout.x[5]-layout.x[4]==h.font.glyphs['A'].advance+kern);
/* The complete text, not isolated cells, fits inside its original row span. */
uint8_t *pixels=malloc(960*672*3);assert(pixels);
assert(!SDL_RenderReadPixels(h.renderer,NULL,SDL_PIXELFORMAT_RGB24,pixels,960*3));
unsigned last=0,ink=0;
for(unsigned y=336;y<360;++y)for(unsigned x=408;x<552;++x) {
 unsigned at=(y*960+x)*3;
 if(pixels[at]) {last=x;++ink;}
}
assert(ink>50 && last<540);free(pixels);
''')

    def test_adjacent_strings_rows_layers_and_fallbacks_split_layout(self):
        self.check(r'''
text_line(&c,1,0,"Wi");text_line(&c,1,2,"ii");
text_line(&c,2,0,"ABC");vdp_render(&c);
assert(rings_font_run_end(&c.vdp,8)==10 && rings_font_run_end(&c.vdp,10)==12);
assert(rings_font_run_end(&c.vdp,12)==15);
assert(sdl_host_draw(&h,&c.vdp));
/* Even a matching run cannot cross a visible-layer boundary. */
c.vdp.font_cells[9].layer=2;assert(rings_font_run_end(&c.vdp,8)==9);
text_line(&c,1,0,"A B");c.pc=0x200;c.vdp.address=cell(1,1);
vdp_store_word(&c,vdp_word(&c.vdp,cell(1,1)));vdp_render(&c);
assert(c.vdp.font_cells[8].ch=='A' && c.vdp.font_cells[9].ch=='B');
assert(rings_font_run_end(&c.vdp,8)==9);
assert(sdl_host_draw(&h,&c.vdp));
''')

    def test_overwide_lines_fit_as_a_whole_and_preserve_descenders(self):
        self.check(r'''
text_line(&c,1,0,"WgjW");vdp_render(&c);assert(sdl_host_draw(&h,&c.vdp));
RingsLineLayout layout;assert(rings_font_layout(&h.font,h.renderer,&c.vdp,8,12,30,&layout));
assert(layout.width>30 && layout.fit<1);
for(unsigned i=0;i<4;++i) {
 RingsGlyph *g=&h.font.glyphs[c.vdp.font_cells[8+i].ch];
 double left=layout.origin+(layout.x[i]+g->min_x)*layout.fit;
 assert(left>=-0.0001 && left+g->ink.w*layout.fit<=30.0001);
 int top=24+h.font.descent-g->max_y;
 assert(top>=0 && top+g->ink.h<=24);
}
assert(!SDL_RenderIsClipEnabled(h.renderer));
SDL_SetWindowSize(h.window,1280,720);assert(sdl_host_draw(&h,&c.vdp));
assert(rings_font_run_end(&c.vdp,8)==12);
''')
