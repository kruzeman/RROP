/* Finite camera catch-up in presentation pixels. No prediction or pad queue.
   The console's master clock freezes the tween during pause/save selection. */
#ifndef GENESIS_RINGS_CAMERA_H
#define GENESIS_RINGS_CAMERA_H
#ifdef GENESIS_RINGS_SMOOTH_CAMERA
typedef struct {
    RingsCameraSnapshot scene;
    uint64_t start,span,now,transitions,motion_frames;
    double from_x,from_y,x,y;
    unsigned duration_ms,percent;
    uint16_t focus_x,focus_y;
    int enabled,ready,active,wide;
} RingsCameraTween;
static double rings_camera_abs(double x) {return x<0 ? -x:x;}
static void rings_camera_reset(RingsCameraTween *t) {
    t->ready=0;t->active=0;t->x=0;t->y=0;t->from_x=0;t->from_y=0;
}
static void rings_camera_evaluate(RingsCameraTween *t,uint64_t now) {
    if(!t->active)return;
    uint64_t elapsed=now>=t->start ? now-t->start:0;
    if(elapsed>=t->span) {t->x=t->y=0;t->active=0;return;}
    double left=1.0-(double)elapsed/(double)t->span;
    t->x=t->from_x*left;t->y=t->from_y*left;
}
static void rings_camera_update(RingsCameraTween *t,const VDP *v,uint64_t now,unsigned hz,unsigned percent) {
    if(!t->enabled || !v->zoom_world_visible || !v->camera.valid || !hz) {
        rings_camera_reset(t);t->now=now;return;
    }
    if(t->ready && (now<t->now || t->wide!=rings_view_wide(v) || t->percent!=percent))rings_camera_reset(t);
    t->now=now;rings_camera_evaluate(t,now);
    if(!t->ready) {
        t->scene=v->camera;t->focus_x=v->zoom_focus_x;t->focus_y=v->zoom_focus_y;
        t->percent=percent;t->wide=rings_view_wide(v);t->ready=1;return;
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
    t->scene=v->camera;t->focus_x=v->zoom_focus_x;t->focus_y=v->zoom_focus_y;
    if(!continuous) {t->x=t->y=0;t->active=0;return;}
    if(!dx && !dy)return;
    t->from_x=t->x+dx;t->from_y=t->y+dy;t->start=now;
    t->span=(uint64_t)hz*(t->duration_ms ? t->duration_ms:200)/1000;
    if(!t->span)t->span=1;
    t->x=t->from_x;t->y=t->from_y;t->active=1;++t->transitions;
}
static int rings_camera_round(double x) {return (int)(x<0 ? x-0.5:x+0.5);}
#endif
#endif
