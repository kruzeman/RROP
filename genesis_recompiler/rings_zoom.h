/* Immutable world/UI layers for presentation-only viewport zoom. */
#ifndef GENESIS_RINGS_ZOOM_H
#define GENESIS_RINGS_ZOOM_H
#ifdef GENESIS_RINGS_WIDE
static unsigned rings_view_width(const VDP *v) {
    return rings_view_wide(v) ? RINGS_WIDE_WIDTH:v->frame_width;
}
static const uint8_t *rings_view_pixels(const VDP *v,int external_font) {
#ifdef GENESIS_RINGS_MENU_FONT
    if(external_font && v->font_count)return rings_view_wide(v) ? v->wide_font_frame:v->font_frame;
#else
    (void)external_font;
#endif
    return rings_view_wide(v) ? v->wide_frame:v->frame;
}
static void rings_zoom_prepare(CPU *c,const uint8_t *sprites) {
    VDP *v=&c->vdp;const RingsWide *w=c->wide;
    unsigned width=rings_view_width(v),height=v->frame_height,offset=(width-v->frame_width)/2;
    memset(v->zoom_mask,0,sizeof v->zoom_mask);
    memset(v->zoom_restore,0,sizeof v->zoom_restore);
    v->zoom_world_visible=(uint8_t)(rings_wide_visible(c) && w->zoom_valid);
#ifdef GENESIS_RINGS_SMOOTH_CAMERA
    if(v->zoom_world_visible)v->camera=w->camera;else v->camera.valid=0;
#endif
    if(!v->zoom_world_visible)return;
    memcpy(v->zoom_scene,w->zoom_scene,sizeof v->zoom_scene);
    memcpy(v->zoom_lift,w->lift_scene,sizeof v->zoom_lift);
    v->zoom_focus_x=(w->focus_x ? w->focus_x:184)+RINGS_ZOOM_LEFT;
    v->zoom_focus_y=(w->focus_y ? w->focus_y:RINGS_SCENE_TOP+96)+RINGS_ZOOM_TOP-RINGS_SCENE_TOP;
    for(unsigned i=0;i<16;++i) {
        unsigned rgb=v->cram[i];
        v->zoom_palette[i*3]=vdp_channel((rgb>>1)&7,1);
        v->zoom_palette[i*3+1]=vdp_channel((rgb>>5)&7,1);
        v->zoom_palette[i*3+2]=vdp_channel((rgb>>9)&7,1);
    }
    for(unsigned y=0;y<(rings_view_wide(v) ? height:RINGS_WIDE_HEIGHT) && y<height;++y)for(unsigned x=0;x<width;++x) {
        int central=x>=offset && x<offset+v->frame_width;
        unsigned gx=central ? x-offset:0;
        /* World tile slots identify what must be restored before scaling.
           Native clipping follows the transparent opening in plane B,
           independently of terrain/actor silhouettes in the original frame. */
        if(rings_view_wide(v)) {
#ifdef GENESIS_RINGS_MENU_FONT
            v->font_hide=(uint8_t)!!v->font_count;
#endif
            unsigned ui=rings_wide_interface(v,sprites,x,y);
#ifdef GENESIS_RINGS_MENU_FONT
            v->font_hide=0;
#endif
            if(ui)continue;
        } else {
            if(gx<16 || gx>=304 || !vdp_window_at(v,gx,y))continue;
            unsigned at=0x1000+((y/8)*64+gx/8)*2;
            if(vdp_word(v,at)!=w->bank+(y/8)*36+gx/8-2)continue;
        }
        if(!rings_view_wide(v) && central && rings_world_foreground(v,sprites,gx,y))continue;
#ifdef GENESIS_RINGS_MENU_FONT
        if(!rings_view_wide(v) && central && v->font_count && v->font_mask[y*v->frame_width+gx])continue;
#endif
        unsigned pixel=y*width+x;
        v->zoom_restore[pixel]=1;
        unsigned b=central && !rings_view_wide(v) ? vdp_plane_pixel(v,1,gx,y):0;
        v->zoom_mask[pixel]=(uint8_t)(rings_view_wide(v) || !(b&15));
        unsigned rgb=v->cram[(b&15) ? b&63:v->registers[7]&63];
        v->zoom_background[pixel*3]=vdp_channel((rgb>>1)&7,1);
        v->zoom_background[pixel*3+1]=vdp_channel((rgb>>5)&7,1);
        v->zoom_background[pixel*3+2]=vdp_channel((rgb>>9)&7,1);
    }
}
static int rings_zoom_sample(int pixel,int source_anchor,int target_anchor,unsigned percent) {
    int numerator=(2*(pixel-target_anchor)+1)*50;
    int distance=numerator>=0 ? numerator/(int)percent:-((-numerator+(int)percent-1)/(int)percent);
    return source_anchor+distance;
}
static int rings_zoom_project(int pixel,int anchor,unsigned percent) {
    int n=(2*(pixel-anchor)+1)*(int)percent;
    return n>=0 ? n/200:-((-n+199)/200);
}
/* Only an elevated pixel whose ground projection lies in the aperture may
   spill over its upper edge. Use the frozen ground mask at the current scale;
   the old 100% silhouettes never determine the new object's outline. */
static int rings_zoom_spill_shift(const VDP *v,int sx,int sy,unsigned percent,int shift_x,int shift_y) {
    if(rings_view_wide(v) || sx<0 || sx>=RINGS_ZOOM_WIDTH || sy<0 || sy>=RINGS_ZOOM_HEIGHT)return 0;
    unsigned p=(unsigned)sy*RINGS_ZOOM_WIDTH+(unsigned)sx;
    if(!v->zoom_lift[p] || !v->zoom_scene[p])return 0;
    int target_x=(int)v->zoom_focus_x-RINGS_ZOOM_LEFT-24;
    int target_y=(int)v->zoom_focus_y-RINGS_ZOOM_TOP;
    int gx=target_x+rings_zoom_project(sx,v->zoom_focus_x,percent)+shift_x;
    int gy=target_y+rings_zoom_project(sy+v->zoom_lift[p],v->zoom_focus_y,percent)+shift_y;
    return gx>=0 && gx<(int)v->frame_width && gy>=0 && gy<(int)v->frame_height &&
           v->zoom_mask[(unsigned)gy*v->frame_width+(unsigned)gx];
}
static int rings_zoom_spill(const VDP *v,int sx,int sy,unsigned percent) {
    return rings_zoom_spill_shift(v,sx,sy,percent,0,0);
}
static void rings_zoom_pixels(const VDP *v,unsigned percent,int external_font,uint8_t *out) {
    unsigned width=rings_view_width(v),height=v->frame_height;
    memcpy(out,rings_view_pixels(v,external_font),(size_t)width*height*3);
    if(!v->zoom_enabled || !v->zoom_world_visible || percent==100)return;
    if(percent<50)percent=50;
    if(percent>100)percent=100;
    if(percent==100)return;
    int target_x=(int)v->zoom_focus_x-RINGS_ZOOM_LEFT+16-(rings_view_wide(v) ? 0:40);
    int target_y=(int)v->zoom_focus_y-RINGS_ZOOM_TOP;
    for(unsigned y=0;y<height;++y)for(unsigned x=0;x<width;++x) {
        unsigned pixel=y*width+x;
        if(v->zoom_restore[pixel])memcpy(out+pixel*3,v->zoom_background+pixel*3,3);
        if(!v->zoom_restore[pixel])continue;
        int sx=rings_zoom_sample((int)x,v->zoom_focus_x,target_x,percent);
        int sy=rings_zoom_sample((int)y,v->zoom_focus_y,target_y,percent);
        unsigned ink=0;
        if(sx>=0 && sx<RINGS_ZOOM_WIDTH && sy>=0 && sy<RINGS_ZOOM_HEIGHT)
            ink=v->zoom_scene[(unsigned)sy*RINGS_ZOOM_WIDTH+(unsigned)sx];
        if(!v->zoom_mask[pixel] && !rings_zoom_spill(v,sx,sy,percent))continue;
        memcpy(out+pixel*3,ink ? v->zoom_palette+ink*3:v->zoom_background+pixel*3,3);
    }
}
#endif
#endif
