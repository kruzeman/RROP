/* Host direction intent for the verified Rings ROM. Not cartridge state. */
#ifndef GENESIS_RINGS_PAD_H
#define GENESIS_RINGS_PAD_H
#if defined(GENESIS_SDL2) && defined(GENESIS_RINGS_WIDE)
typedef struct {uint8_t previous,pending;uint64_t deadline;} RingsPadIntent;
static void rings_pad_reset(RingsPadIntent *p) {p->previous=p->pending=0;p->deadline=0;}
#endif
#endif
