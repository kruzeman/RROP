/* Finite camera catch-up in presentation pixels. No prediction or pad queue.
   The console's master clock freezes the tween during pause/save selection. */
#ifndef GENESIS_RINGS_CAMERA_H
#define GENESIS_RINGS_CAMERA_H
#ifdef GENESIS_RINGS_SMOOTH_CAMERA
typedef struct {
    RingsCameraSnapshot scene;
    uint64_t start,span,now,transitions,motion_frames;
    double from_x,from_y,x,y;
    double from_hx,from_hy,hx,hy;
    uint16_t hero_x,hero_y,hero_sprite;
    int hero_ready;
    unsigned duration_ms,percent;
    uint16_t focus_x,focus_y;
    int enabled,ready,active,wide,native;
} RingsCameraTween;
static double rings_camera_abs(double x) {return x<0 ? -x:x;}
static void rings_camera_reset(RingsCameraTween *t) {
    t->ready=0;t->active=0;t->x=0;t->y=0;t->from_x=0;t->from_y=0;
    t->hx=t->hy=t->from_hx=t->from_hy=0;t->hero_ready=0;
}
static void rings_camera_evaluate(RingsCameraTween *t,uint64_t now) {
    if(!t->active)return;
    uint64_t elapsed=now>=t->start ? now-t->start:0;
    if(elapsed>=t->span) {t->x=t->y=t->hx=t->hy=0;t->active=0;return;}
    double left=1.0-(double)elapsed/(double)t->span;
    /* Immediate travel with a gentle stop; no extra input wait. */
    left*=left;
    t->x=t->from_x*left;t->y=t->from_y*left;
    t->hx=t->from_hx*left;t->hy=t->from_hy*left;
}
static void rings_camera_update(RingsCameraTween *t,const VDP *v,uint64_t now,unsigned hz,unsigned percent) {
    int native=v->native_scene && v->native_world_valid;
    if(native)percent=100;
    if(!t->enabled || (!v->zoom_world_visible && !native) || !v->camera.valid || !hz) {
        rings_camera_reset(t);t->now=now;return;
    }
    if(t->ready && (now<t->now || t->wide!=rings_view_wide(v) || t->native!=native || t->percent!=percent))rings_camera_reset(t);
    t->now=now;rings_camera_evaluate(t,now);
    if(!t->ready) {
        t->scene=v->camera;t->focus_x=v->zoom_focus_x;t->focus_y=v->zoom_focus_y;
        t->percent=percent;t->wide=rings_view_wide(v);t->native=native;t->ready=1;
        t->hero_ready=v->hero.valid;t->hero_x=v->hero.x;t->hero_y=v->hero.y;t->hero_sprite=v->hero.sprite;return;
    }
    if(t->scene.generation==v->camera.generation)return;
    double zoom=percent/100.0;
    double dx=zoom*((double)v->camera.x-t->scene.x)-(1.0-zoom)*((double)v->zoom_focus_x-t->focus_x);
    double dy=zoom*((double)v->camera.y-t->scene.y)-(1.0-zoom)*((double)v->zoom_focus_y-t->focus_y);
    int continuous=t->scene.identity==v->camera.identity && v->camera.generation>t->scene.generation &&
        rings_camera_abs((double)v->camera.x-t->scene.x)<=56 &&
        rings_camera_abs((double)v->camera.y-t->scene.y)<=32 &&
        rings_camera_abs((double)v->zoom_focus_x-t->focus_x)<=48 &&
        rings_camera_abs((double)v->zoom_focus_y-t->focus_y)<=48;
    double hx=0,hy=0;
    int hero_continuous=t->hero_ready && v->hero.valid && t->hero_sprite==v->hero.sprite &&
        rings_camera_abs((double)v->hero.x-t->hero_x)<=48 && rings_camera_abs((double)v->hero.y-t->hero_y)<=48;
    if(hero_continuous) {
        /* Actor travel in world pixels, independent of camera/zoom anchoring. */
        hx=(double)t->hero_x-v->hero.x-((double)v->camera.x-t->scene.x);
        hy=(double)t->hero_y-v->hero.y-((double)v->camera.y-t->scene.y);
    } else t->hx=t->hy=t->from_hx=t->from_hy=0;
    t->hero_ready=v->hero.valid;t->hero_x=v->hero.x;t->hero_y=v->hero.y;t->hero_sprite=v->hero.sprite;
    t->scene=v->camera;t->focus_x=v->zoom_focus_x;t->focus_y=v->zoom_focus_y;
    if(!continuous) {t->x=t->y=t->hx=t->hy=0;t->active=0;return;}
    if(!dx && !dy && !hx && !hy)return;
    t->from_x=t->x+dx;t->from_y=t->y+dy;
    t->from_hx=t->hx+hx;t->from_hy=t->hy+hy;t->start=now;
    t->span=(uint64_t)hz*(t->duration_ms ? t->duration_ms:240)/1000;
    if(!t->span)t->span=1;
    t->x=t->from_x;t->y=t->from_y;t->hx=t->from_hx;t->hy=t->from_hy;t->active=1;++t->transitions;
}
static int rings_camera_round(double x) {return (int)(x<0 ? x-0.5:x+0.5);}
#endif
#endif
