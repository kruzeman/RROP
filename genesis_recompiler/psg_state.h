#ifndef GENESIS_PSG_STATE_H
#define GENESIS_PSG_STATE_H
typedef struct {
    uint16_t tone[3];
    uint8_t volume[4], noise, latch;
    uint16_t noise_lfsr;
    uint64_t writes;
    uint16_t counter[4];
    uint8_t polarity;
    uint64_t cursor, next_tick;
    int64_t area;
} PSG;
#endif
