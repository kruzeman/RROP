#ifndef GENESIS_AUDIO_STATE_H
#define GENESIS_AUDIO_STATE_H
#include "audio_backend.h"
enum { AUDIO_RATE=48000, AUDIO_RING_FRAMES=4096, AUDIO_WAV_FRAMES=1024 };
typedef struct {
    void *fm;
    FILE *wav;
    uint64_t cursor, next_sample, sample_index, frames, wav_bytes, dropped;
    int32_t previous_input[2], filter[2];
    int16_t ring[AUDIO_RING_FRAMES*2], wav_buffer[AUDIO_WAV_FRAMES*2];
    unsigned read, count, wav_count, peak;
    int initialized, playback, error;
} Audio;
#endif
