#ifndef GENESIS_SCHEDULER_H
#define GENESIS_SCHEDULER_H
static void machine_advance(CPU *c, unsigned cycles) {
    if (c->fault) return;
    unsigned clocks=cycles*7;
    c->cycles+=cycles; c->master_cycles+=clocks;
    vdp_advance(c,clocks);
    unsigned zclocks=c->z80_divider+clocks;
    c->z80_divider=zclocks%15;
    z80_tick(c,zclocks/15);
    audio_sync(c);
}
static int machine_interrupt(CPU *c) {
    unsigned level=vdp_irq_level(&c->vdp);
    if (!level || level<=((c->sr>>8)&7)) return 0;
    uint16_t saved=c->sr; uint32_t pc=c->pc;
    set_sr(c,(saved|0x2000)&~0x8000u);
    push32(c,pc); if (c->fault) return 1;
    c->a[7]-=2; write_mem(c,c->a[7],2,saved); if (c->fault) return 1;
    c->sr=(uint16_t)((c->sr&~0x700u)|(level<<8));
    uint32_t target=read_mem(c,(24+level)*4,4);
    if (c->fault) return 1;
    c->pc=target&0xffffff; c->halted=0;
    vdp_irq_ack(&c->vdp,level); ++c->interrupts;
    machine_advance(c,44);
    return 1;
}
#include "rings_motion.h"
static void machine_step(CPU *c) {
    if (c->fault) return;
    if (machine_interrupt(c)) return;
    if (c->halted) { machine_advance(c,4); return; }
#if defined(GENESIS_RINGS_WIDE) && defined(GENESIS_SDL2)
    if(rings_motion_before(c))return;
#endif
    c->instruction_cycles=0;
#ifdef GENESIS_RINGS_WIDE
    rings_wide_observe(c);
#endif
    translated_step(c); ++c->steps;
    unsigned cycles=c->instruction_cycles;
    c->instruction_cycles=0;
#if defined(GENESIS_RINGS_WIDE) && defined(GENESIS_SDL2)
    if(c->wide && c->wide->motion.drawing)return;
#endif
    machine_advance(c,cycles);
}
static int machine_can_wake(const CPU *c) {
    unsigned mask=(c->sr>>8)&7;
    return ((c->vdp.registers[1]&0x20) && mask<6) || ((c->vdp.registers[0]&0x10) && mask<4);
}
#endif
