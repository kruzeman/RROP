#ifndef GENESIS_Z80_BUS_STATE_H
#define GENESIS_Z80_BUS_STATE_H
typedef struct {
    uint8_t ram[8192];
    uint8_t requested, reset_released;
    uint16_t bank;
    uint64_t ram_writes;
} Z80Bus;
#endif
