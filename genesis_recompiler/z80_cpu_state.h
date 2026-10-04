#ifndef GENESIS_Z80_CPU_STATE_H
#define GENESIS_Z80_CPU_STATE_H
enum { Z_C=1, Z_N=2, Z_PV=4, Z_X=8, Z_H=16, Z_Y=32, Z_Z=64, Z_S=128 };
typedef struct {
    uint8_t r8[6], alternate[6], a, f, a_alt, f_alt, i, r, iff1, iff2, im, halted;
    uint8_t irq_line, ei_delay;
    uint16_t pc, sp, ix, iy, wz;
    int64_t debt;
    uint64_t steps, cycles, interrupts;
} Z80CPU;
#endif
