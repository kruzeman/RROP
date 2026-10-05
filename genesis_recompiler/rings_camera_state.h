/* Frozen presentation coordinates belong to the submitted scene, never to
   mutable RAM that may already describe the next in-progress drawing pass. */
#ifndef GENESIS_RINGS_CAMERA_STATE_H
#define GENESIS_RINGS_CAMERA_STATE_H
#ifdef GENESIS_RINGS_SMOOTH_CAMERA
typedef struct {
    uint64_t generation,clocks,identity;
    int32_t x,y;
    uint8_t valid;
} RingsCameraSnapshot;
/* Native draw calls, frozen only after the bitmap upload completes. These
   derived presentation records are deliberately absent from save files. */
enum { RINGS_NATIVE_DRAWS=2048 };
typedef struct {
    uint16_t id;
    int16_t x,y;
    uint8_t flipped,hero;
    int16_t ground;
    uint8_t actor;
} RingsNativeDraw;
typedef struct {
    RingsCameraSnapshot camera;
    RingsNativeDraw draw[RINGS_NATIVE_DRAWS];
    unsigned count;
    int16_t hero_x,hero_y;
    uint8_t valid,hero_valid,overflow;
} RingsNativeMotion;
/* A bounded region in the original resource writer's coordinates. Capture
   every writer intersecting it, including scenery that covers the hero. */
enum { RINGS_HERO_LEFT=-64,RINGS_HERO_TOP=-96,
       RINGS_HERO_WIDTH=448,RINGS_HERO_HEIGHT=320,RINGS_HERO_DRAWS=8192 };
typedef struct {
    RingsNativeDraw draw[RINGS_HERO_DRAWS];
    unsigned count;
    int16_t hero_x,hero_y;
    uint8_t valid,hero_valid,overflow;
} RingsHeroPatch;
#endif
#endif
