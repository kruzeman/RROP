/* Merge directions only at the native main-game decoder. The interrupt FIFO
   and action-button edges retain their original behavior. */
#ifndef GENESIS_RINGS_PAD_SDL_H
#define GENESIS_RINGS_PAD_SDL_H
#if defined(GENESIS_SDL2) && defined(GENESIS_RINGS_WIDE)
static int rings_pad_game(const SDLHost *h,const CPU *c) {
    int enhanced=c->vdp.wide_enabled || c->vdp.zoom_enabled;
#ifdef GENESIS_RINGS_SAVES
    if(h->settings.ready)enhanced=h->settings.enhanced;
    if(h->settings.menu || (h->saves && h->saves->menu))return 0;
#endif
    return enhanced && h->input.focused && !h->paused && !h->stopped && !c->fault &&
        c->vdp.zoom_world_visible && !rings_scene_native(c) &&
        !rings_scene_word(c,0xac) && !rings_scene_word(c,0x110) &&
        !rings_scene_word(c,0x112) && !rings_scene_word(c,0x128);
}
static void rings_pad_sample(SDLHost *h,const CPU *c,uint8_t buttons) {
    RingsPadIntent *p=&h->pad_intent;
    if(!rings_pad_game(h,c) || (buttons&0xf0)) {
        rings_pad_reset(p);if(c->wide)c->wide->motion.fallback=0;return;
    }
    if(buttons && buttons!=p->previous) {
        /* Keep a short press until one decision, even if SDL delivers press
           and release together after a drawing traversal. Latest intent wins. */
        p->pending=buttons;p->deadline=c->master_cycles+(uint64_t)vdp_master_frequency(&c->vdp)*2;
    }
    p->previous=buttons;
    if(p->pending && c->master_cycles>p->deadline) {p->pending=0;if(c->wide)c->wide->motion.fallback=0;}
}
static void rings_pad_observe(SDLHost *h,CPU *c) {
    if(c->pc!=0x12ff8)return;
    RingsPadIntent *p=&h->pad_intent;
    if(!rings_pad_game(h,c) || (c->pad_buttons[0]&0xf0)) {
        rings_pad_reset(p);return;
    }
    if(c->d[0]&0xf0)return; /* Defer a pure direction tap behind queued native actions. */
    if(p->pending && c->master_cycles>p->deadline)p->pending=0;
    unsigned direction=c->pad_buttons[0]&15u;
    if(!direction)direction=p->pending;
    if(c->wide && c->wide->motion.active && rings_motion_scene(c)) {
        RingsMotion *m=&c->wide->motion;
        if(m->fallback) {direction=m->fallback;m->fallback=0;p->pending=0;}
        else if(direction && rings_motion_direction(direction)>=4)p->pending=0;
        else direction=0; /* The idle boundary consumes cardinal movement intent. */
        c->d[0]=(c->d[0]&~15u)|direction;return;
    }
    p->pending=0;c->d[0]=(c->d[0]&~15u)|direction;
}
#endif
#endif
