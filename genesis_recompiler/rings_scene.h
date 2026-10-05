/* Rings presentation policy; reads original scene state without bus effects. */
#ifndef GENESIS_RINGS_SCENE_H
#define GENESIS_RINGS_SCENE_H
#ifdef GENESIS_RINGS_WIDE
static unsigned rings_scene_word(const CPU *c,unsigned at) {
    return ((unsigned)c->ram[at&65535]<<8)|c->ram[(at+1)&65535];
}
#ifdef GENESIS_RINGS_SMOOTH_CAMERA
static uint64_t rings_scene_identity(const CPU *c) {
    unsigned context=((rings_scene_word(c,0xa7fc)<<16)|rings_scene_word(c,0xa7fe))&0xffffff;
    /* Room descriptors are reused at the same RAM address. $0E98 holds the
       fixed scene ID selected by $01DC14, so equally sized rooms still snap. */
    unsigned fields[6]={context,rings_scene_word(c,context),rings_scene_word(c,context+2),
        rings_scene_word(c,context+12),rings_scene_word(c,0xae),rings_scene_word(c,0xe98)};
    uint64_t identity=UINT64_C(14695981039346656037);
    for(unsigned i=0;i<6;++i)identity=(identity^fields[i])*UINT64_C(1099511628211);
    return identity;
}
#endif
static int rings_scene_native(const CPU *c) {
    /* Fixed-map setup at $01DC1C selects mode 2 (rooms/combat);
       $01DE6A restores ordinary exploration. */
    if(rings_scene_word(c,0xae)==2)return 1;
    unsigned context=((rings_scene_word(c,0xa7fc)<<16)|rings_scene_word(c,0xa7fe))&0xffffff;
    /* The active map descriptor lives in mirrored work RAM. Type zero is
       a fixed room; an absent/invalid descriptor is not a room indication. */
    return context>=0xe00000 && !(context&1) && !rings_scene_word(c,context+12);
}
static void rings_scene_discard(CPU *c) {
    if(!c->wide || c->wide->replaying)return;
    c->wide->valid=0;c->wide->pending=0;
    c->wide->zoom_valid=0;c->wide->zoom_pending=0;
#ifdef GENESIS_RINGS_SMOOTH_CAMERA
    c->wide->camera.valid=0;c->wide->camera_work.valid=0;
    c->wide->native.valid=0;c->wide->native_pending=0;
#endif
}
static void rings_scene_snapshot(CPU *c) {
    VDP *v=&c->vdp;
    /* Frozen with the video frame; wide_enabled and zoom_enabled remain
       user preferences and are automatically resumed outside fixed scenes. */
    v->native_scene=(uint8_t)rings_scene_native(c);
#ifdef GENESIS_RINGS_SMOOTH_CAMERA
    v->native_motion.valid=0;
#endif
    if(!v->native_scene)return;
    v->wide_world_visible=0;v->zoom_world_visible=0;v->wide_hud_active=0;
#ifdef GENESIS_RINGS_SMOOTH_CAMERA
    /* Retain only a completed native bitmap's motion records. The outdoor
       camera and extended caches must still be discarded on entry. */
    v->camera.valid=0;
    if(c->wide && !c->wide->replaying && c->wide->native.valid &&
       c->wide->native.camera.identity==rings_scene_identity(c)) {
        v->native_motion=c->wide->native;v->camera=v->native_motion.camera;
    }
#endif
    if(c->wide && !c->wide->replaying) {
        c->wide->valid=c->wide->pending=c->wide->zoom_valid=c->wide->zoom_pending=0;
    }
}
#endif
#endif
