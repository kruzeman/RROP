/* Freeze an extended presentation frame while preserving the console frame. */
#ifndef GENESIS_RINGS_WIDE_COMPOSE_H
#define GENESIS_RINGS_WIDE_COMPOSE_H
#ifdef GENESIS_RINGS_WIDE
#include "rings_hud.h"
static int rings_bitmap_visible(const CPU *c) {
    const VDP *v=&c->vdp;const RingsWide *w=c->wide;
    if(!w || w->replaying || v->frame_width!=320 || !(v->registers[1]&0x40) ||
       (v->registers[12]&8) || ((v->registers[3]&0x3c)<<10)!=0x1000)return 0;
    if(!vdp_window_at(v,16,0) || !vdp_window_at(v,303,151))return 0;
    unsigned matches=0;
    for(unsigned x=2;x<38;++x)if(vdp_word(v,0x1000+x*2)==(unsigned)(w->bank+x-2))++matches;
    return matches>=12;
}
static int rings_wide_visible(const CPU *c) {
    return !c->vdp.native_scene && c->wide && c->wide->valid && rings_bitmap_visible(c);
}
static int rings_world_foreground(const VDP *v,const uint8_t *sprites,unsigned x,unsigned y) {
    unsigned at,sx,sy;
    if(vdp_window_at(v,x,y))at=((v->registers[3]&0x3c)<<10)+((y/8)*64+x/8)*2;
    else at=vdp_plane_address(v,0,x,y,&sx,&sy);
    unsigned b=vdp_plane_pixel(v,1,x,y);
    return (vdp_word(v,at)&0x8000) || (sprites[y*v->frame_width+x]&15) || ((b&128) && (b&15));
}
/* Keep actual interface ink, not transparent priority cells which used to
   reveal the decorative plane B. External fonts are drawn after composition. */
static unsigned rings_wide_ui_pixel(const VDP *v,const uint8_t *sprites,unsigned x,unsigned y) {
    unsigned a=vdp_window_at(v,x,y) ? vdp_window_pixel(v,x,y,1):vdp_plane_pixel(v,0,x,y);
    unsigned b=vdp_plane_pixel(v,1,x,y),s=sprites[y*v->frame_width+x],ink=0;
    if(s&15)ink=s;
    if((b&128) && (b&15))ink=b;
    if((a&128) && (a&15))ink=a;
    if((s&128) && (s&15))ink=s;
#ifdef GENESIS_RINGS_MENU_FONT
    unsigned text=v->font_mask[y*v->frame_width+x];
    if(!ink && (text&2) && (b&15))ink=b;
    if(!ink && (text&1) && (a&15))ink=a;
#endif
    return ink&63;
}
/* Wide coordinates map to the same live ink used by the native renderer. */
static unsigned rings_wide_interface(const CPU *c,const uint8_t *sprites,unsigned x,unsigned y) {
    const VDP *v=&c->vdp;
    if(v->wide_hud_active) {
        unsigned ink=rings_hud_paper(sprites,(int)x,(int)y);
        for(unsigned i=0;i<4;++i) {
            const RingsHudRegion *r=&rings_hud_regions[i];
            if(rings_hud_contains((int)x,(int)y,r->x,r->y,r->w,r->h)) {
                unsigned value=rings_wide_ui_pixel(v,sprites,x-r->x+r->sx,y-r->y+r->sy);
                if(value)ink=value;
            }
        }
        /* Preserve the entire compass, including N, at 80% of its native size.
           Its brown/black plane-B ink is separate from the old pink backdrop
           and from the diamond frame that intersects the source's upper left.
           The live direction indicator is a sprite; move it with the same
           source coordinates and scale, including pixels outside the B mask. */
        if(rings_hud_contains((int)x,(int)y,RINGS_HUD_COMPASS_X,RINGS_HUD_COMPASS_Y,
                              RINGS_HUD_COMPASS_WIDTH,RINGS_HUD_COMPASS_HEIGHT)) {
            unsigned sx=160+(x-RINGS_HUD_COMPASS_X)*80/RINGS_HUD_COMPASS_WIDTH;
            unsigned sy=160+(y-RINGS_HUD_COMPASS_Y)*56/RINGS_HUD_COMPASS_HEIGHT;
            unsigned b=vdp_plane_pixel(v,1,sx,sy);
            if((int)sy>=192-((int)sx-160)*4/7 && (sy<212 || sx<232) &&
               (b&15) && (b&63)!=28)ink=b&63;
            unsigned s=sprites[sy*v->frame_width+sx];
            if(s&15)ink=s&63;
        }
        if(ink)return ink;
    }
    if(x<40 || x>=360)return 0;
    unsigned gx=x-40;
    if(v->wide_hud_active && rings_hud_zone((int)gx,(int)y)>=0)return 0;
    int menu=rings_scene_word(c,0xac)!=0;
    if(menu && rings_hud_zone((int)gx,(int)y)==2)return 0;
    if((v->wide_hud_active || menu) &&
       rings_hud_contains((int)gx,(int)y,160,160,80,56))return 0;
    unsigned zone=(unsigned)rings_hud_zone((int)gx,(int)y);
    if(menu && zone<2) {
        /* The native footer glyphs survive behind Start's sprite parchment.
           Suppress only font tiles, keeping the menu paper and borders intact. */
        unsigned entry=vdp_word(v,0x1000+((y/8)*64+gx/8)*2);
        unsigned anchor=vdp_word(v,0x1000+(20*64+6)*2);
        unsigned base=(anchor&0x7ff)-('G'-32),tile=entry&0x7ff;
        if((anchor&0x8000) && rings_hud_label(v,anchor-('G'-32),48,160,"Gold") &&
           tile>=base && tile<base+96) {
            unsigned b=vdp_plane_pixel(v,1,gx,y),sprite=sprites[y*v->frame_width+gx],ink=0;
            if(sprite&15)ink=sprite;
            if((b&128) && (b&15))ink=b;
            if((sprite&128) && (sprite&15))ink=sprite;
            return ink&63;
        }
    }
    return rings_wide_ui_pixel(v,sprites,gx,y);
}
static void rings_wide_compose(CPU *c,const uint8_t *sprites,const uint8_t *base,uint8_t *out) {
    VDP *v=&c->vdp;RingsWide *w=c->wide;
    unsigned width=v->frame_width,height=v->frame_height,offset=(RINGS_WIDE_WIDTH-width)/2;
    int visible=rings_wide_visible(c) && w->zoom_valid;v->wide_world_visible=(uint8_t)visible;
    /* Native menus reuse the footer tiles for their parchment. Relocating
       those tiles cuts holes in the menu and duplicates its paper as a HUD. */
    v->wide_hud_active=(uint8_t)(visible && !rings_scene_word(c,0xac) && rings_hud_layout(v));
    unsigned backdrop=v->cram[v->registers[7]&63];
    uint8_t background[3]={vdp_channel((backdrop>>1)&7,1),vdp_channel((backdrop>>5)&7,1),vdp_channel((backdrop>>9)&7,1)};
    for(unsigned y=0;y<height;++y)for(unsigned x=0;x<RINGS_WIDE_WIDTH;++x) {
        uint8_t *pixel=out+(y*RINGS_WIDE_WIDTH+x)*3;
        int central=x>=offset && x<offset+width;
        unsigned gx=central ? x-offset:0;
        if(!visible) {memcpy(pixel,central ? base+(y*width+gx)*3:background,3);continue;}
        unsigned ink=w->zoom_scene[(y+RINGS_ZOOM_TOP)*RINGS_ZOOM_WIDTH+x+RINGS_ZOOM_LEFT-16];
        unsigned ui=rings_wide_interface(c,sprites,x,y);
        if(ui)ink=ui;
        if(!ink) {memcpy(pixel,background,3);continue;}
        unsigned rgb=v->cram[ink];
        pixel[0]=vdp_channel((rgb>>1)&7,1);pixel[1]=vdp_channel((rgb>>5)&7,1);pixel[2]=vdp_channel((rgb>>9)&7,1);
    }
}
#endif
#endif
