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
    uint64_t hero_start,hero_span;
    double hero_from_x,hero_from_y,hero_x,hero_y;
    int32_t hero_world_x,hero_world_y;
    int native,hero_ready,hero_active;
} RingsCameraTween;
static double rings_camera_abs(double x) {return x<0 ? -x:x;}
static void rings_camera_reset(RingsCameraTween *t) {
    t->ready=0;t->active=0;t->x=0;t->y=0;t->from_x=0;t->from_y=0;
    t->hero_ready=t->hero_active=0;t->hero_x=t->hero_y=0;t->hero_from_x=t->hero_from_y=0;
}
static void rings_camera_evaluate(RingsCameraTween *t,uint64_t now) {
    if(t->hero_active) {
        uint64_t elapsed=now>=t->hero_start ? now-t->hero_start:0;
        if(elapsed>=t->hero_span) {t->hero_x=t->hero_y=0;t->hero_active=0;}
        else {
            double left=1.0-(double)elapsed/(double)t->hero_span;
            t->hero_x=t->hero_from_x*left;t->hero_y=t->hero_from_y*left;
        }
    }
    if(!t->active)return;
    uint64_t elapsed=now>=t->start ? now-t->start:0;
    if(elapsed>=t->span) {t->x=t->y=0;t->active=0;return;}
    double left=1.0-(double)elapsed/(double)t->span;
    t->x=t->from_x*left;t->y=t->from_y*left;
}
static void rings_camera_update(RingsCameraTween *t,const VDP *v,uint64_t now,unsigned hz,unsigned percent) {
    int native=v->native_scene && v->native_motion.valid;
    int hero_valid=native ? v->native_motion.hero_valid:v->hero_patch.valid && v->hero_patch.hero_valid;
    int32_t hx=(native ? v->native_motion.hero_x:v->hero_patch.hero_x)+v->camera.x;
    int32_t hy=(native ? v->native_motion.hero_y:v->hero_patch.hero_y)+v->camera.y;
    if(native)percent=100;
    if(!t->enabled || (!v->zoom_world_visible && !native) || !v->camera.valid || !hz) {
        rings_camera_reset(t);t->now=now;return;
    }
    if(t->ready && (now<t->now || t->native!=native || t->wide!=rings_view_wide(v) || t->percent!=percent))rings_camera_reset(t);
    t->now=now;rings_camera_evaluate(t,now);
    if(!hero_valid) {t->hero_ready=t->hero_active=0;t->hero_x=t->hero_y=0;}
    if(!t->ready) {
        t->scene=v->camera;t->focus_x=v->zoom_focus_x;t->focus_y=v->zoom_focus_y;
        t->percent=percent;t->wide=rings_view_wide(v);t->native=native;t->ready=1;
        if(hero_valid) {
            t->hero_world_x=hx;t->hero_world_y=hy;t->hero_ready=1;
        }
        return;
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
    if(hero_valid) {
        int hx_delta=hx-t->hero_world_x,hy_delta=hy-t->hero_world_y;
        int hero_continuous=continuous && t->hero_ready &&
            rings_camera_abs(hx_delta)<=56 && rings_camera_abs(hy_delta)<=32;
        if(!hero_continuous) {t->hero_x=t->hero_y=0;t->hero_active=0;}
        else if(hx_delta || hy_delta) {
            /* Offset in world space: camera movement then cancels out of a
               centered actor. No predicted steps and no queued input. */
            t->hero_from_x=t->hero_x-hx_delta;t->hero_from_y=t->hero_y-hy_delta;
            t->hero_x=t->hero_from_x;t->hero_y=t->hero_from_y;t->hero_start=now;
            t->hero_span=(uint64_t)hz*(t->duration_ms ? t->duration_ms:200)/1000;
            if(!t->hero_span)t->hero_span=1;
            t->hero_active=1;
            /* Fast-forward can outpace a finite patch. Snap to the accepted
               position rather than queueing a long visual walk off its edge. */
            if(rings_camera_abs(t->hero_x)>64 || rings_camera_abs(t->hero_y)>48) {
                t->hero_x=t->hero_y=0;t->hero_active=0;
            }
        }
        t->hero_world_x=hx;t->hero_world_y=hy;t->hero_ready=1;
    }
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
