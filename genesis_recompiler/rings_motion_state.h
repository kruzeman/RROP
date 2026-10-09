/* Opt-in Enhanced scheduling, not serialized cartridge state. */
#ifndef GENESIS_RINGS_MOTION_STATE_H
#define GENESIS_RINGS_MOTION_STATE_H
#if defined(GENESIS_RINGS_WIDE) && defined(GENESIS_SDL2)
typedef struct {
    RingsPadIntent *intent;
    int enabled,active,drawing,finish,verified;
    unsigned fallback;
    uint64_t turn,due,period,next_step,draw_budget,player_budget;
    uint64_t attempts,moves,rejected,passes,timing_failures;
} RingsMotion;
#endif
#endif
