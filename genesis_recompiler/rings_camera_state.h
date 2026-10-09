/* Frozen presentation coordinates belong to the submitted scene, never to
   mutable RAM that may already describe the next in-progress drawing pass. */
#ifndef GENESIS_RINGS_CAMERA_STATE_H
#define GENESIS_RINGS_CAMERA_STATE_H
#ifdef GENESIS_RINGS_SMOOTH_CAMERA
enum { RINGS_HERO_WIDTH=128, RINGS_HERO_HEIGHT=128 };
/* Frozen actor ink and the terrain beneath it; derived, never serialized. */
typedef struct {
    uint8_t ink[128*128],under[128*128],cover[128*128];
    int16_t under_lift[128*128];
    uint16_t x,y,ground_y,sprite;
    uint8_t valid;
} RingsHeroLayer;
typedef struct {
    uint64_t generation,clocks,identity;
    int32_t x,y;
    uint8_t valid;
} RingsCameraSnapshot;
#endif
#endif
