/* A presentation traversal of statically translated drawing code on a CPU
   copy. The live game's registers, work RAM, devices and clocks are untouched. */
#ifndef GENESIS_RINGS_WIDE_RENDER_H
#define GENESIS_RINGS_WIDE_RENDER_H
#ifdef GENESIS_RINGS_WIDE
static int rings_wide_rom(CPU *c,unsigned at,unsigned *byte) {
    if(at>=0x100000)return 0;
    *byte=read_mem(c,at,1);return !c->fault;
}
/* Each resource row has a byte-count/left-skip header and packed 4bpp pixels.
   Zero nibbles are transparent; the mirrored writer reverses bytes/nibbles. */
static int rings_wide_resource_shifted(CPU *c,uint8_t *out,unsigned width,unsigned height,
                               unsigned id,int x,int y,int flipped,int shift,int dx,int dy) {
    if(id>=944 || !width || !height)return 0;
    unsigned at=0,byte;
    for(unsigned i=0;i<4;++i) {
        if(!rings_wide_rom(c,0x5f524+id*4+i,&byte))return 0;
        at=(at<<8)|byte;
    }
    if(at>0x100000-0x603e4)return 0;
    at+=0x603e4;
    RingsWide *w=c->wide;
    uint8_t *lift=w && w->replaying && w->grid==32 && out==w->zoom_work ? w->lift_work:NULL;
    x=(int16_t)((uint16_t)x&0xfffe); /* Original packed-pixel alignment. */
    if(y<-21)return 1; /* The verified original writer's top rejection. */
    x+=dx;y+=dy;
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
            if(y>=0 && y<(int)height) {
                int distance=lift ? w->resource_ground-(w->resource_actor ? y:0):0;
                uint8_t elevation=(uint8_t)(distance<0 ? 0:distance>255 ? 255:distance);
                if(xx>=0 && xx<(int)width && hi) {
                    unsigned p=(unsigned)y*width+(unsigned)xx;out[p]=(uint8_t)hi;
                    if(lift)lift[p]=elevation;
                }
                if(xx+1>=0 && xx+1<(int)width && lo) {
                    unsigned p=(unsigned)y*width+(unsigned)(xx+1);out[p]=(uint8_t)lo;
                    if(lift)lift[p]=elevation;
                }
            }
        }
    }
    return 0;
}
static int rings_wide_resource(CPU *c,uint8_t *out,unsigned width,unsigned height,
                               unsigned id,int x,int y,int flipped,int shift) {
    return rings_wide_resource_shifted(c,out,width,height,id,x,y,flipped,shift,0,0);
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
    RingsWide *w=source->wide;
    if(!w || !w->shadow || (grid!=10 && grid!=14 && grid!=32 && grid!=80))return 0;
    CPU *c=w->shadow;memcpy(c,source,sizeof *c);
    c->audio_mode=AUDIO_STUB;
#ifdef GENESIS_RINGS_MENU_FONT
    c->vdp.font_enabled=0;
#endif
    uint8_t *work=grid>=32 ? w->zoom_work:w->work;
    unsigned width=grid>=32 ? RINGS_ZOOM_WIDTH:grid==14 ? RINGS_WIDE_FIELD:288;
    unsigned height=grid>=32 ? RINGS_ZOOM_HEIGHT:grid==14 ? RINGS_SCENE_HEIGHT:RINGS_WIDE_HEIGHT;
    int top=grid>=32 ? RINGS_ZOOM_TOP:grid==14 ? RINGS_SCENE_TOP:0;
    int shift=grid>=32 ? 40+RINGS_ZOOM_LEFT:grid==14 ? 40:0;
    memset(work,0,(size_t)width*height);w->replaying=1;w->grid=(uint8_t)grid;
    if(grid==32)memset(w->lift_work,0,sizeof w->lift_work);
    w->tracking_hero=0;w->work_focus_x=184;w->work_focus_y=RINGS_SCENE_TOP+96;
    unsigned steps=0,budget=grid==80 ? 12500000:2000000;uint64_t submissions=0;
    while(!c->fault && steps++<budget && c->pc!=0x1b9e8 && c->pc!=0x1b94c) {
        if(c->pc==0x231d8)w->tracking_hero=(read_mem(c,c->a[7]+4,4)&0xffffff)==0xffb0cc;
        if(c->pc==0x232aa)w->tracking_hero=0;
        if(grid==32 && c->pc==0x1baea)
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
#ifdef GENESIS_RINGS_SMOOTH_CAMERA
            if(grid==10) {
                RingsNativeMotion *m=&w->native_work;
                if(m->count<RINGS_NATIVE_DRAWS) {
                    RingsNativeDraw *d=&m->draw[m->count++];
                    d->id=(uint16_t)id;d->x=(int16_t)x;d->y=(int16_t)y;
                    d->flipped=(uint8_t)flipped;d->hero=w->tracking_hero;
                } else m->overflow=1;
                if(w->tracking_hero && id==0x209 && !flipped) {
                    m->hero_x=(int16_t)(x&~1);m->hero_y=(int16_t)y;m->hero_valid=1;
                }
            }
#endif
            /* Terrain is lowered by seven pixels per height level. Actors
               stand on this tile's ground and can rise above its footprint.
               Record ownership at every opaque write, including flat ground
               that subsequently covers an earlier elevated object. */
            w->resource_actor=(uint8_t)(caller!=0x1bc20 && caller!=0x1bc42 && caller!=0x1bc8a);
            w->resource_ground=w->resource_actor ? w->tile_ground_y+top+20:w->tile_ground_y-y;
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
    if(context<0xe00000 || (context&1))return m;
    unsigned kind=rings_camera_ram_word(c,context+12);
    int x=(int16_t)rings_camera_ram_word(c,0xe8e),y=(int16_t)rings_camera_ram_word(c,0xe90);
    /* $020D58 uses a zero origin for fixed rooms, regardless of the hero's
       coordinates. Scrolling maps, including indoor maps, use this transform. */
    m.x=kind ? 14*(x-y):0;m.y=kind ? 8*(x+y):0;m.valid=1;
    m.identity=rings_scene_identity(c);
    return m;
}
#endif
static void rings_wide_observe(CPU *c) {
    RingsWide *w=c->wide;
    if(!w || w->replaying)return;
    /* Only the redraw/upload boundaries need the live map classification.
       VDP snapshots handle changes between them; keep the CPU hot path small. */
    if(c->pc!=0x1b950 && c->pc!=0x1b9ee)return;
    if(!c->vdp.wide_enabled && !c->vdp.zoom_enabled) {rings_scene_discard(c);return;}
    if(rings_scene_native(c)) {
        w->pending=w->zoom_pending=w->valid=w->zoom_valid=0;
#ifdef GENESIS_RINGS_SMOOTH_CAMERA
        /* Replay precisely the original 10x10 traversal. Never extend a
           room/combat map and wrap its tiles beyond the room's walls. */
        if(c->pc==0x1b950 && (c->ram[0x98] || c->ram[0x99])) {
            memset(&w->native_work,0,sizeof w->native_work);
            w->native_work.camera=rings_camera_capture(c);
            w->native_pending=(uint8_t)rings_wide_replay(c,10);
            if(!w->native_pending)w->native.valid=0;
        }
        if(c->pc==0x1b9ee && w->native_pending) {
            w->native_pending=0;w->native=w->native_work;
            w->native.valid=(uint8_t)(w->native.camera.valid && !w->native.overflow && w->native.count);
            w->native.camera.generation=++w->scenes;w->native.camera.clocks=c->master_cycles;
            w->bank=(uint16_t)(((unsigned)c->ram[0x8674]<<8)|c->ram[0x8675]);
        }
#else
        rings_scene_discard(c);
#endif
        return;
    }
#ifdef GENESIS_RINGS_SMOOTH_CAMERA
    w->native.valid=0;w->native_pending=0;
#endif
    if(c->pc==0x1b950 && (c->ram[0x98] || c->ram[0x99])) {
#ifdef GENESIS_RINGS_SMOOTH_CAMERA
        w->camera_work=rings_camera_capture(c);
#endif
        w->pending=(uint8_t)rings_wide_replay(c,14);
        if(!w->pending)w->valid=0;
        w->zoom_pending=(uint8_t)(w->pending && (c->vdp.zoom_enabled || c->vdp.wide_enabled) &&
                                 rings_wide_replay(c,c->vdp.wide_enabled ? 80:32));
        if(!w->zoom_pending)w->zoom_valid=0;
    }
    if(c->pc==0x1b9ee && w->pending) {
        /* Activate only after the original scene's upload has returned. */
        memcpy(w->scene,w->work,sizeof w->scene);w->pending=0;w->valid=1;
        if(w->zoom_pending) {
            memcpy(w->zoom_scene,w->zoom_work,sizeof w->zoom_scene);w->zoom_pending=0;w->zoom_valid=1;
            if(!c->vdp.wide_enabled)memcpy(w->lift_scene,w->lift_work,sizeof w->lift_scene);
        }
        w->bank=(uint16_t)(((unsigned)c->ram[0x8674]<<8)|c->ram[0x8675]);
        w->focus_x=w->work_focus_x;w->focus_y=w->work_focus_y;
        ++w->scenes;
#ifdef GENESIS_RINGS_SMOOTH_CAMERA
        w->camera=w->camera_work;w->camera.generation=w->scenes;w->camera.clocks=c->master_cycles;
#endif
    }
}
#endif
#endif
