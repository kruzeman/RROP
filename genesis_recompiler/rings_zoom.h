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
#ifdef GENESIS_RINGS_SMOOTH_CAMERA
static int rings_wide_resource_shifted(CPU *c,uint8_t *out,unsigned width,unsigned height,
                                      unsigned id,int x,int y,int flipped,int shift,int dx,int dy);
static int rings_wide_resource_layer(CPU *c,uint8_t *out,unsigned width,unsigned height,
                                    unsigned id,int x,int y,int flipped,int shift,int dx,int dy,
                                    uint8_t *lift,int ground,int actor);
static int rings_hero_pixels(CPU *c,const VDP *v,int dx,int dy,uint8_t *out,uint8_t *lift) {
    if(!c || !c->wide || !c->wide->shadow || !v->hero_patch.valid)return 0;
    CPU *shadow=c->wide->shadow;shadow->fault=0;
    memset(out,0,RINGS_HERO_WIDTH*RINGS_HERO_HEIGHT);
    memset(lift,0,RINGS_HERO_WIDTH*RINGS_HERO_HEIGHT);
    for(unsigned i=0;i<v->hero_patch.count;++i) {
        const RingsNativeDraw *d=&v->hero_patch.draw[i];
        int mx=d->hero ? dx:0,my=d->hero ? dy:0;
        int ground=d->ground+(d->actor ? -RINGS_HERO_TOP+my:0);
        if(!rings_wide_resource_layer(shadow,out,RINGS_HERO_WIDTH,RINGS_HERO_HEIGHT,
                d->id,d->x,d->y+RINGS_ZOOM_TOP,d->flipped,-RINGS_HERO_LEFT,
                mx,-RINGS_ZOOM_TOP-RINGS_HERO_TOP+my,lift,ground,d->actor))return 0;
    }
    return 1;
}
static int rings_native_pixels(CPU *c,const VDP *v,int dx,int dy,uint8_t *out) {
    if(!c->wide || !c->wide->shadow || !v->native_motion.valid)return 0;
    CPU *shadow=c->wide->shadow;
    /* A newer disposable traversal can have failed while this completed
       frame remains visible. Its fault must not poison ROM-only decoding. */
    shadow->fault=0;
    memset(out,0,RINGS_ZOOM_WIDTH*RINGS_ZOOM_HEIGHT);
    for(unsigned i=0;i<v->native_motion.count;++i) {
        const RingsNativeDraw *d=&v->native_motion.draw[i];
        if(!rings_wide_resource_shifted(shadow,out,RINGS_ZOOM_WIDTH,RINGS_ZOOM_HEIGHT,
                d->id,d->x,d->y,d->flipped,RINGS_ZOOM_LEFT+40,
                d->hero ? dx:0,RINGS_ZOOM_TOP+(d->hero ? dy:0)))return 0;
    }
    return 1;
}
#endif
static void rings_zoom_prepare(CPU *c,const uint8_t *sprites) {
    VDP *v=&c->vdp;const RingsWide *w=c->wide;
    unsigned width=rings_view_width(v),height=v->frame_height,offset=(width-v->frame_width)/2;
    memset(v->zoom_mask,0,sizeof v->zoom_mask);
    memset(v->zoom_restore,0,sizeof v->zoom_restore);
    v->zoom_world_visible=(uint8_t)(rings_wide_visible(c) && w->zoom_valid);
    int native=0;
#ifdef GENESIS_RINGS_SMOOTH_CAMERA
    native=v->native_scene && v->native_motion.valid && rings_bitmap_visible(c);
    if(v->zoom_world_visible) {v->camera=w->camera;v->hero_patch=w->hero;}
    else if(!native) {v->camera.valid=0;v->native_motion.valid=0;}
#endif
    if(!v->zoom_world_visible && !native)return;
    if(native) {
#ifdef GENESIS_RINGS_SMOOTH_CAMERA
        if(!rings_native_pixels(c,v,0,0,v->zoom_scene)) {v->native_motion.valid=0;v->camera.valid=0;return;}
#endif
        memset(v->zoom_lift,0,sizeof v->zoom_lift);
        v->zoom_focus_x=184+RINGS_ZOOM_LEFT;v->zoom_focus_y=96+RINGS_ZOOM_TOP;
    } else {
        memcpy(v->zoom_scene,w->zoom_scene,sizeof v->zoom_scene);
        memcpy(v->zoom_lift,w->lift_scene,sizeof v->zoom_lift);
        v->zoom_focus_x=(w->focus_x ? w->focus_x:184)+RINGS_ZOOM_LEFT;
        v->zoom_focus_y=(w->focus_y ? w->focus_y:RINGS_SCENE_TOP+96)+RINGS_ZOOM_TOP-RINGS_SCENE_TOP;
    }
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
static int rings_zoom_spill_layer(const VDP *v,const uint8_t *scene,const uint8_t *lift,
                                 int sx,int sy,unsigned percent,int shift_x,int shift_y) {
    if(rings_view_wide(v) || sx<0 || sx>=RINGS_ZOOM_WIDTH || sy<0 || sy>=RINGS_ZOOM_HEIGHT)return 0;
    unsigned p=(unsigned)sy*RINGS_ZOOM_WIDTH+(unsigned)sx;
    if(!lift[p] || !scene[p])return 0;
    int target_x=(int)v->zoom_focus_x-RINGS_ZOOM_LEFT-24;
    int target_y=(int)v->zoom_focus_y-RINGS_ZOOM_TOP;
    int gx=target_x+rings_zoom_project(sx,v->zoom_focus_x,percent)+shift_x;
    int gy=target_y+rings_zoom_project(sy+lift[p],v->zoom_focus_y,percent)+shift_y;
    return gx>=0 && gx<(int)v->frame_width && gy>=0 && gy<(int)v->frame_height &&
           v->zoom_mask[(unsigned)gy*v->frame_width+(unsigned)gx];
}
static int rings_zoom_spill_shift(const VDP *v,int sx,int sy,unsigned percent,int shift_x,int shift_y) {
    return rings_zoom_spill_layer(v,v->zoom_scene,v->zoom_lift,sx,sy,percent,shift_x,shift_y);
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
