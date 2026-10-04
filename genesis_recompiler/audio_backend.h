/* C ABI for the optional BSD-licensed ymfm YM2612 sound backend. */
#ifndef GENESIS_AUDIO_BACKEND_H
#define GENESIS_AUDIO_BACKEND_H
#include <stdint.h>
#include <stddef.h>
#ifdef GENESIS_AUDIO
#ifdef __cplusplus
extern "C" {
#endif
void *genesis_ymfm_create(void);
void genesis_ymfm_destroy(void *chip);
void genesis_ymfm_reset(void *chip);
void genesis_ymfm_advance(void *chip, uint64_t master, int32_t stereo[2]);
uint8_t genesis_ymfm_read(void *chip, unsigned port);
void genesis_ymfm_write(void *chip, unsigned port, uint8_t value);
size_t genesis_ymfm_state_size(void *chip);
int genesis_ymfm_save_state(void *chip, uint8_t *bytes, size_t size);
void *genesis_ymfm_load_state(const uint8_t *bytes, size_t size);
#ifdef __cplusplus
}
#endif
#endif
#endif
