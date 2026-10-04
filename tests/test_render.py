import subprocess
from genesis_recompiler.decode import analyze
from genesis_recompiler.emit import emit
from support import CompiledTestCase, rom_with


class RenderTests(CompiledTestCase):
    def check(self, body):
        p=analyze(rom_with('4e72 2700'),[0x200])
        source='#define GENESIS_NO_MAIN\n'+emit(p)+'''
#include <assert.h>
static void word(VDP *v,unsigned a,unsigned n) { v->vram[a]=(uint8_t)(n>>8); v->vram[a+1]=(uint8_t)n; }
static void tile(VDP *v,unsigned n,unsigned color) { memset(v->vram+n*32,(color<<4)|color,32); }
static void pixel(VDP *v,unsigned x,unsigned y,unsigned r,unsigned g,unsigned b) {
 size_t i=((size_t)y*v->frame_width+x)*3;
 assert(v->frame[i]==r && v->frame[i+1]==g && v->frame[i+2]==b);
}
int main(void) {
 CPU c={0}; c.rom=rom_data; c.rom_size=sizeof rom_data; VDP *v=&c.vdp;
 v->registers[1]=0x44; v->registers[2]=0x30; v->registers[4]=5;
 v->registers[3]=0x2c; v->registers[5]=0x6c; v->registers[13]=0x38;
 v->cram[1]=0x000e; v->cram[2]=0x00e0; v->cram[3]=0x0e00;
'''+body+'\nreturn 0; }\n'
        exe=self.compile(source)
        result=subprocess.run([str(exe)],capture_output=True,text=True,timeout=10)
        self.assertEqual(result.returncode,0,result.stderr)

    def test_planes_transparency_palette_and_priority(self):
        self.check('''
 tile(v,1,1); tile(v,2,2); word(v,0xc000,1); word(v,0xa000,2);
 vdp_render(&c); pixel(v,0,0,255,0,0); pixel(v,8,0,0,0,0);
 word(v,0xa000,0x8002); vdp_render(&c); pixel(v,0,0,0,255,0);
 word(v,0xc000,0x8001); vdp_render(&c); pixel(v,0,0,255,0,0);
 tile(v,1,0); vdp_render(&c); pixel(v,0,0,0,255,0);
 v->cram[17]=0x0eee; tile(v,1,1); word(v,0xc000,0xa001);
 vdp_render(&c); pixel(v,0,0,255,255,255);
''')

    def test_flips_and_pattern_nibbles(self):
        self.check('''
 v->vram[32]=0x12; v->vram[32+31]=0x30;
 word(v,0xc000,1); vdp_render(&c);
 pixel(v,0,0,255,0,0); pixel(v,1,0,0,255,0);
 word(v,0xc000,0x1801); vdp_render(&c);
 pixel(v,0,0,0,0,0); pixel(v,1,0,0,0,255);
''')

    def test_horizontal_vertical_scroll_and_plane_size(self):
        self.check('''
 tile(v,1,1); tile(v,2,2); word(v,0xc000,1); word(v,0xc002,2);
 word(v,0xe000,8); vdp_render(&c); pixel(v,8,0,255,0,0); pixel(v,16,0,0,255,0);
 word(v,0xe000,0); v->vsram[0]=8; word(v,0xc040,2);
 vdp_render(&c); pixel(v,0,0,0,255,0);
 v->vsram[0]=0; v->registers[16]=3; word(v,0xc000+127*2,1); word(v,0xe000,8);
 vdp_render(&c); pixel(v,0,0,255,0,0);
''')

    def test_line_and_column_scroll(self):
        self.check('''
 tile(v,1,1); tile(v,2,2); word(v,0xc000,1); word(v,0xc040,2);
 v->registers[11]=3; word(v,0xe004,8);
 vdp_render(&c); pixel(v,0,0,255,0,0); pixel(v,8,1,255,0,0); pixel(v,0,1,0,0,0);
 v->registers[11]=4; v->vsram[2]=8; word(v,0xc044,2);
 vdp_render(&c); pixel(v,16,0,0,255,0);
''')

    def test_window_replaces_plane_a_and_h40_stride(self):
        self.check('''
 tile(v,1,1); tile(v,2,2); word(v,0xc000,1); word(v,0xb000,2);
 v->registers[17]=1; vdp_render(&c); pixel(v,0,0,0,255,0);
 v->registers[17]=0; v->registers[18]=1; vdp_render(&c); pixel(v,0,0,0,255,0);
 v->registers[12]=0x81; word(v,0xb080,1); v->registers[18]=2;
 vdp_render(&c); assert(v->frame_width==320); pixel(v,0,8,255,0,0);
''')

    def test_sprites_priority_chain_and_column_tile_order(self):
        self.check('''
 tile(v,1,1); tile(v,2,2); tile(v,3,3);
 word(v,0xc000,0x8001);
 word(v,0xd800,128); word(v,0xd802,0x0401); word(v,0xd804,2); word(v,0xd806,128);
 word(v,0xd808,128); word(v,0xd80a,0); word(v,0xd80c,0x8003); word(v,0xd80e,128);
 vdp_render(&c); pixel(v,0,0,255,0,0); pixel(v,8,0,0,0,255);
 word(v,0xd804,0x8802); vdp_render(&c); pixel(v,0,0,0,0,255); pixel(v,8,0,0,255,0);
''')

    def test_backdrop_display_disabled_and_unsupported_modes(self):
        self.check('''
 v->registers[7]=3; v->registers[1]=4; vdp_render(&c);
 pixel(v,0,0,0,0,255); assert(v->frame_width==256 && v->frame_height==224);
 v->registers[1]=0x4c; vdp_render(&c); assert(v->frame_height==240);
 uint64_t before=v->rendered_frames; v->registers[12]=6; vdp_render(&c);
 assert(v->render_unsupported && v->rendered_frames==before);
''')

    def test_snapshot_is_taken_at_vblank_only_while_display_enabled(self):
        self.check('''
 vdp_advance(&c,224*3420); assert(v->rendered_frames==1);
 v->registers[1]=4; vdp_advance(&c,262*3420); assert(v->rendered_frames==1);
''')

    def test_shadow_highlight_planes_transparent_priority_and_sprite_operators(self):
        self.check('''
 v->registers[12]=8;
 tile(v,1,1); tile(v,2,2); tile(v,3,14); tile(v,4,15);
 word(v,0xc000,1); vdp_render(&c); pixel(v,0,0,127,0,0);
 assert(!v->render_unsupported);
 word(v,0xa000,0x8000); vdp_render(&c); pixel(v,0,0,255,0,0);
 word(v,0xa000,0); word(v,0xc000,0x8001);
 vdp_render(&c); pixel(v,0,0,255,0,0);
 word(v,0xd800,128); word(v,0xd802,0); word(v,0xd804,0x6003); word(v,0xd806,128);
 vdp_render(&c); pixel(v,0,0,255,0,0); /* Low sprite blocked by opaque high plane. */
 word(v,0xd804,0xe003); vdp_render(&c); pixel(v,0,0,255,127,127);
 word(v,0xd804,0xe004); vdp_render(&c); pixel(v,0,0,127,0,0);
 word(v,0xc000,1); word(v,0xd804,0x6003);
 vdp_render(&c); pixel(v,0,0,255,0,0); /* Highlight lifts shadow to normal. */
 word(v,0xd804,2); vdp_render(&c); pixel(v,0,0,0,127,0);
 word(v,0xd804,0x8002); vdp_render(&c); pixel(v,0,0,0,255,0);
 v->cram[14]=0x000e; word(v,0xd804,3);
 vdp_render(&c); pixel(v,0,0,255,0,0); /* Ordinary sprite color E stays normal. */
 word(v,0xa000,0x8000); word(v,0xd804,2);
 vdp_render(&c); pixel(v,0,0,0,255,0); /* Transparent priority selects intensity. */
''')

    def test_shadow_highlight_channel_levels_and_backdrop(self):
        self.check('''
 for (unsigned channel=0;channel<8;++channel) {
   assert(vdp_channel(channel,0)==channel*255/14);
   assert(vdp_channel(channel,1)==channel*255/7);
   assert(vdp_channel(channel,2)==(channel+7)*255/14);
 }
 v->registers[12]=8; v->registers[7]=3;
 vdp_render(&c); pixel(v,0,0,0,0,127);
 word(v,0xc000,0x8000); vdp_render(&c); pixel(v,0,0,0,0,255);
''')

    def test_standalone_frame_dump_is_ppm(self):
        code='33fc 8144 00c00004 3039 00c00004 0800 0003 67f4 4e72 2700'
        path=self.root/'frame.ppm'
        result=self.execute(rom_with(code),['--limit','100000','--dump-frame',str(path)])
        self.assertEqual(result.returncode,0,result.stderr)
        data=path.read_bytes()
        self.assertTrue(data.startswith(b'P6\n256 224\n255\n'))
        self.assertEqual(len(data),len(b'P6\n256 224\n255\n')+256*224*3)
