#ifndef GENESIS_RINGS_MOUSE_SDL_H
#define GENESIS_RINGS_MOUSE_SDL_H
#if defined(GENESIS_SDL2) && defined(GENESIS_RINGS_WIDE)
static int rings_mouse_game(const SDLHost *h,const CPU *c) {
    if(!h->mouse.enabled || h->paused || h->stopped || c->fault ||
       !c->vdp.zoom_world_visible || !rings_hud_layout(&c->vdp))return 0;
#ifdef GENESIS_RINGS_SAVES
    if((h->saves && h->saves->menu) || h->settings.menu)return 0;
#endif
    /* Native dialogue/selection modes also use the direction decoder. */
    return !c->ram[0x110] && !c->ram[0x111] && !c->ram[0x112] && !c->ram[0x113];
}
/* SDL transforms event coordinates when a logical size is active. Store
   window coordinates so later resize/renderer-mode changes cannot reinterpret
   a motion event using a different scale. High-DPI input remains in window units. */
static void rings_mouse_position(SDLHost *h,int x,int y) {
    int lw,lh,ww,wh;SDL_RenderGetLogicalSize(h->renderer,&lw,&lh);SDL_GetWindowSize(h->window,&ww,&wh);
    double px=x,py=y;
    if(lw>0 && lh>0 && ww>0 && wh>0) {
        double scale=(double)ww/lw;if((double)wh/lh<scale)scale=(double)wh/lh;
        px=(ww-lw*scale)*0.5+x*scale;py=(wh-lh*scale)*0.5+y*scale;
    }
    h->mouse.x=px;h->mouse.y=py;
}
static int rings_mouse_world_point(SDLHost *h,const VDP *v,double *to_x,double *to_y) {
    int ww,wh;SDL_GetWindowSize(h->window,&ww,&wh);
    unsigned width=rings_view_width(v),height=v->frame_height;
    if(ww<=0 || wh<=0 || !width || !height)return 0;
    double dx=0,dy=0;
#ifdef GENESIS_RINGS_SMOOTH_CAMERA
    dx=h->camera.x;dy=h->camera.y;
#endif
    RingsWindowLayout canvas=rings_window_layout(v,ww,wh,h->zoom_percent,dx,dy);
    double x=(h->mouse.x-canvas.world_x)/canvas.world_scale;
    double y=(h->mouse.y-canvas.world_y)/canvas.world_scale;
    if(canvas.adaptive) {
        if(h->mouse.x<0 || h->mouse.y<0 || h->mouse.x>=ww || h->mouse.y>=wh ||
           rings_window_ui_hit(&canvas,v,h->mouse.x,h->mouse.y))return 0;
    } else if(x<0 || y<0 || x>=width || y>=height || !v->zoom_mask[(unsigned)y*width+(unsigned)x])return 0;
    *to_x=x;*to_y=y;return 1;
}
static uint8_t rings_mouse_direction(SDLHost *h,const CPU *c) {
    const VDP *v=&c->vdp;double x,y;
    if(!rings_mouse_world_point(h,v,&x,&y))return 0;
    double hx=(int)v->zoom_focus_x-RINGS_ZOOM_LEFT+16-(rings_view_wide(v) ? 0:40);
    double hy=(int)v->zoom_focus_y-RINGS_ZOOM_TOP;
#ifdef GENESIS_RINGS_SMOOTH_CAMERA
    hx+=h->camera.x;hy+=h->camera.y;
#endif
    double dx=x-hx,dy=y-hy;
    if(dx*dx+dy*dy<=64)return 0; /* Eight native pixels around the ground anchor. */
    /* Up reduces map Y, right increases map X: the four screen diagonals.
       Keep the previous sector within a two-pixel boundary to avoid jitter. */
    uint8_t previous=h->mouse.direction;
    int right=dx>=0,down=dy>=0;
    if(dx>-2 && dx<2 && previous)right=previous==PAD_UP || previous==PAD_RIGHT;
    if(dy>-2 && dy<2 && previous)down=previous==PAD_DOWN || previous==PAD_RIGHT;
    return right ? (down ? PAD_RIGHT:PAD_UP):(down ? PAD_DOWN:PAD_LEFT);
}
static void rings_mouse_event(SDLHost *h,CPU *c,const SDL_Event *e) {
    RingsMouse *m=&h->mouse;if(!m->enabled)return;
    if(e->type==SDL_MOUSEMOTION)rings_mouse_position(h,e->motion.x,e->motion.y);
    if(e->type==SDL_MOUSEBUTTONDOWN || e->type==SDL_MOUSEBUTTONUP) {
        int down=e->type==SDL_MOUSEBUTTONDOWN;
        rings_mouse_position(h,e->button.x,e->button.y);
        if(e->button.button==SDL_BUTTON_LEFT) {
            double x,y;
            m->left=down && rings_mouse_game(h,c) && rings_mouse_world_point(h,&c->vdp,&x,&y);
            m->pending=0;m->direction=0;
        }
        if(e->button.button==SDL_BUTTON_RIGHT) {
            if(down && !m->right && rings_mouse_game(h,c)) {
                m->pending=rings_mouse_direction(h,c);
                m->deadline=c->master_cycles+(uint64_t)vdp_master_frequency(&c->vdp)*2;
                m->left=0;m->direction=0;
            }
            m->right=down;
        }
    }
    if(e->type==SDL_WINDOWEVENT &&
       (e->window.event==SDL_WINDOWEVENT_FOCUS_LOST || e->window.event==SDL_WINDOWEVENT_LEAVE))rings_mouse_reset(m);
    if(e->type==SDL_KEYDOWN && sdl_pad_key(e->key.keysym.sym))rings_mouse_reset(m);
}
static void rings_mouse_update(SDLHost *h,CPU *c) {
    RingsMouse *m=&h->mouse;if(!m->enabled)return;
    if(!rings_mouse_game(h,c)) {rings_mouse_reset(m);return;}
    if(m->pending && c->master_cycles>m->deadline)m->pending=0;
    m->direction=m->left ? rings_mouse_direction(h,c):0;
}
static void rings_mouse_observe(SDLHost *h,CPU *c) {
    RingsMouse *m=&h->mouse;
    if(!m->enabled || c->pc!=0x12ff8)return;
    if(!rings_mouse_game(h,c) || c->pad_buttons[0]) {rings_mouse_reset(m);return;}
    if(m->pending && c->master_cycles>m->deadline)m->pending=0;
    uint8_t input=(uint8_t)c->d[0];
    if(m->pending) {
        /* A needs a fresh edge. A second quick click replaces the pending
           intent and waits for the native decoder to observe the release. */
        if(!(c->ram[0x244]&0x40)) {
            input=(uint8_t)((input&0xb0)|0x40|m->pending);
            m->pending=0;++m->starts;
        } else input&=(uint8_t)~0x40;
    } else if(m->left) {
        input=(uint8_t)((input&0xf0)|m->direction);++m->reads;
    }
    c->d[0]=(c->d[0]&~255u)|input;
}
#endif
#endif
