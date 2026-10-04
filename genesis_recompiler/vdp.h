/* VDP ports, memory and synchronous DMA. Beam state is advanced by the scheduler. */
#ifndef GENESIS_VDP_H
#define GENESIS_VDP_H

static void vdp_increment(VDP *v) {
    v->address=(uint16_t)(v->address+v->registers[15]);
}
static uint32_t vdp_dma_length(VDP *v) {
    uint32_t length=v->registers[19]|((uint32_t)v->registers[20]<<8);
    return length ? length:65536;
}
static void vdp_store_word(CPU *c, uint16_t value) {
    VDP *v=&c->vdp;
    switch (v->code&15) {
        case 1:
#ifdef GENESIS_RINGS_MENU_FONT
            rings_text_invalidate(v,v->address);
#endif
            v->vram[v->address]=(uint8_t)(value>>8);
            v->vram[v->address^1]=(uint8_t)value;
#ifdef GENESIS_RINGS_MENU_FONT
            if(!(v->address&1) && !v->fill_pending)rings_text_capture(c,value);
#endif
            break;
        case 3: v->cram[(v->address>>1)&63]=(uint16_t)(value&0x0eee); break;
        case 5: {
            unsigned index=(v->address>>1)&63;
            if (index<40) v->vsram[index]=(uint16_t)(value&0x07ff);
            break;
        }
        default: fail(c,"unsupported VDP data-write access code",0xc00000); return;
    }
    vdp_increment(v);
}
static uint16_t vdp_load_word(CPU *c) {
    VDP *v=&c->vdp; uint16_t value=0;
    switch (v->code&15) {
        case 0: {
            unsigned a=v->address&0xfffe;
            value=(uint16_t)((v->vram[a]<<8)|v->vram[a+1]);
            break;
        }
        case 8: value=v->cram[(v->address>>1)&63]; break;
        case 4: {
            unsigned index=(v->address>>1)&63;
            value=index<40 ? v->vsram[index]:0;
            break;
        }
        default: fail(c,"unsupported VDP data-read access code",0xc00000); return 0;
    }
    vdp_increment(v); return value;
}
static void vdp_start_dma(CPU *c) {
    VDP *v=&c->vdp;
    unsigned mode=v->registers[23]>>6;
    if (mode==2) { v->fill_pending=1; return; }
    uint32_t length=vdp_dma_length(v);
    if (mode==3) {
        uint16_t source=(uint16_t)(v->registers[21]|(v->registers[22]<<8));
        for (uint32_t n=0; n<length; ++n) {
            /* Copy is sequential, so overlapping regions feed later reads. */
#ifdef GENESIS_RINGS_MENU_FONT
            rings_text_invalidate(v,v->address);
#endif
            v->vram[v->address^1]=v->vram[source^1];
            ++source; vdp_increment(v); ++v->dma_bytes;
        }
        v->registers[21]=(uint8_t)source; v->registers[22]=(uint8_t)(source>>8);
    } else {
        uint32_t source=(v->registers[21]|((uint32_t)v->registers[22]<<8)|((uint32_t)(v->registers[23]&0x7f)<<16))<<1;
        /* The 68000 DMA source counter wraps within its 128 KiB bank. */
        uint32_t bank=source&0xfe0000;
        for (uint32_t n=0; n<length; ++n) {
            if ((source&0xffffff)>=0xc00000 && (source&0xffffff)<0xc00020) {
                fail(c,"VDP DMA source points to VDP ports",source); return;
            }
            uint16_t word=(uint16_t)read_mem(c,source,2);
            if (c->fault) return;
            vdp_store_word(c,word);
            if (c->fault) return;
            source=bank|((source+2)&0x1ffff); v->dma_bytes+=2;
        }
        source>>=1;
        v->registers[21]=(uint8_t)source; v->registers[22]=(uint8_t)(source>>8);
        v->registers[23]=(uint8_t)(source>>16);
    }
    v->registers[19]=0; v->registers[20]=0;
}
static void vdp_control_write(CPU *c, uint16_t value) {
    VDP *v=&c->vdp;
    v->bus_value=value;
    if (v->command_pending) {
        v->address=(uint16_t)((v->address&0x3fff)|((value&3)<<14));
        v->code=(uint8_t)((v->code&3)|((value>>2)&0x3c));
        v->command_pending=0;
        if ((v->code&0x20) && (v->registers[1]&0x10)) vdp_start_dma(c);
        return;
    }
    if ((value&0xc000)==0x8000) {
        unsigned reg=(value>>8)&31;
        if (reg<24) v->registers[reg]=(uint8_t)value;
        /* Register writes set the access-code low bits to zero. */
        v->code=0;
        return;
    }
    v->address=(uint16_t)((v->address&0xc000)|(value&0x3fff));
    v->code=(uint8_t)((v->code&0x3c)|(value>>14));
    v->command_pending=1;
}
static void vdp_data_write(CPU *c, uint16_t value) {
    VDP *v=&c->vdp;
    v->command_pending=0; v->bus_value=value;
    vdp_store_word(c,value);
    if (c->fault) return;
    ++v->data_writes;
    if (v->fill_pending) {
        v->fill_pending=0;
        if ((v->code&15)!=1) { fail(c,"VDP DMA fill requires VRAM",0xc00000); return; }
        /* The triggering FIFO word is written normally. Fill subsequently
           writes its high byte onto the opposite VRAM byte lane. */
        uint32_t length=vdp_dma_length(v);
        for (uint32_t n=0; n<length; ++n) {
#ifdef GENESIS_RINGS_MENU_FONT
            rings_text_invalidate(v,v->address);
#endif
            v->vram[v->address^1]=(uint8_t)(value>>8);
            vdp_increment(v); ++v->dma_bytes;
        }
        v->registers[19]=0; v->registers[20]=0;
    }
}
static uint16_t vdp_port_read(CPU *c, uint32_t address) {
    VDP *v=&c->vdp;
    switch (address&0x1c) {
        case 0: {
            v->command_pending=0;
            uint16_t value=vdp_load_word(c); ++v->data_reads; v->bus_value=value;
            return value;
        }
        case 4:
            v->command_pending=0;
            { uint16_t status=(uint16_t)((v->bus_value&0xfc00)|0x0200|v->pal|
                (vdp_vblank(v) ? 8:0)|(vdp_hblank(v) ? 4:0)|(vdp_status_vint(c) ? 0x80:0));
              return status; }
        case 8: case 12: return vdp_counter(v);
        default: fail(c,"read of write-only VDP/PSG port",address); return 0;
    }
}
static void vdp_port_write(CPU *c, uint32_t address, uint16_t value) {
    if ((address&0x18)==0x10) { psg_write(c,(uint8_t)value); return; }
    switch (address&0x1c) {
        case 0: vdp_data_write(c,value); return;
        case 4: vdp_control_write(c,value); return;
        default: fail(c,"VDP counter/audio port not implemented",address); return;
    }
}
#endif
