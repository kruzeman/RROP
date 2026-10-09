/* Optional presentation state for the verified Rings of Power ROM. */
#ifndef GENESIS_RINGS_WIDE_STATE_H
#define GENESIS_RINGS_WIDE_STATE_H
#include "rings_motion_state.h"
#ifdef GENESIS_RINGS_WIDE
enum { RINGS_WIDE_WIDTH=400, RINGS_WIDE_FIELD=368, RINGS_WIDE_HEIGHT=184,
       RINGS_SCENE_HEIGHT=240, RINGS_SCENE_TOP=28,
       RINGS_ZOOM_WIDTH=960, RINGS_ZOOM_HEIGHT=704,
       RINGS_ZOOM_LEFT=296, RINGS_ZOOM_TOP=260 };
typedef struct {
    void *shadow;
#ifdef GENESIS_SDL2
    RingsMotion motion;
#endif
#ifdef GENESIS_RINGS_SMOOTH_CAMERA
    RingsCameraSnapshot camera_work,camera;
    RingsHeroLayer hero_work,hero,native_hero_work,native_hero;
    uint8_t tracking_player;
#endif
    uint8_t work[RINGS_WIDE_FIELD*RINGS_SCENE_HEIGHT];
    uint8_t scene[RINGS_WIDE_FIELD*RINGS_SCENE_HEIGHT];
    uint8_t zoom_work[RINGS_ZOOM_WIDTH*RINGS_ZOOM_HEIGHT];
    uint8_t zoom_scene[RINGS_ZOOM_WIDTH*RINGS_ZOOM_HEIGHT];
    /* Vertical distance back to the ground for the final visible writer. */
    uint8_t lift_work[RINGS_ZOOM_WIDTH*RINGS_ZOOM_HEIGHT];
    uint8_t lift_scene[RINGS_ZOOM_WIDTH*RINGS_ZOOM_HEIGHT];
    /* Original 10x10 traversal, distinct from the expanded map at 100%. */
    uint8_t native_work[288*184],native_scene[288*184];
    uint8_t native_lift_work[288*184],native_lift_scene[288*184];
    uint8_t native_pending,native_valid;
    int tile_ground_y,resource_ground;
    uint8_t resource_actor;
    uint8_t zoom_pending,zoom_valid;
    uint8_t replaying, grid, pending, valid;
    uint8_t tracking_hero;
    uint16_t bank;
    uint16_t work_focus_x,work_focus_y,focus_x,focus_y;
    uint64_t scenes, failures, submissions;
    uint64_t identity_work,identity;
} RingsWide;
#endif
#endif
