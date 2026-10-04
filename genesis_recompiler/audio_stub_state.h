#ifndef GENESIS_AUDIO_STUB_STATE_H
#define GENESIS_AUDIO_STUB_STATE_H
typedef struct {
    uint8_t address[2], registers[2][256];
    uint64_t writes;
} YM2612Stub;
#endif
