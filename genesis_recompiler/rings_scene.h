/* Rings presentation policy; reads original scene state without bus effects. */
#ifndef GENESIS_RINGS_SCENE_H
#define GENESIS_RINGS_SCENE_H
#ifdef GENESIS_RINGS_WIDE
static unsigned rings_scene_word(const CPU *c,unsigned at) {
    return ((unsigned)c->ram[at&65535]<<8)|c->ram[(at+1)&65535];
}
static unsigned rings_scene_context(const CPU *c) {
    return ((rings_scene_word(c,0xa7fc)<<16)|rings_scene_word(c,0xa7fe))&0xffffff;
}
static int rings_scene_room(const CPU *c) {
    unsigned context=rings_scene_context(c);
    /* Combat uses its own descriptor, although its type is also zero. */
    return context>=0xe00000 && !(context&1) && context!=0xffb0bc &&
           !rings_scene_word(c,context+12);
}
static uint64_t rings_scene_identity(const CPU *c) {
    unsigned context=((rings_scene_word(c,0xa7fc)<<16)|rings_scene_word(c,0xa7fe))&0xffffff;
    if(context<0xe00000 || (context&1))return 0;
    if(!rings_scene_word(c,context+12)) {
        if(!rings_scene_room(c))return 0;
        /* Both room descriptors are reused. Include the fixed room ID and
           dimensions, so equally sized rooms cannot share a stale tween. */
        unsigned fields[]={context,rings_scene_word(c,context),rings_scene_word(c,context+2),
            rings_scene_word(c,0xae),rings_scene_word(c,0xe98)};
        uint64_t identity=UINT64_C(14695981039346656037);
        for(unsigned i=0;i<sizeof fields/sizeof *fields;++i)identity=(identity^fields[i])*UINT64_C(1099511628211);
        return identity;
    }
    return ((uint64_t)context<<32)|((uint64_t)rings_scene_word(c,context)<<16)|rings_scene_word(c,context+2);
}
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
    c->wide->native_valid=0;c->wide->native_pending=0;
    c->wide->identity=0;c->wide->identity_work=0;
#ifdef GENESIS_RINGS_SMOOTH_CAMERA
    c->wide->camera.valid=0;c->wide->camera_work.valid=0;
    c->wide->hero.valid=0;c->wide->hero_work.valid=0;
#endif
}
static void rings_scene_snapshot(CPU *c) {
    VDP *v=&c->vdp;
    /* Frozen with the video frame; wide_enabled and zoom_enabled remain
       user preferences and are automatically resumed outside fixed scenes. */
    v->native_scene=(uint8_t)rings_scene_native(c);
    if(!v->native_scene)return;
    v->wide_world_visible=0;v->zoom_world_visible=0;v->wide_hud_active=0;
#ifdef GENESIS_RINGS_SMOOTH_CAMERA
    v->camera.valid=0;v->hero.valid=0;
#endif
    v->native_world_valid=0;
    RingsWide *w=c->wide;
    if(!w || w->replaying)return;
    w->valid=w->pending=w->zoom_valid=w->zoom_pending=0;
    uint64_t identity=rings_scene_identity(c);
    if(!rings_scene_room(c)) {rings_scene_discard(c);return;}
    if(w->identity!=identity)w->native_valid=0;
    if(w->identity_work!=identity)w->native_pending=0;
}
#endif
#endif
