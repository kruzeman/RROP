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
#endif
#endif
