/* Host mouse intent for the verified Rings ROM. Never enqueue pad snapshots:
   merge only at the original main-game direction decoder's pad return. */
#ifndef GENESIS_RINGS_MOUSE_H
#define GENESIS_RINGS_MOUSE_H
#if defined(GENESIS_SDL2) && defined(GENESIS_RINGS_WIDE)
typedef struct {
    double x,y;
    uint64_t deadline,starts,reads;
    uint8_t direction,pending;
    int enabled,left,right;
} RingsMouse;
static void rings_mouse_reset(RingsMouse *m) {
    m->left=m->right=0;m->direction=m->pending=0;m->deadline=0;
}
#endif
#endif
