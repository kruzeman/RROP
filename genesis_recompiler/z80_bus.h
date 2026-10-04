/* Functional bus ownership and RAM. Execution resumes in the Z80 scheduler. */
#ifndef GENESIS_Z80_BUS_H
#define GENESIS_Z80_BUS_H
static int z80_bus_address(uint32_t address) {
    return (address>=0xa00000 && address<0xa10000) ||
        (address>=0xa11100 && address<0xa11102) ||
        (address>=0xa11200 && address<0xa11202);
}
static uint8_t z80_bus_read(CPU *c, uint32_t address) {
    Z80Bus *z=&c->z80_bus;
    if (address>=0xa11100 && address<0xa11102)
        return address&1 ? 0:(uint8_t)!z->requested;
    if (address>=0xa11200 && address<0xa11202) {
        fail(c,"read of write-only Z80 reset register",address); return 0;
    }
    if (!z->requested) { fail(c,"Z80 bus has not been granted",address); return 0; }
    if (address<0xa04000) return z->ram[address&0x1fff];
    if (c->audio_mode && address<0xa06000) return audio_fm_read(c,address&3);
    fail(c,"Z80 peripheral read not implemented",address); return 0;
}
static void z80_bus_write(CPU *c, uint32_t address, uint8_t value) {
    Z80Bus *z=&c->z80_bus;
    if (address>=0xa11100 && address<0xa11102) {
        if (address&1) return;
        z->requested=value&1;
        return;
    }
    if (address>=0xa11200 && address<0xa11202) {
        if (address&1) return;
        z->reset_released=value&1;
        if (!z->reset_released) { z80_reset(c); audio_fm_reset(c); }
        return;
    }
    if (!z->requested) { fail(c,"Z80 bus has not been granted",address); return; }
    if (address<0xa04000) { z->ram[address&0x1fff]=value; ++z->ram_writes; return; }
    if (c->audio_mode && address<0xa06000) { audio_fm_write(c,address&3,value); return; }
    if (address>=0xa06000 && address<0xa06100) {
        z->bank=(uint16_t)((z->bank>>1)|((value&1)<<8)); return;
    }
    fail(c,"Z80 peripheral write not implemented",address);
}
#endif
