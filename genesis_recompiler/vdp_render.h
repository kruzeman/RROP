/* Mode 5 progressive frame snapshot, including shadow/highlight. No raster effects. */
#ifndef GENESIS_VDP_RENDER_H
#define GENESIS_VDP_RENDER_H
static uint16_t vdp_word(const VDP *v, unsigned address) {
    return (uint16_t)((v->vram[address&65535]<<8)|v->vram[(address+1)&65535]);
}
static unsigned vdp_pattern(const VDP *v, unsigned tile, unsigned x, unsigned y) {
    unsigned byte=v->vram[(tile*32+y*4+x/2)&65535];
    return x&1 ? byte&15:byte>>4;
}
static unsigned vdp_tile_pixel(const VDP *v, unsigned entry, unsigned x, unsigned y) {
    if (entry&0x0800) x=7-x;
    if (entry&0x1000) y=7-y;
    unsigned nibble=vdp_pattern(v,entry&0x7ff,x,y);
    /* Transparent high-priority plane pixels still select normal intensity
       in shadow/highlight mode, without hiding the other plane or sprites. */
    return nibble ? ((entry>>9)&0x30)|nibble|((entry>>8)&0x80):
                   (v->registers[12]&8 ? (entry>>8)&0x80:0);
}
static unsigned vdp_plane_address(const VDP *v, unsigned plane, unsigned x, unsigned y, unsigned *sx_out, unsigned *sy_out) {
    unsigned wm=v->registers[16]&3, hm=(v->registers[16]>>4)&3;
    unsigned width=32u<<(wm==3 ? 2:wm), height=32u<<(hm==3 ? 2:hm);
    unsigned mode=v->registers[11]&3;
    unsigned row=mode==3 ? y:mode==2 ? y&~7u:0;
    unsigned scroll_base=(v->registers[13]&0x3f)<<10;
    unsigned hscroll=vdp_word(v,scroll_base+row*4+plane*2)&0x3ff;
    unsigned column=(v->registers[11]&4) ? (x/16)*2+plane:plane;
    unsigned vscroll=column<40 ? v->vsram[column]&0x7ff:0;
    unsigned sx=(x-hscroll)&(width*8-1), sy=(y+vscroll)&(height*8-1);
    unsigned base=plane ? (v->registers[4]&7)<<13:(v->registers[2]&0x38)<<10;
    *sx_out=sx; *sy_out=sy;
    return (base+((sy/8)*width+sx/8)*2)&65535;
}
static unsigned vdp_name_pixel(const VDP *v,unsigned at,unsigned x,unsigned y,unsigned px,unsigned py,unsigned layer) {
#ifdef GENESIS_RINGS_MENU_FONT
    if(v->font_hide && (v->font_mask[py*v->frame_width+px]&layer))return 0;
#else
    (void)px;(void)py;(void)layer;
#endif
    return vdp_tile_pixel(v,vdp_word(v,at),x,y);
}
static unsigned vdp_plane_pixel(const VDP *v,unsigned plane,unsigned x,unsigned y) {
    unsigned sx,sy,at=vdp_plane_address(v,plane,x,y,&sx,&sy);
    return vdp_name_pixel(v,at,sx&7,sy&7,x,y,plane ? 2:1);
}
static int vdp_window_at(const VDP *v, unsigned x, unsigned y) {
    unsigned horizontal=(v->registers[17]&31)*16, vertical=(v->registers[18]&31)*8;
    return ((v->registers[17]&0x80) ? x>=horizontal:x<horizontal) ||
           ((v->registers[18]&0x80) ? y>=vertical:y<vertical);
}
static unsigned vdp_window_pixel(const VDP *v, unsigned x, unsigned y, int h40) {
    unsigned base=(v->registers[3]&(h40 ? 0x3c:0x3e))<<10;
    unsigned at=base+((y/8)*(h40 ? 64:32)+x/8)*2;
    return vdp_name_pixel(v,at&65535,x&7,y&7,x,y,1);
}
static void vdp_sprites(const VDP *v, unsigned width, unsigned height, uint8_t *pixels) {
    unsigned base=(v->registers[5]&(width==320 ? 0x7e:0x7f))<<9;
    unsigned link=0, maximum=width==320 ? 80:64;
    uint8_t visited[128]={0};
    for (unsigned n=0;n<maximum;++n) {
        if (link>=maximum || visited[link]) break;
        visited[link]=1;
        unsigned at=base+link*8;
        int top=(int)(vdp_word(v,at)&0x3ff)-128;
        unsigned size_link=vdp_word(v,at+2), entry=vdp_word(v,at+4);
        int left=(int)(vdp_word(v,at+6)&0x1ff)-128;
        unsigned w=((size_link>>10)&3)+1, h=((size_link>>8)&3)+1;
        for (unsigned y=0;y<h*8;++y) for (unsigned x=0;x<w*8;++x) {
            int px=left+(int)x, py=top+(int)y;
            if (px<0 || py<0 || px>=(int)width || py>=(int)height) continue;
            unsigned sx=entry&0x0800 ? w*8-1-x:x, sy=entry&0x1000 ? h*8-1-y:y;
            unsigned tile=(entry&0x7ff)+(sx/8)*h+sy/8;
            unsigned nibble=vdp_pattern(v,tile,sx&7,sy&7);
            size_t offset=(size_t)py*width+(unsigned)px;
            if (nibble && !pixels[offset]) pixels[offset]=(uint8_t)(nibble|((entry>>9)&0x30)|((entry>>8)&0x80));
        }
        link=size_link&127;
        if (!link) break;
    }
}
#ifdef GENESIS_RINGS_MENU_FONT
#include "rings_text.h"
#endif
/* Return palette index plus intensity in bits 6..7: shadow=0, normal=1,
   highlight=2. Background priority and sprite ordering are separate from
   intensity; sprite palette 3 colors E/F act on the background color. */
static unsigned vdp_shadow_pixel(unsigned a, unsigned b, unsigned s, unsigned backdrop) {
    unsigned background=(b&15) ? b:0;
    if ((a&15) && ((a&128) || !(background&128))) background=a;
    unsigned color=(background&15) ? background&63:backdrop;
    unsigned intensity=((a|b)&128) ? 1:0;
    if ((s&15) && ((s&128) || !(background&128))) {
        unsigned sprite=s&63;
        if (sprite==62) ++intensity;
        else if (sprite==63) intensity=0;
        else {
            color=sprite;
            if ((s&128) || (s&15)==14) intensity=1;
        }
    }
    return color|(intensity<<6);
}
static uint8_t vdp_channel(unsigned channel, unsigned intensity) {
    unsigned level=intensity==0 ? channel:intensity==2 ? channel+7:channel*2;
    return (uint8_t)(level*255/14);
}
static void vdp_render_pixels(VDP *v,unsigned width,unsigned height,const uint8_t *sprites,uint8_t *frame) {
    int h40=width==320;

    for (unsigned y=0;y<height;++y) for (unsigned x=0;x<width;++x) {
        unsigned color=v->registers[7]&63;
        unsigned intensity=1;
        if (v->registers[1]&0x40) {
            unsigned b=vdp_plane_pixel(v,1,x,y);
            unsigned a=vdp_window_at(v,x,y) ? vdp_window_pixel(v,x,y,h40):vdp_plane_pixel(v,0,x,y);
            unsigned s=sprites[y*width+x];
            if (v->registers[12]&8) {
                unsigned mixed=vdp_shadow_pixel(a,b,s,color);
                color=mixed&63; intensity=mixed>>6;
            } else {
                if (b && !(b&128)) color=b&63;
                if (a && !(a&128)) color=a&63;
                if (s && !(s&128)) color=s&63;
                if (b&128) color=b&63;
                if (a&128) color=a&63;
                if (s&128) color=s&63;
            }
        }
        unsigned rgb=v->cram[color];
        size_t offset=((size_t)y*width+x)*3;
        frame[offset]=vdp_channel((rgb>>1)&7,intensity);
        frame[offset+1]=vdp_channel((rgb>>5)&7,intensity);
        frame[offset+2]=vdp_channel((rgb>>9)&7,intensity);
    }
}
#include "rings_wide_compose.h"
#include "rings_zoom.h"
static void vdp_render(CPU *c) {
    VDP *v=&c->vdp;
    /* Unsupported video modes leave the last supported frame intact. */
    if (!(v->registers[1]&4) || (v->registers[12]&6) ||
        (v->registers[16]&3)==2 || ((v->registers[16]>>4)&3)==2 || (v->registers[11]&3)==1) {
        v->render_unsupported=1; return;
    }
    v->render_unsupported=0;
    int h40=v->registers[12]&1;
    unsigned width=h40 ? 320:256, height=vdp_visible_lines(v);
    uint8_t sprites[320*240]={0};
    if (v->registers[1]&0x40) vdp_sprites(v,width,height,sprites);
    v->frame_width=(uint16_t)width; v->frame_height=(uint16_t)height;
    vdp_render_pixels(v,width,height,sprites,v->frame);
#ifdef GENESIS_RINGS_MENU_FONT
    v->font_count=0;v->font_visible=0;
    if(v->font_enabled)rings_text_prepare(v,width,height,sprites);
    if(v->font_count) {
        v->font_hide=1;
        vdp_render_pixels(v,width,height,sprites,v->font_frame);
        v->font_hide=0;
    }
#endif
#ifdef GENESIS_RINGS_WIDE
    rings_scene_snapshot(c);
    v->wide_hud_active=0;
    if(v->wide_enabled && c->wide && !c->wide->replaying) {
        rings_wide_compose(c,sprites,v->frame,v->wide_frame);
#ifdef GENESIS_RINGS_MENU_FONT
        if(v->font_count) {
            v->font_hide=1;
            rings_wide_compose(c,sprites,v->font_frame,v->wide_font_frame);
            v->font_hide=0;
        }
#endif
    }
    if((v->zoom_enabled || v->wide_enabled) && c->wide && !c->wide->replaying)rings_zoom_prepare(c,sprites);
#endif
    v->frame_width=(uint16_t)width; v->frame_height=(uint16_t)height;
    ++v->rendered_frames;
}
#endif
