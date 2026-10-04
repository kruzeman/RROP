/* Support for statically translated Z80 operations; no opcode interpreter. */
#ifndef GENESIS_Z80_RUNTIME_H
#define GENESIS_Z80_RUNTIME_H
static unsigned translated_z80_step(CPU *c);
static void z80_reset(CPU *c) {
    Z80CPU *z=&c->z80_cpu;
    z->pc=0; z->wz=0; z->i=0; z->r=0; z->iff1=z->iff2=z->im=z->halted=z->ei_delay=0; z->debt=0;
}
static uint16_t z80_pair(CPU *c, unsigned pair) {
    Z80CPU *z=&c->z80_cpu;
    if (pair<3) return (uint16_t)((z->r8[pair*2]<<8)|z->r8[pair*2+1]);
    if (pair==3) return z->sp;
    if (pair==4) return z->ix;
    if (pair==5) return z->iy;
    return (uint16_t)((z->a<<8)|z->f);
}
static void z80_set_pair(CPU *c, unsigned pair, uint16_t value) {
    Z80CPU *z=&c->z80_cpu;
    if (pair<3) { z->r8[pair*2]=(uint8_t)(value>>8); z->r8[pair*2+1]=(uint8_t)value; }
    else if (pair==3) z->sp=value;
    else if (pair==4) z->ix=value;
    else if (pair==5) z->iy=value;
    else { z->a=(uint8_t)(value>>8); z->f=(uint8_t)value; }
}
static uint8_t z80_read(CPU *c, uint16_t address) {
    if (address<0x4000) return c->z80_bus.ram[address&0x1fff];
    if (c->audio_mode && address<0x6000) return audio_fm_read(c,address&3);
    if (address>=0x8000) return (uint8_t)read_mem(c,((uint32_t)c->z80_bus.bank<<15)|(address&0x7fff),1);
    fail(c,"Z80 peripheral read not implemented",0xa00000+address); return 0;
}
static void z80_write(CPU *c, uint16_t address, uint8_t value) {
    if (address<0x4000) { c->z80_bus.ram[address&0x1fff]=value; return; }
    if (c->audio_mode && address<0x6000) { audio_fm_write(c,address&3,value); return; }
    if (address>=0x6000 && address<0x6100) { c->z80_bus.bank=(uint16_t)((c->z80_bus.bank>>1)|((value&1)<<8)); return; }
    if (address>=0x7f10 && address<0x7f18) { psg_write(c,value); return; }
    if (address>=0x8000) { write_mem(c,((uint32_t)c->z80_bus.bank<<15)|(address&0x7fff),1,value); return; }
    fail(c,"Z80 peripheral write not implemented",0xa00000+address);
}
static uint16_t z80_read16(CPU *c, uint16_t address) {
    uint8_t low=z80_read(c,address); if (c->fault) return 0;
    return (uint16_t)(low|(z80_read(c,(uint16_t)(address+1))<<8));
}
static void z80_write16(CPU *c, uint16_t address, uint16_t value) {
    z80_write(c,address,(uint8_t)value);
    if (!c->fault) z80_write(c,(uint16_t)(address+1),(uint8_t)(value>>8));
}
static uint16_t z80_pop(CPU *c) {
    uint16_t value=z80_read16(c,c->z80_cpu.sp);
    if (!c->fault) c->z80_cpu.sp=(uint16_t)(c->z80_cpu.sp+2);
    return value;
}
static void z80_push(CPU *c, uint16_t value) {
    z80_write(c,--c->z80_cpu.sp,(uint8_t)(value>>8));
    if (!c->fault) z80_write(c,--c->z80_cpu.sp,(uint8_t)value);
}
static uint8_t z80_reg(CPU *c, unsigned reg) {
    return reg<6 ? c->z80_cpu.r8[reg]:reg==6 ? z80_read(c,z80_pair(c,2)):c->z80_cpu.a;
}
static void z80_set_reg(CPU *c, unsigned reg, uint8_t value) {
    if (reg<6) c->z80_cpu.r8[reg]=value;
    else if (reg==6) z80_write(c,z80_pair(c,2),value);
    else c->z80_cpu.a=value;
}
static void z80_m1(CPU *c, unsigned fetches) {
    c->z80_cpu.r=(uint8_t)((c->z80_cpu.r&0x80)|((c->z80_cpu.r+fetches)&0x7f));
}
static uint8_t z80_szxy(uint8_t value) {
    unsigned p=value; p^=p>>4; p^=p>>2; p^=p>>1;
    return (uint8_t)((value&0xa8)|(value==0 ? Z_Z:0)|(!(p&1) ? Z_PV:0));
}
static void z80_alu(CPU *c, unsigned kind, uint8_t src) {
    Z80CPU *z=&c->z80_cpu; uint8_t a=z->a, result, flags;
    if (kind>=4 && kind<=6) {
        result=kind==4 ? a&src:kind==5 ? a^src:a|src;
        flags=(uint8_t)(z80_szxy(result)|(kind==4 ? Z_H:0));
    } else {
        unsigned carry=(kind==1 || kind==3) ? !!(z->f&Z_C):0;
        int sub=kind==2 || kind==3 || kind==7;
        result=(uint8_t)(sub ? a-src-carry:a+src+carry);
        unsigned co=sub ? (unsigned)src+carry>a:(unsigned)a+src+carry>255;
        unsigned ov=!!((sub ? (a^src)&(a^result):~(a^src)&(a^result))&0x80);
        flags=(uint8_t)((z80_szxy(result)&~Z_PV)|(co ? Z_C:0)|(ov ? Z_PV:0)|((a^src^result)&Z_H)|(sub ? Z_N:0));
        if (kind==7) flags=(uint8_t)((flags&~0x28)|(src&0x28));
    }
    z->f=flags; if (kind!=7) z->a=result;
}
static uint8_t z80_inc(CPU *c, uint8_t value, int change) {
    uint8_t result=(uint8_t)(value+change);
    unsigned ov=change<0 ? value==0x80:value==0x7f;
    c->z80_cpu.f=(uint8_t)((c->z80_cpu.f&Z_C)|(z80_szxy(result)&~Z_PV)|((value^result)&Z_H)|(ov ? Z_PV:0)|(change<0 ? Z_N:0));
    return result;
}
static uint8_t z80_rotate(CPU *c, uint8_t value, unsigned kind) {
    unsigned carry=c->z80_cpu.f&Z_C, out;
    uint8_t result;
    if (kind==0 || kind==2 || kind==4 || kind==6) {
        out=value>>7;
        result=(uint8_t)((value<<1)|(kind==0 ? out:kind==2 ? carry:kind==6 ? 1:0));
    } else {
        out=value&1;
        result=(uint8_t)((value>>1)|(kind==1 ? out<<7:kind==3 ? carry<<7:kind==5 ? value&128:0));
    }
    c->z80_cpu.f=(uint8_t)(z80_szxy(result)|out);
    return result;
}
static void z80_add_pair(CPU *c, unsigned pair, uint16_t src) {
    uint16_t hl=z80_pair(c,pair); uint32_t sum=(uint32_t)hl+src;
    c->z80_cpu.wz=(uint16_t)(hl+1);
    c->z80_cpu.f=(uint8_t)((c->z80_cpu.f&(Z_S|Z_Z|Z_PV))|((sum>>8)&0x28)|((hl^src^sum)&0x1000 ? Z_H:0)|(sum>65535 ? Z_C:0));
    z80_set_pair(c,pair,(uint16_t)sum);
}
static void z80_add_hl(CPU *c, uint16_t src) { z80_add_pair(c,2,src); }
static void z80_alu16(CPU *c, uint16_t rhs, int subtract) {
    uint16_t lhs=z80_pair(c,2);
    unsigned carry=c->z80_cpu.f&Z_C;
    uint32_t wide=subtract ? (uint32_t)lhs-rhs-carry:(uint32_t)lhs+rhs+carry;
    uint16_t result=(uint16_t)wide;
    unsigned overflow=(subtract ? lhs^rhs:~(lhs^rhs))&(lhs^result)&0x8000;
    c->z80_cpu.f=(uint8_t)(((result>>8)&0xa8)|(result==0 ? Z_Z:0)|
        ((lhs^rhs^result)&0x1000 ? Z_H:0)|(wide>65535 ? Z_C:0)|
        (overflow ? Z_PV:0)|(subtract ? Z_N:0));
    c->z80_cpu.wz=(uint16_t)(lhs+1);
    z80_set_pair(c,2,result);
}
static void z80_bit(CPU *c, uint8_t value, unsigned bit, uint8_t xy) {
    c->z80_cpu.f=(uint8_t)((c->z80_cpu.f&Z_C)|(xy&0x28)|Z_H|
        (!(value&(1u<<bit)) ? Z_Z|Z_PV:0)|(bit==7 ? value&Z_S:0));
}
static int z80_condition(CPU *c, unsigned condition) {
    uint8_t f=c->z80_cpu.f;
    switch (condition) {
        case 0:return !(f&Z_Z); case 1:return !!(f&Z_Z);
        case 2:return !(f&Z_C); case 3:return !!(f&Z_C);
        case 4:return !(f&Z_PV); case 5:return !!(f&Z_PV);
        case 6:return !(f&Z_S); case 7:return !!(f&Z_S);
    }
    return 0;
}
static int z80_block(CPU *c, int direction, int repeat) {
    uint16_t source=z80_pair(c,2), destination=z80_pair(c,1), count=z80_pair(c,0);
    uint8_t value=z80_read(c,source); if (c->fault) return 0;
    z80_write(c,destination,value); if (c->fault) return 0;
    z80_set_pair(c,2,(uint16_t)(source+direction));
    z80_set_pair(c,1,(uint16_t)(destination+direction));
    z80_set_pair(c,0,--count);
    uint8_t sum=(uint8_t)(c->z80_cpu.a+value);
    c->z80_cpu.f=(uint8_t)((c->z80_cpu.f&(Z_C|Z_Z|Z_S))|(count ? Z_PV:0)|(sum&8)|((sum&2)<<4));
    return repeat && count;
}
static void z80_tick(CPU *c, unsigned quantum) {
    Z80CPU *z=&c->z80_cpu;
    if (c->audio_mode==AUDIO_STUB || c->fault || c->z80_bus.requested || !c->z80_bus.reset_released) return;
    z->debt+=quantum;
    while (z->debt>0 && !c->fault) {
        unsigned cycles;
        if (z->irq_line && z->iff1 && !z->ei_delay) {
            // The Genesis VDP leaves the interrupt-acknowledge data bus at $FF.
            // IM 0 therefore executes RST $38, IM 1 uses its fixed vector.
            z80_m1(c,1);z->iff1=z->iff2=0;z->halted=0;
            z80_push(c,z->pc);if(c->fault)return;
            uint16_t target=z->im==2 ? z80_read16(c,(uint16_t)((z->i<<8)|0xff)):0x38;
            if(c->fault)return;
            z->pc=z->wz=target;cycles=z->im==2 ? 19:13;++z->interrupts;
        } else if (z->halted) { z80_m1(c,1); cycles=4; }
        else {
            cycles=translated_z80_step(c); ++z->steps;
            if(z->ei_delay)--z->ei_delay;
        }
        if (!cycles || c->fault) return;
        z->cycles+=cycles; z->debt-=cycles;
    }
}
#endif
