/* Boot-time handling of held keyboard keys through the original controller input. */
#ifndef GENESIS_RINGS_STARTUP_SDL_H
#define GENESIS_RINGS_STARTUP_SDL_H
#ifdef GENESIS_RINGS_SAVES
static void rings_startup_cancel(SDLHost *h,CPU *c) {
    if(h->startup_injected)c->pad_buttons[1]=h->startup_previous;
    h->startup_armed=h->startup_injected=h->startup_latched=h->startup_held=0;
}
static void rings_startup_init(SDLHost *h,const CPU *c) {
    /* These instructions identify the verified boot-only logo check. Other
       games, headless execution and loading a save cannot arm the shortcut. */
    static const uint8_t check[]={0xb0,0x7c,0x00,0xfa,0x66,0x06};
    static const uint8_t reader[]={0x4e,0xb9,0x00,0x00,0xdc,0xe2};
    h->startup_held=h->startup_latched=h->startup_injected=0;h->startup_focused=1;
    h->startup_armed=(uint8_t)(c->pc==0x200 && !c->steps && c->rom && c->rom_size==0x100000 &&
        !memcmp(c->rom+0x12434,check,sizeof check) && !memcmp(c->rom+0x12420,reader,sizeof reader));
}
static unsigned rings_startup_key(const SDL_Keysym *key) {
    if(key->scancode==SDL_SCANCODE_N || key->sym==SDLK_n)return 1;
    if(key->scancode==SDL_SCANCODE_U || key->sym==SDLK_u)return 2;
    if(key->scancode==SDL_SCANCODE_D || key->sym==SDLK_d)return 4;
    if(key->scancode==SDL_SCANCODE_E || key->sym==SDLK_e)return 8;
    return 0;
}
static void rings_startup_event(SDLHost *h,const SDL_Event *event) {
    if(!h->startup_armed)return;
    if(event->type==SDL_WINDOWEVENT && event->window.event==SDL_WINDOWEVENT_FOCUS_LOST) {
        h->startup_focused=0;h->startup_held=h->startup_latched=0;return;
    }
    if(event->type==SDL_WINDOWEVENT && event->window.event==SDL_WINDOWEVENT_FOCUS_GAINED)h->startup_focused=1;
    if(event->type!=SDL_KEYDOWN && event->type!=SDL_KEYUP)return;
    unsigned bit=rings_startup_key(&event->key.keysym);
    if(event->type==SDL_KEYUP)h->startup_held&=(uint8_t)~bit;
    else if(h->startup_focused)h->startup_held|=(uint8_t)bit;
    if(h->startup_focused && h->startup_held==15)h->startup_latched=1;
}
static void rings_startup_keyboard(SDLHost *h) {
    if(!h->startup_armed || !h->startup_focused)return;
    /* SDL also reconciles keys already held when the new window gains focus.
       Physical scancodes keep the chord usable with a non-Latin layout. */
    const Uint8 *keys=SDL_GetKeyboardState(NULL);
    if(keys[SDL_SCANCODE_N] && keys[SDL_SCANCODE_U] &&
       keys[SDL_SCANCODE_D] && keys[SDL_SCANCODE_E])h->startup_latched=1;
}
static void rings_startup_observe(SDLHost *h,CPU *c) {
    if(h->startup_armed && c->pc==0x12420) {
        SDL_PumpEvents();rings_startup_keyboard(h);
        h->startup_armed=0;
        if(h->startup_latched) {
            h->startup_previous=c->pad_buttons[1];
            c->pad_buttons[1]=PAD_A|PAD_B|PAD_C|PAD_START|PAD_DOWN|PAD_RIGHT;
            h->startup_injected=1;
        }
        h->startup_latched=h->startup_held=0;
    }
    if(h->startup_injected && c->pc==0x12434) {
        c->pad_buttons[1]=h->startup_previous;h->startup_injected=0;
    }
}
#endif
#endif
