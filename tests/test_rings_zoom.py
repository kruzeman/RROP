"""World-only zoom, frozen UI layers and real SDL wheel event regressions."""
import contextlib
import io
import os
import subprocess
import unittest

from genesis_recompiler.cli import main
from genesis_recompiler.decode import analyze
from genesis_recompiler.emit import emit
from support import CompiledTestCase, rom_with
import test_rings_wide as wide_tests
from test_rings_fonts import LIVE_TEXT


ZOOM_SCENE = wide_tests.SCENE+r'''
static void zoom_scene(CPU *c,RingsWide *w) {
 c->rom=rom_data;c->rom_size=sizeof rom_data;
 scene(c,w);w->bank=1024;c->vdp.wide_enabled=0;c->vdp.zoom_enabled=1;
 w->focus_x=184;w->focus_y=124;
 for(unsigned y=0;y<23;++y)for(unsigned x=2;x<38;++x) {
  unsigned value=w->bank+y*36+x-2,at=0x1000+(y*64+x)*2;
  c->vdp.vram[at]=(uint8_t)(value>>8);c->vdp.vram[at+1]=(uint8_t)value;
  memset(c->vdp.vram+value*32,0x11,32);
 }
 w->zoom_valid=1;memset(w->zoom_scene,2,sizeof w->zoom_scene);
 for(unsigned y=0;y<RINGS_ZOOM_HEIGHT;++y)w->zoom_scene[y*RINGS_ZOOM_WIDTH+RINGS_ZOOM_LEFT+190]=3;
}
'''


class RingsZoomTests(CompiledTestCase):
    def check(self,body):
        program=analyze(rom_with('4e72 2700'),[0x200])
        source='#define GENESIS_NO_MAIN\n#define GENESIS_RINGS_WIDE\n'+emit(program)
        source+='\n#include <assert.h>\n'+ZOOM_SCENE+'\nint main(void) { CPU *c=calloc(1,sizeof *c);assert(c);RingsWide w={0};zoom_scene(c,&w);\n'+body+'\nfree(c);return 0;}'
        binary=self.compile(source)
        result=subprocess.run([str(binary)],capture_output=True,text=True,timeout=15)
        self.assertEqual(result.returncode,0,result.stderr)

    def test_unit_scale_is_byte_identical_and_world_changes_only_inside_the_mask(self):
        self.check(r'''
vdp_render(c);assert(c->vdp.zoom_world_visible);
uint8_t out[400*240*3];rings_zoom_pixels(&c->vdp,100,0,out);
assert(!memcmp(out,c->vdp.frame,320*224*3));
rings_zoom_pixels(&c->vdp,50,0,out);
assert(out[(96*320+160)*3+1]==255);
for(unsigned p=0;p<320*224;++p)if(!c->vdp.zoom_mask[p])
 assert(!memcmp(out+p*3,c->vdp.frame+p*3,3));
assert(!c->steps && !c->cycles && !c->fault);
''')

    def test_zoom_retains_priority_ui_and_sprites_at_their_original_size(self):
        self.check(r'''
unsigned at=0x1000+(5*64+10)*2;c->vdp.vram[at]=0x80;c->vdp.vram[at+1]=1;
c->vdp.registers[5]=0x7e;
c->vdp.vram[0xfc01]=128+40;c->vdp.vram[0xfc05]=2;c->vdp.vram[0xfc07]=128+112;
vdp_render(c);uint8_t out[400*240*3];rings_zoom_pixels(&c->vdp,80,0,out);
for(unsigned y=40;y<48;++y)for(unsigned x=80;x<88;++x)
 assert(!c->vdp.zoom_mask[y*320+x] && !memcmp(out+(y*320+x)*3,c->vdp.frame+(y*320+x)*3,3));
for(unsigned y=40;y<48;++y)for(unsigned x=112;x<120;++x)
 assert(!c->vdp.zoom_mask[y*320+x] && !memcmp(out+(y*320+x)*3,c->vdp.frame+(y*320+x)*3,3));
''')

    def test_scaled_outline_can_cross_transparent_pixels_of_the_unscaled_world(self):
        self.check(r'''
/* A transparent tile and an empty wide scene used to freeze the old outline. */
unsigned tile=w.bank+5*36+10-2;memset(c->vdp.vram+tile*32,0,32);
memset(w.scene,0,sizeof w.scene);c->vdp.registers[7]=4;
uint8_t out[400*240*3];
for(unsigned wide=0;wide<2;++wide) {
 c->vdp.wide_enabled=(uint8_t)wide;vdp_render(c);
 unsigned width=rings_view_width(&c->vdp),x=80+wide*40,p=40*width+x;
 assert(c->vdp.zoom_mask[p]);
 for(unsigned percent=50;percent<=90;percent+=10) {
  rings_zoom_pixels(&c->vdp,percent,0,out);
  assert(!out[p*3] && out[p*3+1]==255 && !out[p*3+2]);
 }
 rings_zoom_pixels(&c->vdp,100,0,out);
 assert(!memcmp(out,rings_view_pixels(&c->vdp,0),width*224*3));
}
''')

    def test_native_aperture_preserves_frame_and_clears_original_world_outside_it(self):
        self.check(r'''
/* A non-priority decorative pixel is behind the unscaled world, but outside
   the real viewport opening. The adjacent transparent B cell is inside it. */
unsigned at=0xa000+(5*64+10)*2;c->vdp.vram[at]=0;c->vdp.vram[at+1]=1;
vdp_render(c);uint8_t out[400*240*3];unsigned frame=40*320+80,inside=40*320+88;
assert(c->vdp.frame[frame*3]==255 && !c->vdp.frame[frame*3+2]);
assert(!c->vdp.zoom_mask[frame] && c->vdp.zoom_restore[frame]);
assert(c->vdp.zoom_mask[inside] && c->vdp.zoom_restore[inside]);
for(unsigned percent=50;percent<=90;percent+=10) {
 rings_zoom_pixels(&c->vdp,percent,0,out);
 assert(!out[frame*3] && !out[frame*3+1] && out[frame*3+2]==255);
 assert(!out[inside*3] && out[inside*3+1]==255 && !out[inside*3+2]);
}
/* Pause uses both frozen masks and the frozen decorative background. */
memset(c->vdp.vram+32,0x44,32);rings_zoom_pixels(&c->vdp,80,0,out);
assert(!out[frame*3] && out[frame*3+2]==255);
rings_zoom_pixels(&c->vdp,100,0,out);assert(!memcmp(out,c->vdp.frame,320*224*3));
c->vdp.wide_enabled=1;vdp_render(c);
assert(c->vdp.zoom_mask[40*400+120]); /* Wide mode still admits world over decorations. */
rings_zoom_pixels(&c->vdp,50,0,out);assert(out[(40*400+120)*3+1]==255);
assert(!c->steps && !c->cycles && !c->fault);
''')

    def test_elevated_world_crosses_frame_only_when_its_ground_is_inside(self):
        self.check(r'''
unsigned at=0xa000+(5*64+10)*2;c->vdp.vram[at]=0;c->vdp.vram[at+1]=1;
memset(w.lift_scene,48,sizeof w.lift_scene);
vdp_render(c);uint8_t out[400*240*3];unsigned p=40*320+80;
for(unsigned percent=50;percent<=90;percent+=10) {
 rings_zoom_pixels(&c->vdp,percent,0,out);
 assert(!c->vdp.zoom_mask[p] && c->vdp.zoom_restore[p]);
 assert(!out[p*3] && out[p*3+1]==255 && !out[p*3+2]);
}
/* Pause freezes the elevation too, even when the replay buffers change. */
memset(w.lift_scene,0,sizeof w.lift_scene);rings_zoom_pixels(&c->vdp,50,0,out);
assert(out[p*3+1]==255);
/* A raised object's supporting ground now lies outside the aperture. */
for(unsigned y=6;y<11;++y) {
 unsigned b=0xa000+(y*64+10)*2;c->vdp.vram[b]=0;c->vdp.vram[b+1]=1;
}
memset(w.lift_scene,48,sizeof w.lift_scene);vdp_render(c);
rings_zoom_pixels(&c->vdp,50,0,out);assert(!out[p*3+1] && out[p*3+2]==255);
rings_zoom_pixels(&c->vdp,100,0,out);assert(!memcmp(out,c->vdp.frame,320*224*3));
assert(!c->steps && !c->cycles && !c->fault);
''')

    def test_zoom_reuses_frozen_scene_palette_and_ui_during_pause(self):
        self.check(r'''
vdp_render(c);uint8_t first[400*240*3],second[400*240*3];
rings_zoom_pixels(&c->vdp,70,0,first);
memset(w.zoom_scene,3,sizeof w.zoom_scene);c->vdp.cram[2]=0x0e00;memset(c->ram,9,sizeof c->ram);
rings_zoom_pixels(&c->vdp,70,0,second);assert(!memcmp(first,second,320*224*3));
vdp_render(c);rings_zoom_pixels(&c->vdp,70,0,second);assert(memcmp(first,second,320*224*3));
''')

    def test_hero_anchor_survives_scale_changes_and_transparent_pixels_clear_the_old_world(self):
        self.check(r'''
memset(w.zoom_scene,0,sizeof w.zoom_scene);
for(unsigned y=RINGS_ZOOM_TOP+96;y<=RINGS_ZOOM_TOP+97;++y)
 for(unsigned x=RINGS_ZOOM_LEFT+184;x<=RINGS_ZOOM_LEFT+185;++x)w.zoom_scene[y*RINGS_ZOOM_WIDTH+x]=2;
c->vdp.registers[7]=4;vdp_render(c);uint8_t out[400*240*3];
unsigned scales[]={50,60,70,80,90};
for(unsigned i=0;i<sizeof scales/sizeof *scales;++i) {
 rings_zoom_pixels(&c->vdp,scales[i],0,out);
 assert(out[(96*320+160)*3+1]==255 && !out[(96*320+160)*3]);
 assert(out[(40*320+40)*3]==255 && out[(40*320+40)*3+1]==255);
}
''')

    def test_unrecognized_scenes_fall_back_and_wide_mode_supports_half_scale(self):
        self.check(r'''
c->vdp.wide_enabled=1;vdp_render(c);uint8_t out[400*240*3];
rings_zoom_pixels(&c->vdp,50,0,out);assert(out[(96*400+16)*3+1]==255 && out[(96*400+383)*3+1]==255);
c->vdp.wide_enabled=0;c->vdp.registers[17]=0;vdp_render(c);
assert(!c->vdp.zoom_world_visible);rings_zoom_pixels(&c->vdp,200,0,out);
assert(!memcmp(out,c->vdp.frame,320*224*3));
''')

    def test_zoom_compiler_option_requires_window_and_verified_rom(self):
        rom=self.root/'demo.gen';rom.write_bytes(rom_with('4e72 2700'))
        with contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as exc:main([str(rom),'--rings-zoom','-o',str(self.root/'game')])
            self.assertEqual(exc.exception.code,2)
            self.assertEqual(main([str(rom),'--build','--frontend','sdl2','--rings-zoom','-o',str(self.root/'game')]),1)
        result=self.execute(rom.read_bytes(),['--zoom'])
        self.assertEqual(result.returncode,64);self.assertIn('zoom support is not compiled in',result.stderr)

    def test_half_scale_has_source_coverage_at_extreme_hero_anchors(self):
        self.check(r'''
c->vdp.wide_enabled=1;memset(w.zoom_scene,2,sizeof w.zoom_scene);
unsigned xs[]={134,238},ys[]={RINGS_SCENE_TOP+48,RINGS_SCENE_TOP+128};
uint8_t out[400*240*3];
for(unsigned i=0;i<2;++i)for(unsigned j=0;j<2;++j) {
 w.focus_x=(uint16_t)xs[i];w.focus_y=(uint16_t)ys[j];vdp_render(c);
 rings_zoom_pixels(&c->vdp,50,0,out);
for(unsigned y=0;y<224;++y)for(unsigned x=0;x<400;++x)
  if(c->vdp.zoom_mask[y*400+x])assert(out[(y*400+x)*3+1]==255);
}
''')


class RingsZoomSDLTests(CompiledTestCase):
    @classmethod
    def setUpClass(cls):
        wide_tests.RingsWideSDLTests.setUpClass.__func__(cls)

    def check_sdl(self,body,font=False):
        program=analyze(rom_with('4e72 2700'),[0x200])
        source='#define GENESIS_NO_MAIN\n'+emit(program)+'\n#include <assert.h>\n'+LIVE_TEXT+ZOOM_SCENE+r'''
static void wheel(int delta,unsigned direction) {
 SDL_Event e={0};e.type=SDL_MOUSEWHEEL;e.wheel.y=delta;e.wheel.direction=direction;
 assert(SDL_PushEvent(&e)==1);
}
int main(int argc,char **argv) {
 (void)argc;(void)argv;CPU *c=calloc(1,sizeof *c);assert(c);RingsWide w={0};zoom_scene(c,&w);
 SDLHost h={0};h.no_throttle=1;assert(sdl_host_open(&h));
'''+body+'\nsdl_host_close(&h);free(c);return 0;}\n'
        path=self.root/'zoom.c';path.write_text(source);binary=self.root/'zoom'
        result=subprocess.run(['cc','-std=c11','-O2','-Wall','-Wextra','-Werror','-Wno-unused-function',
            '-DGENESIS_SDL2','-DGENESIS_RINGS_WIDE','-DGENESIS_RINGS_MENU_FONT',*self.flags,str(path),'-o',str(binary),*self.libs],capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stderr)
        result=subprocess.run([str(binary),*([self.font] if font else [])],
            env=dict(os.environ,SDL_VIDEODRIVER='dummy',SDL_RENDER_DRIVER='software'),capture_output=True,text=True,timeout=15)
        self.assertEqual(result.returncode,0,result.stderr)

    def test_wheel_clamps_flipped_direction_and_reset_without_advancing_game(self):
        self.check_sdl(r'''
vdp_render(c);assert(sdl_host_service(&h,c));assert(h.zoom_percent==100);
SDL_Event held={0};held.type=SDL_KEYDOWN;held.key.keysym.sym=SDLK_RIGHT;
assert(SDL_PushEvent(&held)==1);assert(sdl_host_service(&h,c));uint64_t frame=c->vdp.rendered_frames;
wheel(-1,SDL_MOUSEWHEEL_NORMAL);assert(sdl_host_service(&h,c));assert(h.zoom_percent==90 && h.last_zoom==90);
assert(c->vdp.rendered_frames==frame && !c->steps && !c->cycles && c->pad_buttons[0]==PAD_RIGHT);
wheel(2147483647,SDL_MOUSEWHEEL_NORMAL);assert(sdl_host_service(&h,c));assert(h.zoom_percent==100);
wheel(2147483647,SDL_MOUSEWHEEL_FLIPPED);assert(sdl_host_service(&h,c));assert(h.zoom_percent==50);
SDL_Event e={0};e.type=SDL_MOUSEBUTTONDOWN;e.button.button=SDL_BUTTON_MIDDLE;
assert(SDL_PushEvent(&e)==1);assert(sdl_host_service(&h,c));assert(h.zoom_percent==100 && h.last_zoom==100);
h.paused=1;wheel(-3,SDL_MOUSEWHEEL_NORMAL);assert(sdl_host_service(&h,c));assert(h.zoom_percent==70);
e.type=SDL_KEYDOWN;e.key.keysym.sym=SDLK_0;assert(SDL_PushEvent(&e)==1);
assert(sdl_host_service(&h,c));assert(h.zoom_percent==100);
c->vdp.zoom_world_visible=0;wheel(2,SDL_MOUSEWHEEL_NORMAL);assert(sdl_host_service(&h,c));assert(h.zoom_percent==100);
c->vdp.zoom_world_visible=1;c->vdp.wide_enabled=1;vdp_render(c);
wheel(-20,SDL_MOUSEWHEEL_NORMAL);assert(sdl_host_service(&h,c));assert(h.zoom_percent==50 && h.width==400);
''')

    def test_zoom_out_keeps_single_scene_columns_at_drawable_resolution(self):
        self.check_sdl(r'''
memset(w.zoom_scene,2,sizeof w.zoom_scene);
for(unsigned y=0;y<RINGS_ZOOM_HEIGHT;++y)w.zoom_scene[y*RINGS_ZOOM_WIDTH+RINGS_ZOOM_LEFT+191]=3;
vdp_render(c);assert(sdl_host_service(&h,c));
/* The old 320-pixel resample skips source column 191 at 80%. */
uint8_t low[400*240*3];rings_zoom_pixels(&c->vdp,80,0,low);
unsigned old_blue=0;
for(unsigned x=16;x<304;++x)old_blue+=low[(96*320+x)*3+2]==255;
assert(!old_blue);
wheel(-2,SDL_MOUSEWHEEL_NORMAL);assert(sdl_host_service(&h,c));assert(h.zoom_percent==80);
uint8_t row[960*3];SDL_Rect region={0,288,960,1};
assert(!SDL_RenderReadPixels(h.renderer,&region,SDL_PIXELFORMAT_RGB24,row,960*3));
unsigned blue=0;
for(unsigned x=48;x<912;++x)if(row[x*3+2]==255 && row[x*3]==0 && row[x*3+1]==0)++blue;
assert(blue>=2 && blue<=3); /* Source pixel now occupies ~2.4 screen pixels. */
assert(!c->steps && !c->cycles && !c->fault && !SDL_RenderIsClipEnabled(h.renderer));
''')

    def test_device_world_outline_moves_independently_of_the_original_silhouette(self):
        self.check_sdl(r'''
/* Two opposite old/new opacity cases, plus a fixed priority UI tile. */
unsigned tile=w.bank+5*36+10-2;memset(c->vdp.vram+tile*32,0,32);
memset(w.scene,0,sizeof w.scene);c->vdp.registers[7]=4;
unsigned at=0x1000+(5*64+12)*2;
c->vdp.vram[at]=0x80;c->vdp.vram[at+1]=1;
/* At 50%, native (160,40) samples just above the hero, a new hole. */
for(unsigned y=RINGS_ZOOM_TOP-24;y<RINGS_ZOOM_TOP+6;++y)
 for(unsigned x=RINGS_ZOOM_LEFT+176;x<RINGS_ZOOM_LEFT+206;++x)
 w.zoom_scene[y*RINGS_ZOOM_WIDTH+x]=0;
uint8_t rgb[3];
for(unsigned wide=0;wide<2;++wide) {
 c->vdp.wide_enabled=(uint8_t)wide;vdp_render(c);
 h.zoom_percent=100;assert(sdl_host_service(&h,c));
 SDL_SetWindowSize(h.window,wide ? 1200:960,672);assert(sdl_host_draw(&h,&c->vdp));
 wheel(-5,SDL_MOUSEWHEEL_NORMAL);assert(sdl_host_service(&h,c));
 SDL_Rect green={(80+(int)wide*40)*3+1,40*3+1,1,1};
 assert(!SDL_RenderReadPixels(h.renderer,&green,SDL_PIXELFORMAT_RGB24,rgb,3));
 assert(!rgb[0] && rgb[1]==255 && !rgb[2]);
 SDL_Rect hole={(160+(int)wide*40)*3+1,40*3+1,1,1};
 assert(!SDL_RenderReadPixels(h.renderer,&hole,SDL_PIXELFORMAT_RGB24,rgb,3));
 assert(rgb[0]==255 && rgb[1]==255 && rgb[2]==255);
 SDL_Rect ui={(96+(int)wide*40)*3+1,40*3+1,1,1};
 assert(!SDL_RenderReadPixels(h.renderer,&ui,SDL_PIXELFORMAT_RGB24,rgb,3));
 assert(!rgb[0] && !rgb[1] && rgb[2]==255);
}
assert(!c->steps && !c->cycles && !c->fault);
''')

    def test_device_native_zoom_keeps_aperture_at_every_scale_and_removes_old_world_ghosts(self):
        self.check_sdl(r'''
unsigned at=0xa000+(5*64+10)*2;c->vdp.vram[at]=0;c->vdp.vram[at+1]=1;
vdp_render(c);assert(sdl_host_service(&h,c));
uint8_t *before=malloc(960*672*3),*after=malloc(960*672*3);assert(before && after);
assert(!SDL_RenderReadPixels(h.renderer,NULL,SDL_PIXELFORMAT_RGB24,before,960*3));
for(unsigned percent=50;percent<=90;percent+=10) {
 h.zoom_percent=percent;assert(sdl_host_draw(&h,&c->vdp));
 uint8_t rgb[3];SDL_Rect frame={80*3+1,40*3+1,1,1},inside={88*3+1,40*3+1,1,1};
 assert(!SDL_RenderReadPixels(h.renderer,&frame,SDL_PIXELFORMAT_RGB24,rgb,3));
 assert(!rgb[0] && !rgb[1] && rgb[2]==255);
 assert(!SDL_RenderReadPixels(h.renderer,&inside,SDL_PIXELFORMAT_RGB24,rgb,3));
 assert(!rgb[0] && rgb[1]==255 && !rgb[2]);
}
h.zoom_percent=100;assert(sdl_host_draw(&h,&c->vdp));
assert(!SDL_RenderReadPixels(h.renderer,NULL,SDL_PIXELFORMAT_RGB24,after,960*3));
assert(!memcmp(before,after,960*672*3));free(before);free(after);
assert(!c->steps && !c->cycles && !c->fault && !SDL_RenderIsClipEnabled(h.renderer));
''')

    def test_device_elevated_objects_spill_over_frame_but_stay_behind_ui(self):
        self.check_sdl(r'''
unsigned at=0xa000+(5*64+10)*2;c->vdp.vram[at]=0;c->vdp.vram[at+1]=1;
at=0x1000+(5*64+12)*2;c->vdp.vram[at]=0x80;c->vdp.vram[at+1]=1;
memset(w.lift_scene,48,sizeof w.lift_scene);vdp_render(c);
assert(sdl_host_service(&h,c));
uint8_t rgb[3];SDL_Rect roof={80*3+1,40*3+1,1,1},ui={96*3+1,40*3+1,1,1};
for(unsigned percent=50;percent<=90;percent+=10) {
 h.zoom_percent=percent;assert(sdl_host_draw(&h,&c->vdp));
 assert(!SDL_RenderReadPixels(h.renderer,&roof,SDL_PIXELFORMAT_RGB24,rgb,3));
 assert(!rgb[0] && rgb[1]==255 && !rgb[2]);
 assert(!SDL_RenderReadPixels(h.renderer,&ui,SDL_PIXELFORMAT_RGB24,rgb,3));
 assert(!rgb[0] && !rgb[1] && rgb[2]==255);
}
memset(w.lift_scene,0,sizeof w.lift_scene);h.paused=1;h.zoom_percent=50;
assert(sdl_host_draw(&h,&c->vdp));
assert(!SDL_RenderReadPixels(h.renderer,&roof,SDL_PIXELFORMAT_RGB24,rgb,3));assert(rgb[1]==255);
assert(!c->steps && !c->cycles && !c->fault && !SDL_RenderIsClipEnabled(h.renderer));
''')

    def test_device_zoom_preserves_ui_transparency_pause_resize_and_exact_reset(self):
        self.check_sdl(r'''
memset(w.zoom_scene,0,sizeof w.zoom_scene);
for(unsigned y=RINGS_ZOOM_TOP+96;y<=RINGS_ZOOM_TOP+97;++y)
 for(unsigned x=RINGS_ZOOM_LEFT+184;x<=RINGS_ZOOM_LEFT+185;++x)w.zoom_scene[y*RINGS_ZOOM_WIDTH+x]=2;
c->vdp.registers[7]=4;
vdp_render(c);assert(sdl_host_service(&h,c));
uint8_t *before=malloc(960*672*3),*after=malloc(960*672*3);assert(before && after);
assert(!SDL_RenderReadPixels(h.renderer,NULL,SDL_PIXELFORMAT_RGB24,before,960*3));
wheel(-5,SDL_MOUSEWHEEL_NORMAL);assert(sdl_host_service(&h,c));
assert(!SDL_RenderReadPixels(h.renderer,NULL,SDL_PIXELFORMAT_RGB24,after,960*3));
for(unsigned y=0;y<224;++y)for(unsigned x=0;x<320;++x)if(!c->vdp.zoom_mask[y*320+x])
 assert(!memcmp(before+((y*3+1)*960+x*3+1)*3,after+((y*3+1)*960+x*3+1)*3,3));
assert(after[(120*960+120)*3]==255 && after[(120*960+120)*3+1]==255);
assert(after[(288*960+480)*3+1]==255 && !after[(288*960+480)*3]);
h.paused=1;memset(w.zoom_scene,3,sizeof w.zoom_scene);c->vdp.cram[2]=0x0e00;
assert(sdl_host_draw(&h,&c->vdp));
uint8_t *frozen=malloc(960*672*3);assert(frozen);
assert(!SDL_RenderReadPixels(h.renderer,NULL,SDL_PIXELFORMAT_RGB24,frozen,960*3));
assert(!memcmp(after,frozen,960*672*3));free(frozen);
SDL_SetWindowSize(h.window,1200,900);assert(sdl_host_draw(&h,&c->vdp));
uint8_t rgb[3];SDL_Rect bar={600,0,1,1};
assert(!SDL_RenderReadPixels(h.renderer,&bar,SDL_PIXELFORMAT_RGB24,rgb,3));
assert(!rgb[0] && !rgb[1] && !rgb[2]);
SDL_SetWindowSize(h.window,960,672);wheel(5,SDL_MOUSEWHEEL_NORMAL);assert(sdl_host_service(&h,c));
assert(h.zoom_percent==100);
assert(!SDL_RenderReadPixels(h.renderer,NULL,SDL_PIXELFORMAT_RGB24,after,960*3));
assert(!memcmp(before,after,960*672*3));
assert(!c->steps && !c->cycles && !c->fault);free(before);free(after);
''')

    def test_device_zoom_masks_wide_ui_and_restores_wide_presentation(self):
        self.check_sdl(r'''
c->vdp.wide_enabled=1;vdp_render(c);assert(sdl_host_service(&h,c));
SDL_SetWindowSize(h.window,1200,672);assert(sdl_host_draw(&h,&c->vdp));
uint8_t *before=malloc(1200*672*3),*after=malloc(1200*672*3);assert(before && after);
assert(!SDL_RenderReadPixels(h.renderer,NULL,SDL_PIXELFORMAT_RGB24,before,1200*3));
wheel(-5,SDL_MOUSEWHEEL_NORMAL);assert(sdl_host_service(&h,c));assert(h.width==400);
assert(!SDL_RenderReadPixels(h.renderer,NULL,SDL_PIXELFORMAT_RGB24,after,1200*3));
for(unsigned y=0;y<224;++y)for(unsigned x=0;x<400;++x)if(!c->vdp.zoom_mask[y*400+x])
 assert(!memcmp(before+((y*3+1)*1200+x*3+1)*3,after+((y*3+1)*1200+x*3+1)*3,3));
wheel(5,SDL_MOUSEWHEEL_NORMAL);assert(sdl_host_service(&h,c));
assert(!SDL_RenderReadPixels(h.renderer,NULL,SDL_PIXELFORMAT_RGB24,after,1200*3));
assert(!memcmp(before,after,1200*672*3));free(before);free(after);
''')

    def test_wide_world_fills_edges_at_full_and_half_scale_without_wheel_support(self):
        self.check_sdl(r'''
c->vdp.wide_enabled=1;c->vdp.zoom_enabled=0;
unsigned at=0x1000+(25*64+10)*2;
c->vdp.vram[at]=0x80;c->vdp.vram[at+1]=2;
vdp_render(c);assert(sdl_host_service(&h,c));
SDL_SetWindowSize(h.window,1200,672);
for(unsigned percent=50;percent<=100;percent+=50) {
 h.zoom_percent=percent;assert(sdl_host_draw(&h,&c->vdp));
 unsigned xs[]={0,1199,60,1140},ys[]={0,671,600,630};uint8_t rgb[3];
 for(unsigned i=0;i<4;++i) {
  SDL_Rect pixel={(int)xs[i],(int)ys[i],1,1};
  assert(!SDL_RenderReadPixels(h.renderer,&pixel,SDL_PIXELFORMAT_RGB24,rgb,3));
  assert(!rgb[0] && rgb[1]==255 && !rgb[2]);
 }
 SDL_Rect hud={120+80*3+1,200*3+1,1,1};
 assert(!SDL_RenderReadPixels(h.renderer,&hud,SDL_PIXELFORMAT_RGB24,rgb,3));
 assert(rgb[0]==255 && rgb[1]==255 && rgb[2]==255);
}
wheel(-5,SDL_MOUSEWHEEL_NORMAL);assert(sdl_host_service(&h,c));assert(h.zoom_percent==100);
assert(!c->steps && !c->cycles && !c->fault);
''')

    def test_external_font_pixels_and_metrics_do_not_scale_with_world(self):
        self.check_sdl(r'''
assert(argc==2);c->vdp.font_enabled=1;memset(c->vdp.font_supported,1,sizeof c->vdp.font_supported);
character(c,0x1000+(13*64+17)*2,'C',0x11192);
assert(rings_font_open(&h.font,argv[1]));vdp_render(c);assert(c->vdp.font_count==1);
assert(sdl_host_service(&h,c));int pixels=h.font.pixels;uint8_t before[24*24*3],after[24*24*3];
SDL_Rect region={136*3,104*3,24,24};
assert(!SDL_RenderReadPixels(h.renderer,&region,SDL_PIXELFORMAT_RGB24,before,24*3));
wheel(-3,SDL_MOUSEWHEEL_NORMAL);assert(sdl_host_service(&h,c));assert(h.zoom_percent==70);
assert(!SDL_RenderReadPixels(h.renderer,&region,SDL_PIXELFORMAT_RGB24,after,24*3));
assert(!memcmp(before,after,sizeof before) && h.font.pixels==pixels);
SDL_SetWindowSize(h.window,1280,896);assert(sdl_host_draw(&h,&c->vdp));assert(h.font.pixels>pixels);
assert(!SDL_RenderIsClipEnabled(h.renderer));
''',font=True)

    def test_full_wide_font_snapshot_removes_bitmap_ink_and_allows_world_under_text(self):
        self.check_sdl(r'''
assert(argc==2);c->vdp.wide_enabled=1;c->vdp.font_enabled=1;
memset(c->vdp.font_supported,1,sizeof c->vdp.font_supported);
character(c,0x1000+(13*64+17)*2,'C',0x11192);
assert(rings_font_open(&h.font,argv[1]));vdp_render(c);
assert(c->vdp.font_count==1 && !c->vdp.font_hide);
for(unsigned y=104;y<112;++y)for(unsigned x=176;x<184;++x) {
 unsigned p=y*400+x;
 assert(c->vdp.wide_frame[p*3]==255 && !c->vdp.wide_frame[p*3+1]);
 assert(!c->vdp.wide_font_frame[p*3] && c->vdp.wide_font_frame[p*3+1]==255);
 assert(c->vdp.zoom_mask[p]);
}
assert(sdl_host_service(&h,c));
wheel(-5,SDL_MOUSEWHEEL_NORMAL);assert(sdl_host_service(&h,c));
assert(h.zoom_percent==50 && !c->steps && !c->cycles && !c->fault);
''',font=True)
