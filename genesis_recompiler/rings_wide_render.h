/* A presentation traversal of statically translated drawing code on a CPU
   copy. The live game's registers, work RAM, devices and clocks are untouched. */
#ifndef GENESIS_RINGS_WIDE_RENDER_H
#define GENESIS_RINGS_WIDE_RENDER_H
#ifdef GENESIS_RINGS_WIDE
static int rings_wide_rom(CPU *c,unsigned at,unsigned *byte) {
    if(at>=0x100000)return 0;
    *byte=read_mem(c,at,1);return !c->fault;
}
static uint8_t rings_resource_lift(int distance,unsigned row,int column,int terrain) {
    if(terrain && column>=0 && column<28) {
        int edge=7+(column<14 ? 13-column:column-14)/2;
        if((int)row<edge)distance+=edge-(int)row;
    }
    return (uint8_t)(distance<0 ? 0:distance>255 ? 255:distance);
}
#ifdef GENESIS_RINGS_SMOOTH_CAMERA
static void rings_hero_begin(RingsWide *w,int x,int y,unsigned sprite) {
    RingsHeroLayer *h=&w->hero_work;
    int left=(x&~1)-10+RINGS_ZOOM_LEFT-64,top=y+13+RINGS_ZOOM_TOP-96;
    memset(h,0,sizeof *h);
    if(left<0 || top<0 || left+128>RINGS_ZOOM_WIDTH || top+128>RINGS_ZOOM_HEIGHT)return;
    h->x=(uint16_t)left;h->y=(uint16_t)top;h->sprite=(uint16_t)sprite;h->valid=1;
    for(unsigned row=0;row<128;++row) {
        memcpy(h->under+row*128,w->zoom_work+(top+row)*RINGS_ZOOM_WIDTH+left,128);
        if(w->grid==10 || w->grid==32)for(unsigned x=0;x<128;++x)
            h->under_lift[row*128+x]=w->lift_work[(top+row)*RINGS_ZOOM_WIDTH+left+x];
    }
}
static void rings_hero_write(RingsWide *w,unsigned x,unsigned y,unsigned ink,unsigned lift) {
    RingsHeroLayer *h=&w->hero_work;
    if(!h->valid || x<h->x || x>=h->x+128u || y<h->y || y>=h->y+128u)return;
    unsigned p=(y-h->y)*128+x-h->x;
    if(w->tracking_player) {h->cover[p]=0;h->ink[p]=(uint8_t)ink;h->ground_y=(uint16_t)w->resource_ground;}
    else {h->under[p]=(uint8_t)ink;h->under_lift[p]=(int16_t)lift;h->cover[p]=1;}
}
#endif
/* Each resource row has a byte-count/left-skip header and packed 4bpp pixels.
   Zero nibbles are transparent; the mirrored writer reverses bytes/nibbles. */
static int rings_wide_resource(CPU *c,uint8_t *out,unsigned width,unsigned height,
                               unsigned id,int x,int y,int flipped,int shift) {
    if(id>=944 || !width || !height)return 0;
    unsigned at=0,byte;
    for(unsigned i=0;i<4;++i) {
        if(!rings_wide_rom(c,0x5f524+id*4+i,&byte))return 0;
        at=(at<<8)|byte;
    }
    if(at>0x100000-0x603e4)return 0;
    at+=0x603e4;
    RingsWide *w=c->wide;
    uint8_t *lift=w && w->replaying && (w->grid==10 || w->grid==32) && out==w->zoom_work ? w->lift_work:NULL;
    int native=w && w->replaying && w->grid==10 && out==w->zoom_work;
    int min_x=native ? RINGS_ZOOM_LEFT+40:0,max_x=native ? RINGS_ZOOM_LEFT+40+288:(int)width;
    int min_y=native ? RINGS_ZOOM_TOP:0,max_y=native ? RINGS_ZOOM_TOP+184:(int)height;
    x=(int16_t)((uint16_t)x&0xfffe); /* Original packed-pixel alignment. */
    if(y-min_y<-21)return 1; /* The verified original writer's top rejection. */
    for(unsigned row=0;row<64;++row,++y) {
        unsigned header;
        if(!rings_wide_rom(c,at++,&header))return 0;
        if(!header)return 1;
        unsigned count=header>>4,skip=header&15;
        int left=x+(flipped ? -38-(int)skip*2:-64+(int)skip*2)+shift;
        for(unsigned i=0;i<count;++i) {
            if(!rings_wide_rom(c,at++,&byte))return 0;
            int xx=left+(flipped ? -(int)i*2:(int)i*2);
            unsigned hi=flipped ? byte&15:byte>>4,lo=flipped ? byte>>4:byte&15;
            if(y>=min_y && y<max_y) {
                int distance=lift ? w->resource_ground-(w->resource_actor==1 ? y:0):0;
                if(xx>=min_x && xx<max_x && hi) {
                    unsigned p=(unsigned)y*width+(unsigned)xx;out[p]=(uint8_t)hi;
                    uint8_t elevation=lift ? rings_resource_lift(distance,row,xx-(x+shift-64),w->resource_actor==2):0;
                    if(lift)lift[p]=elevation;
#ifdef GENESIS_RINGS_SMOOTH_CAMERA
                    if(w && w->replaying && (w->grid==10 || w->grid>=32) && out==w->zoom_work)
                        rings_hero_write(w,(unsigned)xx,(unsigned)y,hi,elevation);
#endif
                }
                if(xx+1>=min_x && xx+1<max_x && lo) {
                    unsigned p=(unsigned)y*width+(unsigned)(xx+1);out[p]=(uint8_t)lo;
                    uint8_t elevation=lift ? rings_resource_lift(distance,row,xx+1-(x+shift-64),w->resource_actor==2):0;
                    if(lift)lift[p]=elevation;
#ifdef GENESIS_RINGS_SMOOTH_CAMERA
                    if(w && w->replaying && (w->grid==10 || w->grid>=32) && out==w->zoom_work)
                        rings_hero_write(w,(unsigned)xx+1,(unsigned)y,lo,elevation);
#endif
                }
            }
        }
    }
    return 0;
}
static int rings_wide_open(CPU *c,RingsWide *w) {
    w->shadow=calloc(1,sizeof(CPU));
    if(!w->shadow)return 0;
    c->wide=w;c->vdp.wide_enabled=1;return 1;
}
static void rings_wide_close(CPU *c) {
    if(c->wide) {free(c->wide->shadow);c->wide->shadow=NULL;}
}
static int rings_wide_replay(CPU *source,unsigned grid) {
    int native=grid==10;
    RingsWide *w=source->wide;
    if(!w || !w->shadow || (grid!=10 && grid!=14 && grid!=32 && grid!=80))return 0;
    CPU *c=w->shadow;memcpy(c,source,sizeof *c);
    c->audio_mode=AUDIO_STUB;
#ifdef GENESIS_RINGS_MENU_FONT
    c->vdp.font_enabled=0;
#endif
    uint8_t *work=native || grid>=32 ? w->zoom_work:w->work;
    unsigned width=native || grid>=32 ? RINGS_ZOOM_WIDTH:grid==14 ? RINGS_WIDE_FIELD:288;
    unsigned height=native || grid>=32 ? RINGS_ZOOM_HEIGHT:grid==14 ? RINGS_SCENE_HEIGHT:RINGS_WIDE_HEIGHT;
    int top=native || grid>=32 ? RINGS_ZOOM_TOP:grid==14 ? RINGS_SCENE_TOP:0;
    int shift=native || grid>=32 ? 40+RINGS_ZOOM_LEFT:grid==14 ? 40:0;
    memset(work,0,(size_t)width*height);w->replaying=1;w->grid=(uint8_t)grid;
    if(native || grid==32)memset(w->lift_work,0,sizeof w->lift_work);
#ifdef GENESIS_RINGS_SMOOTH_CAMERA
    w->tracking_player=0;
    if(native || grid>=32)memset(&w->hero_work,0,sizeof w->hero_work);
    unsigned actor=rings_scene_word(source,0x2b2);
    unsigned sprite=actor<56 ? rings_scene_word(source,0x2b4+actor*52+4):56;
    /* Fixed rooms draw the party directly through sprite zero; the outdoor
       actor record deliberately has no sprite assigned in this mode. */
    if(sprite>=56 && rings_scene_room(source))sprite=0;
#endif
    w->tracking_hero=0;w->work_focus_x=184;w->work_focus_y=RINGS_SCENE_TOP+96;
    unsigned steps=0,budget=grid==80 ? 12500000:2000000;uint64_t submissions=0;
    while(!c->fault && steps++<budget && c->pc!=0x1b9e8 && c->pc!=0x1b94c) {
        if(c->pc==0x231d8)w->tracking_hero=(read_mem(c,c->a[7]+4,4)&0xffffff)==0xffb0cc;
#ifdef GENESIS_RINGS_SMOOTH_CAMERA
        if(c->pc==0x231d8 || c->pc==0x2343a)w->tracking_player=sprite<56 &&
            (read_mem(c,c->a[7]+4,4)&0xffffff)==0xffb0cc+sprite*12;
        if(c->pc==0x232aa || c->pc==0x23626)w->tracking_player=0;
        if((native || grid>=32) && w->tracking_player && (c->pc==0x2320c || c->pc==0x2348a)) {
            /* Both ordinary animated sprites and the party icon use the same
               pose table. Capture before shadows, equipment and status icons. */
            int x=(int16_t)read_mem(c,c->a[6]+12,2)+(int16_t)read_mem(c,c->a[3]+4,2);
            int y=(int16_t)read_mem(c,c->a[6]+14,2)+(int16_t)read_mem(c,c->a[6]+16,2)+
                  (int16_t)read_mem(c,c->a[3]+6,2);
            if((native && rings_scene_room(source)) || (x>=144 && x<=248 && y>=35 && y<=130))
                rings_hero_begin(w,x,y-(c->pc==0x2348a ? 13:0),sprite);
        }
#endif
        if(c->pc==0x232aa)w->tracking_hero=0;
        if((native || grid>=32) && c->pc==0x1baea)
            w->tile_ground_y=(int16_t)read_mem(c,c->a[6]-12,2);
        if(c->pc==0x1386a) {
            /* Presentation traversal does not wait for the live console IRQ. */
            c->d[0]&=0xffff0000;logic_flags(c,0,2);c->pc=pop32(c)&0xffffff;continue;
        }
        if(c->pc==0xe358) {
            unsigned id=read_mem(c,c->a[7]+4,2);
            int x=(int16_t)read_mem(c,c->a[7]+6,2),y=(int16_t)read_mem(c,c->a[7]+8,2);
            int flipped=!!read_mem(c,c->a[7]+10,2);
            unsigned caller=read_mem(c,c->a[7],4)&0xffffff;
            /* Terrain is lowered by seven pixels per height level. Actors
               stand on this tile's ground and can rise above its footprint.
               Record ownership at every opaque write, including flat ground
               that subsequently covers an earlier elevated object. */
            w->resource_actor=(uint8_t)((caller!=0x1bc20 && caller!=0x1bc42 && caller!=0x1bc8a) ? 1:2);
            w->resource_ground=w->resource_actor==1 ? w->tile_ground_y+top+20:w->tile_ground_y-y;
            /* The primary hero's shadow has bounds x=0..27, y=7..19 in
               the verified resource. Keep its ground anchor fixed by zoom. */
            if(grid>=14 && w->tracking_hero && id==0x209 && !flipped &&
               x>=144 && x<=248 && y>=35 && y<=115) {
                w->work_focus_x=(uint16_t)((x&~1)-10);
                w->work_focus_y=(uint16_t)(y+13+RINGS_SCENE_TOP);
            }
            if(c->fault || !rings_wide_resource(c,work,width,height,id,x,y+top,flipped,shift))break;
            ++submissions;c->pc=pop32(c)&0xffffff;continue;
        }
        if(grid>=14) {
            /* Expand the terrain traversal symmetrically around the camera.
               These modifications apply only to the disposable CPU copy. */
            if(c->pc==0x1ba6e)c->d[7]=(c->d[7]&0xffff0000)|(uint16_t)(c->d[7]-(grid-10)/2);
            if(c->pc==0x1ba78)c->a[3]-=(grid-10)/2;
            if(c->pc==0x1bb1e) {arithmetic(c,c->d[4],grid-1,2,1,1);c->pc=0x1bb22;continue;}
            if(c->pc==0x1bb24) {arithmetic(c,c->d[5],grid-1,2,1,1);c->pc=0x1bb28;continue;}
            if(c->pc==0x1c0c4) {arithmetic(c,c->d[5],grid,2,1,1);c->pc=0x1c0c8;continue;}
            if(c->pc==0x1c0ce) {arithmetic(c,c->d[4],grid,2,1,1);c->pc=0x1c0d2;continue;}
        }
        c->instruction_cycles=0;translated_step(c);
    }
    w->replaying=0;w->tracking_hero=0;
    if(native && !c->fault && c->pc==0x1b9e8) {
        for(unsigned y=0;y<184;++y) {
            unsigned at=(y+RINGS_ZOOM_TOP)*RINGS_ZOOM_WIDTH+RINGS_ZOOM_LEFT+40;
            memcpy(w->native_work+y*288,w->zoom_work+at,288);
            memcpy(w->native_lift_work+y*288,w->lift_work+at,288);
        }
#ifdef GENESIS_RINGS_SMOOTH_CAMERA
        w->native_hero_work=w->hero_work;
#endif
    }
    if(c->fault || c->pc!=0x1b9e8) {++w->failures;return 0;}
    w->submissions+=submissions;return 1;
}
#ifdef GENESIS_RINGS_SMOOTH_CAMERA
static unsigned rings_camera_ram_word(const CPU *c,unsigned at) {
    return ((unsigned)c->ram[at&65535]<<8)|c->ram[(at+1)&65535];
}
static RingsCameraSnapshot rings_camera_capture(const CPU *c) {
    RingsCameraSnapshot m={0};
    unsigned context=(rings_camera_ram_word(c,0xa7fc)<<16)|rings_camera_ram_word(c,0xa7fe);
    context&=0xffffff;
    if(context<0xe00000)return m;
    unsigned kind=rings_camera_ram_word(c,context+12);
    /* A fixed map-data origin does not imply a fixed camera. Larger rooms
       still scroll through these coordinates; small rooms leave them fixed. */
    if(!kind && !rings_scene_room(c))return m;
    int x=(int16_t)rings_camera_ram_word(c,0xe8e),y=(int16_t)rings_camera_ram_word(c,0xe90);
    m.x=14*(x-y);m.y=8*(x+y);m.valid=1;
    m.identity=rings_scene_identity(c);
    return m;
}
#endif
static void rings_native_commit(CPU *c) {
    RingsWide *w=c->wide;
    if(w->native_pending) {
        memcpy(w->native_scene,w->native_work,sizeof w->native_scene);
        memcpy(w->native_lift_scene,w->native_lift_work,sizeof w->native_lift_scene);
        w->native_valid=1;w->native_pending=0;
#ifdef GENESIS_RINGS_SMOOTH_CAMERA
        w->native_hero=w->native_hero_work;
#endif
    }
}
/* Publish only a completed replay from the live drawing boundary. This does
   not skip original drawing, advance gameplay, or predict a movement. */
static void rings_wide_commit(CPU *c) {
    RingsWide *w=c->wide;
    if(!w || !w->pending)return;
    memcpy(w->scene,w->work,sizeof w->scene);w->pending=0;w->valid=1;
    if(w->zoom_pending) {
        memcpy(w->zoom_scene,w->zoom_work,sizeof w->zoom_scene);w->zoom_pending=0;w->zoom_valid=1;
        if(!c->vdp.wide_enabled)memcpy(w->lift_scene,w->lift_work,sizeof w->lift_scene);
#ifdef GENESIS_RINGS_SMOOTH_CAMERA
        w->hero=w->hero_work;
#endif
    }
    rings_native_commit(c);
    w->bank=(uint16_t)(((unsigned)c->ram[0x8674]<<8)|c->ram[0x8675]);
    w->focus_x=w->work_focus_x;w->focus_y=w->work_focus_y;
    w->identity=w->identity_work;++w->scenes;
#ifdef GENESIS_RINGS_SMOOTH_CAMERA
    w->camera=w->camera_work;w->camera.generation=w->scenes;w->camera.clocks=c->master_cycles;
#endif
}
static int rings_wide_early_ready(const CPU *c) {
    const RingsWide *w=c->wide;
    /* Initial scenes, room/dialogue transitions and a changed tile bank still
       wait for the native upload. A stable outdoor scene already has its UI,
       palette and aperture, so its completed replay can be shown next VBlank. */
    return w && w->pending && w->zoom_pending && w->valid && w->zoom_valid &&
        c->vdp.zoom_world_visible && w->identity && w->identity==w->identity_work &&
        w->bank==rings_scene_word(c,0x8674) &&
        !rings_scene_word(c,0xac) && !rings_scene_word(c,0x110) && !rings_scene_word(c,0x112);
}
static void rings_wide_observe(CPU *c) {
    RingsWide *w=c->wide;
    if(!w || w->replaying)return;
    /* Only the redraw/upload boundaries need the live map classification.
       VDP snapshots handle changes between them; keep the CPU hot path small. */
    if(c->pc!=0x1b950 && c->pc!=0x1b9ee)return;
    if(!c->vdp.wide_enabled && !c->vdp.zoom_enabled) {rings_scene_discard(c);return;}
    if(rings_scene_native(c)) {
        w->valid=w->pending=w->zoom_valid=w->zoom_pending=0;
        if(!rings_scene_room(c)) {rings_scene_discard(c);return;}
#ifdef GENESIS_RINGS_SMOOTH_CAMERA
        if(c->pc==0x1b950 && (c->ram[0x98] || c->ram[0x99])) {
            w->identity_work=rings_scene_identity(c);w->camera_work=rings_camera_capture(c);
            w->native_pending=(uint8_t)rings_wide_replay(c,10);
            if(!w->native_pending)w->native_valid=0;
        }
        /* Rooms retain the native cadence: publish after the real upload.
           No extended traversal, prediction, or early gameplay step is used. */
        if(c->pc==0x1b9ee && w->native_pending) {
            rings_native_commit(c);w->identity=w->identity_work;++w->scenes;
            w->bank=(uint16_t)rings_scene_word(c,0x8674);
            w->camera=w->camera_work;w->camera.generation=w->scenes;w->camera.clocks=c->master_cycles;
        }
#else
        rings_scene_discard(c);
#endif
        return;
    }
    if(c->pc==0x1b950 && (c->ram[0x98] || c->ram[0x99])) {
        w->identity_work=rings_scene_identity(c);
#ifdef GENESIS_RINGS_SMOOTH_CAMERA
        w->camera_work=rings_camera_capture(c);
#endif
        w->native_pending=(uint8_t)(!c->vdp.wide_enabled && rings_wide_replay(c,10));
        if(!w->native_pending)w->native_valid=0;
        w->pending=(uint8_t)rings_wide_replay(c,14);
        if(!w->pending)w->valid=0;
        w->zoom_pending=(uint8_t)(w->pending && (c->vdp.zoom_enabled || c->vdp.wide_enabled) &&
                                 rings_wide_replay(c,c->vdp.wide_enabled ? 80:32));
        if(!w->zoom_pending)w->zoom_valid=0;
    }
    if(c->pc==0x1b9ee || rings_wide_early_ready(c))rings_wide_commit(c);
}
#endif
#endif
