/* MC68000 and Genesis bus. Instruction-boundary NTSC/PAL device scheduling. */
#ifndef GENESIS_RUNTIME_H
#define GENESIS_RUNTIME_H
#include <stdint.h>
#include <stddef.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <errno.h>
#include <inttypes.h>
#include "rings_camera_state.h"
#include "vdp_state.h"
#include "z80_bus_state.h"
#include "z80_cpu_state.h"
#include "psg_state.h"
#include "eeprom_state.h"
#include "audio_stub_state.h"
#include "audio_state.h"
#include "rings_wide_state.h"

enum { AUDIO_STRICT=0, AUDIO_STUB=1, AUDIO_MUTE=2, AUDIO_ON=3 };
enum { F_C=1, F_V=2, F_Z=4, F_N=8, F_X=16 };
typedef struct {
    uint32_t d[8], a[8], pc;
    uint32_t usp, ssp;
    uint16_t sr;
    uint8_t ram[65536];
    uint8_t io_data[3], io_control[3], tmss[4];
    uint8_t io_tx[3], io_serial_control[3];
    uint8_t pad_buttons[3];
    VDP vdp;
    Z80Bus z80_bus;
    Z80CPU z80_cpu;
    PSG psg;
    EEPROM eeprom;
    YM2612Stub ym2612_stub;
    Audio audio;
    int audio_mode;
    const uint8_t *rom;
    size_t rom_size;
    uint64_t steps;
    uint64_t cycles, master_cycles, interrupts;
    unsigned instruction_cycles, z80_divider;
    int halted, fault;
    uint32_t fault_address;
    const char *reason;
#ifdef GENESIS_RINGS_SAVES
    /* Host diagnostics only; not serialized as game state. */
    uint64_t rings_pool_revision;
    uint32_t rings_pool_write_pc;
#endif
#ifdef GENESIS_RINGS_WIDE
    RingsWide *wide;
#endif
#if defined(GENESIS_RINGS_SAVES) && defined(GENESIS_SDL2)
    /* Host menu extensions are not part of a saved console state. */
    int rings_settings_enabled;
#endif
} CPU;
#include "rings_scene.h"
#include "rings_settings_rom.h"
#ifdef GENESIS_RINGS_MENU_FONT
#include "rings_text_capture.h"
#endif
static uint16_t vdp_port_read(CPU *c, uint32_t address);
static void vdp_port_write(CPU *c, uint32_t address, uint16_t value);
static void z80_reset(CPU *c);
static void vdp_render(CPU *c);
static void audio_sync(CPU *c);
static uint8_t audio_fm_read(CPU *c,unsigned port);
static void audio_fm_write(CPU *c,unsigned port,uint8_t value);
static void audio_fm_reset(CPU *c);

static void fail(CPU *c, const char *reason, uint32_t address) {
    if (!c->fault) { c->fault=1; c->reason=reason; c->fault_address=address; }
}
#include "audio_stub.h"
#include "z80_bus.h"
#include "psg.h"
#include "eeprom.h"
#include "vdp_timing.h"
#include "vdp_render.h"
#include "audio.h"
#include "controller.h"
static uint32_t mask_for(unsigned size) {
    return size==4 ? UINT32_MAX : (1u << (size*8))-1u;
}
static uint32_t sign_extend(uint32_t value, unsigned size) {
    uint32_t sign=1u << (size*8-1), mask=mask_for(size);
    value &= mask;
    return (value ^ sign)-sign;
}
static uint8_t io_read(CPU *c, unsigned reg) {
    /* Overseas hardware, revision 1 (TMSS), with 3-button pads. */
    if (reg==0) return c->vdp.pal ? 0xe1:0xa1;
    if (reg>=1 && reg<=3) {
        unsigned p=reg-1;
        unsigned th=(c->io_control[p]&0x40) ? c->io_data[p]&0x40 : 0x40;
        uint8_t pins=controller_pins(c->pad_buttons[p],!!th);
        unsigned mask=c->io_control[p]|0x80; /* D7 always reads its latch. */
        return (uint8_t)((c->io_data[p]&mask)|(pins&~mask));
    }
    if (reg>=4 && reg<=6) return c->io_control[reg-4];
    if (reg>=7 && reg<=15) {
        unsigned p=(reg-7)/3, kind=(reg-7)%3;
        if (kind==0) return c->io_tx[p];
        if (kind==2) return c->io_serial_control[p];
        return 0; /* No serial peripheral: receive buffer stays empty. */
    }
    fail(c,"invalid I/O register",0xa10000+reg*2); return 0;
}
static void io_write(CPU *c, unsigned reg, uint8_t value) {
    if (reg==0) return; /* Read-only hardware version register. */
    if (reg>=1 && reg<=3) { c->io_data[reg-1]=value; return; }
    if (reg>=4 && reg<=6) { c->io_control[reg-4]=value; return; }
    if (reg>=7 && reg<=15) {
        unsigned p=(reg-7)/3, kind=(reg-7)%3;
        if (kind==0) c->io_tx[p]=value;
        if (kind==2) {
            /* Baud/interrupt configuration is writable; status bits 0..2
             * are read-only. Serial pin operation still needs a UART. */
            c->io_serial_control[p]=value&0xf8;
            if (value&0x30) fail(c,"active serial communication not implemented",0xa10000+reg*2);
        }
        return; /* Receive data is read-only. */
    }
    fail(c,"invalid I/O register",0xa10000+reg*2);
}
static uint8_t read8(CPU *c, uint32_t address) {
    address &= 0xffffff;
    if (c->eeprom.enabled && (address==0x200000 || address==0x200001))
        return address&1 ? eeprom_read(c):0;
#if defined(GENESIS_RINGS_SAVES) && defined(GENESIS_SDL2)
    /* Read-only host copy of SYSTEM: 12-byte header, nine 14-byte rows.
       Original ROM and following QUIT table remain untouched. */
    if(c->rings_settings_enabled && address>=0x400000 && address<0x400000+138) {
        return rings_settings_rom_byte(c,address-0x400000);
    }
#endif
    if (address < c->rom_size) return c->rom[address];
    if (address >= 0xe00000) return c->ram[address & 0xffff];
    if (address>=0xa10000 && address<0xa10020) return io_read(c,(address-0xa10000)/2);
    if (z80_bus_address(address)) return z80_bus_read(c,address);
    if (address>=0xc00000 && address<0xc00020) {
        uint16_t value=vdp_port_read(c,address);
        return (uint8_t)(address&1 ? value:value>>8);
    }
    fail(c, "unmapped read / hardware device not implemented", address);
    return 0;
}
static void write8(CPU *c, uint32_t address, uint8_t value) {
    address &= 0xffffff;
    if (c->eeprom.enabled && (address==0x200000 || address==0x200001)) {
        if (address&1) eeprom_write(c,value);
        return;
    }
    if (address >= 0xe00000) {
#ifdef GENESIS_RINGS_SAVES
        unsigned at=address&0xffff;
        if(c->ram[at]!=value && ((at>=0x02b4 && at<0x02b4+56*52 && (at-0x02b4)%52<2) ||
                                (at>=0xb0cc && at<0xb0cc+56*12 && (at-0xb0cc)%12<2))) {
            ++c->rings_pool_revision;c->rings_pool_write_pc=c->pc;
        }
#endif
        c->ram[address & 0xffff]=value;return;
    }
    if (address>=0xa10000 && address<0xa10020) { io_write(c,(address-0xa10000)/2,value); return; }
    if (address>=0xa14000 && address<0xa14004) { c->tmss[address-0xa14000]=value; return; }
    if (z80_bus_address(address)) { z80_bus_write(c,address,value); return; }
    if (address>=0xc00000 && address<0xc00020) {
        /* A 68000 byte write replicates its byte on the VDP's 16-bit bus. */
        vdp_port_write(c,address,(uint16_t)((value<<8)|value)); return;
    }
    fail(c, address<c->rom_size ? "write to ROM" : "unmapped write / hardware device not implemented", address);
}
static uint32_t read_mem(CPU *c, uint32_t address, unsigned size) {
#ifdef GENESIS_RINGS_WIDE
    if(c->wide && c->wide->replaying && c->wide->grid>=14) {
        if(size==2) {
            if(c->pc==0x1baca)return (uint16_t)(196+14*((int)c->d[4]-(int)c->d[5]));
            if(c->pc==0x1bae4)return (uint16_t)(18+8*((int)c->d[4]+(int)c->d[5]-(c->wide->grid-10)));
        }
        if(size==1 && (c->pc==0x1bcd2 || c->pc==0x1bd1e)) {
            /* The original actor caches cover 32x32 cells. Extra terrain
               must not interpret neighboring RAM as actor index zero. */
            uint32_t base=c->pc==0x1bcd2 ? 0xffb36c:0xffb76c;
            uint32_t at=address&0xffffff;
            int32_t column=(int32_t)c->d[1];
            int32_t row=(int32_t)(c->d[0]-c->d[1])/32;
            if(column<0 || column>=32 || row<0 || row>=32 ||
               at<base || at>=base+1024)return 0xff;
        }
    }
#endif
    uint32_t value=0;
    if (size>1 && (address & 1)) { fail(c, "address error on read", address); return 0; }
    uint32_t bus_address=address&0xffffff;
    if (size>1 && bus_address>=0xc00000 && bus_address<0xc00020) {
        for (unsigned i=0; i<size && !c->fault; i+=2) value=(value<<16)|vdp_port_read(c,bus_address+i);
        return value;
    }
    for (unsigned i=0; i<size && !c->fault; ++i) value=(value<<8)|read8(c,address+i);
    return value;
}
static void write_mem(CPU *c, uint32_t address, unsigned size, uint32_t value) {
#if defined(GENESIS_RINGS_SAVES) && defined(GENESIS_SDL2)
    if(c->rings_settings_enabled && (address&0xffffff)==0xffbb82 && size==4 && value==0xccff4)
        value=0x400000;
#endif
    if (size>1 && (address & 1)) { fail(c, "address error on write", address); return; }
    uint32_t bus_address=address&0xffffff;
    if (size>1 && bus_address>=0xc00000 && bus_address<0xc00020) {
        for (unsigned i=0; i<size && !c->fault; i+=2) vdp_port_write(c,bus_address+i,(uint16_t)(value>>((size-i-2)*8)));
        return;
    }
    for (unsigned i=0; i<size && !c->fault; ++i) write8(c,address+i,(uint8_t)(value >> ((size-i-1)*8)));
}
#include "vdp.h"
#include "z80_runtime.h"
static void logic_flags(CPU *c, uint32_t value, unsigned size) {
    value &= mask_for(size);
    c->sr=(uint16_t)((c->sr & ~15u) | (value==0 ? F_Z:0) | (value & (1u<<(size*8-1)) ? F_N:0));
}
static uint32_t arithmetic(CPU *c, uint32_t dst, uint32_t src, unsigned size, int sub, int compare) {
    uint32_t mask=mask_for(size), sign=1u<<(size*8-1);
    dst &= mask; src &= mask;
    uint32_t result=(sub ? dst-src : dst+src)&mask;
    int carry=sub ? src>dst : (uint64_t)dst+src>mask;
    int overflow=!!((sub ? (dst^src)&(dst^result) : ~(dst^src)&(dst^result)) & sign);
    unsigned flags=(result==0 ? F_Z:0) | (result & sign ? F_N:0) | (carry ? F_C:0) | (overflow ? F_V:0);
    if (compare) c->sr=(uint16_t)((c->sr & ~15u)|flags);
    else c->sr=(uint16_t)((c->sr & ~31u)|flags|(carry ? F_X:0));
    return result;
}
static int64_t signed_bits(uint32_t value, unsigned size) {
    uint64_t range=UINT64_C(1)<<(size*8);
    value &= mask_for(size);
    return value >= range/2 ? (int64_t)value-(int64_t)range : (int64_t)value;
}
static uint32_t extended_arithmetic(CPU *c, uint32_t dst, uint32_t src, unsigned size, int sub) {
    uint32_t mask=mask_for(size), sign=1u<<(size*8-1), x=!!(c->sr&F_X);
    dst &= mask; src &= mask;
    uint32_t result=(uint32_t)(sub ? (uint64_t)dst-src-x : (uint64_t)dst+src+x)&mask;
    int carry=sub ? (uint64_t)src+x>dst : (uint64_t)dst+src+x>mask;
    int64_t mathematical=sub ? signed_bits(dst,size)-signed_bits(src,size)-x : signed_bits(dst,size)+signed_bits(src,size)+x;
    int overflow=mathematical < -(int64_t)sign || mathematical >= sign;
    unsigned flags=(result==0 && (c->sr&F_Z) ? F_Z:0) | (result&sign ? F_N:0) |
        (carry ? F_C|F_X:0) | (overflow ? F_V:0);
    c->sr=(uint16_t)((c->sr&~31u)|flags);
    return result;
}
static uint32_t bcd_arithmetic(CPU *c, uint32_t dst, uint32_t src, int sub) {
    uint32_t x=!!(c->sr&F_X);
    uint32_t low=sub ? (dst&15)-(src&15)-x : (dst&15)+(src&15)+x;
    if (low>9) low=sub ? low-6 : low+6;
    uint32_t decimal=sub ? low+(dst&0xf0)-(src&0xf0) : low+(dst&0xf0)+(src&0xf0);
    unsigned carry=decimal>0x99;
    if (carry) decimal=sub ? decimal+0xa0 : decimal-0xa0;
    uint32_t result=decimal&255;
    /* N/V are undefined by the MC68000 BCD instructions; preserve them. */
    unsigned flags=(result==0 && (c->sr&F_Z) ? F_Z:0)|(carry ? F_C|F_X:0);
    c->sr=(uint16_t)((c->sr&~(F_C|F_X|F_Z))|flags);
    return result;
}
static uint32_t bcd_negate(CPU *c, uint32_t value) {
    value &= 255;
    uint32_t complement=(0x9a-value-!!(c->sr&F_X))&255;
    if (complement==0x9a) {
        c->sr=(uint16_t)(c->sr&~(F_C|F_X));
        return value;
    }
    uint32_t result=((complement&15)==10 ? complement+6:complement)&255;
    unsigned flags=F_C|F_X|(result==0 && (c->sr&F_Z) ? F_Z:0);
    c->sr=(uint16_t)((c->sr&~(F_C|F_X|F_Z))|flags);
    return result;
}
static void set_sr(CPU *c, uint32_t sr) {
    if ((c->sr^sr)&0x2000) {
        if (c->sr&0x2000) { c->ssp=c->a[7]; c->a[7]=c->usp; }
        else { c->usp=c->a[7]; c->a[7]=c->ssp; }
    }
    c->sr=(uint16_t)(sr&0xa71f);
}
/* kind: 0 arithmetic, 1 logical, 2 rotate through X, 3 rotate. */
static uint32_t shift_value(CPU *c, uint32_t value, unsigned count, unsigned size, unsigned kind, int left) {
    uint32_t mask=mask_for(size), sign=1u<<(size*8-1);
    unsigned x=!!(c->sr&F_X), carry=kind==2 ? x:0, overflow=0;
    value &= mask;
    count &= 63;
    for (unsigned n=0; n<count; ++n) {
        unsigned oldsign=!!(value&sign);
        carry=left ? oldsign : value&1;
        uint32_t next=left ? (value<<1)&mask : value>>1;
        if (kind==0 && !left && oldsign) next|=sign;
        if (kind==2) next|=left ? x : (x ? sign:0);
        if (kind==3) next|=left ? carry : (carry ? sign:0);
        if (kind==0 && left && oldsign!=!!(next&sign)) overflow=1;
        if (kind!=3) x=carry;
        value=next;
    }
    unsigned flags=(value==0 ? F_Z:0)|(value&sign ? F_N:0)|(carry ? F_C:0)|(overflow ? F_V:0);
    c->sr=(uint16_t)((c->sr&~31u)|flags|(x ? F_X:0));
    return value;
}
static uint32_t divide_value(CPU *c, uint32_t dividend, uint32_t divisor, int is_signed) {
    divisor &= 0xffff;
    if (!divisor) { fail(c,"division by zero exception not implemented",c->pc); return dividend; }
    int64_t d=is_signed ? signed_bits(dividend,4) : (int64_t)dividend;
    int64_t s=is_signed ? signed_bits(divisor,2) : (int64_t)divisor;
    int64_t quotient=d/s, remainder=d%s;
    if (is_signed ? quotient < -32768 || quotient > 32767 : quotient>65535) {
        c->sr=(uint16_t)((c->sr&~15u)|F_V); return dividend;
    }
    logic_flags(c,(uint32_t)quotient,2);
    return ((uint32_t)remainder&0xffff)<<16 | ((uint32_t)quotient&0xffff);
}
static void movem(CPU *c, unsigned mask, uint32_t address, unsigned mode, unsigned base, unsigned size, int load) {
    uint32_t registers[16];
    for (unsigned r=0; r<8; ++r) { registers[r]=c->d[r]; registers[r+8]=c->a[r]; }
    for (unsigned bit=0; bit<16; ++bit) {
        if (!(mask&(1u<<bit))) continue;
        unsigned reg=!load && mode==4 ? 15-bit:bit;
        if (!load && mode==4) address-=size;
        if (load) {
            uint32_t value=read_mem(c,address,size);
            if (c->fault) return;
            if (size==2) value=sign_extend(value,2);
            if (reg<8) c->d[reg]=value; else c->a[reg-8]=value;
        } else {
            write_mem(c,address,size,registers[reg]);
            if (c->fault) return;
        }
        if (load || mode!=4) address+=size;
    }
    if (mode==3 || mode==4) c->a[base]=address;
}
static int condition(CPU *c, unsigned cond) {
    int n=!!(c->sr&F_N), z=!!(c->sr&F_Z), v=!!(c->sr&F_V), carry=!!(c->sr&F_C);
    switch (cond) {
        case 0:return 1; case 1:return 0;
        case 2:return !carry&&!z; case 3:return carry||z;
        case 4:return !carry; case 5:return carry;
        case 6:return !z; case 7:return z;
        case 8:return !v; case 9:return v;
        case 10:return !n; case 11:return n;
        case 12:return n==v; case 13:return n!=v;
        case 14:return !z&&n==v; case 15:return z||n!=v;
    }
    return 0;
}
static uint32_t index_value(CPU *c, unsigned extension) {
    uint32_t value=extension&0x8000 ? c->a[(extension>>12)&7] : c->d[(extension>>12)&7];
    return extension&0x0800 ? value : sign_extend(value,2);
}
static void push32(CPU *c, uint32_t value) { c->a[7]-=4; write_mem(c,c->a[7],4,value); }
static uint32_t pop32(CPU *c) { uint32_t value=read_mem(c,c->a[7],4); if (!c->fault) c->a[7]+=4; return value; }
/* Defined by the generated translation. */
static void translated_step(CPU *c);
#include "rings_wide_render.h"
#include "scheduler.h"
#include "rings_saves.h"
#include "sdl_frontend.h"

#ifndef GENESIS_NO_MAIN
static int parse_number(const char *s, uint64_t *out) {
    char *end;
    if (!*s || *s=='-') return 0;
    errno=0;
    unsigned long long value=strtoull(s,&end,0);
    if (errno || *end) return 0;
    *out=(uint64_t)value; return 1;
}
static int run_main(int argc, char **argv, const uint8_t *rom, size_t size, int ea_eeprom) {
    uint64_t limit=1000000, peek=0; int have_peek=0, trace=0, audio_mode=AUDIO_STRICT;
    int window=0, limit_set=0, user_closed=0, host_error=0, no_throttle=0, pal=0;
    const char *font_path=NULL;
#ifdef GENESIS_RINGS_SAVES
    const char *save_directory=NULL;int autosave=1,load_slot=-1,save_slot=-1;
#endif
    int widescreen=0,zoom=0;const char *wide_dump=NULL;
    int mouse=0,smooth_camera=0;
#ifdef GENESIS_RINGS_SMOOTH_CAMERA
    uint64_t smooth_ms=200;
#endif
    const char *vram_dump=NULL, *z80_dump=NULL, *frame_dump=NULL, *audio_dump=NULL;
    for (int i=1; i<argc; ++i) {
        if (!strcmp(argv[i],"--limit") && i+1<argc) {
            if (!parse_number(argv[++i],&limit)) goto usage;
            limit_set=1;
        } else if (!strcmp(argv[i],"--peek") && i+1<argc) {
            if (!parse_number(argv[++i],&peek) || peek>0xffffff) goto usage;
            have_peek=1;
        } else if (!strcmp(argv[i],"--trace")) trace=1;
        else if (!strcmp(argv[i],"--region") && i+1<argc) {
            const char *region=argv[++i];
            if (!strcmp(region,"ntsc")) pal=0;
            else if (!strcmp(region,"pal")) pal=1;
            else goto usage;
        }
        else if (!strcmp(argv[i],"--audio") && i+1<argc) {
            const char *mode=argv[++i];
            if (!strcmp(mode,"stub")) audio_mode=AUDIO_STUB;
            else if (!strcmp(mode,"strict")) audio_mode=AUDIO_STRICT;
            else if (!strcmp(mode,"mute")) audio_mode=AUDIO_MUTE;
            else if (!strcmp(mode,"on")) audio_mode=AUDIO_ON;
            else goto usage;
        }
        else if (!strcmp(argv[i],"--window")) {
#ifdef GENESIS_SDL2
            window=1;
#else
            fprintf(stderr,"window support is not compiled in; rebuild with --frontend sdl2\n");
            return 64;
#endif
        }
        else if (!strcmp(argv[i],"--font") && i+1<argc) {
#ifdef GENESIS_RINGS_MENU_FONT
            font_path=argv[++i]; if(!*font_path)goto usage;
#else
            fprintf(stderr,"external font support is not compiled in; rebuild Rings of Power with --text-renderer rings-text\n");return 64;
#endif
        }
        else if (!strcmp(argv[i],"--widescreen")) {
#ifdef GENESIS_RINGS_WIDE
            widescreen=1;
#else
            fprintf(stderr,"widescreen support is not compiled in; rebuild Rings of Power with --widescreen\n");return 64;
#endif
        }
        else if (!strcmp(argv[i],"--dump-wide-frame") && i+1<argc)wide_dump=argv[++i];
        else if (!strcmp(argv[i],"--zoom")) {
#ifdef GENESIS_RINGS_WIDE
            zoom=1;
#else
            fprintf(stderr,"zoom support is not compiled in; rebuild Rings of Power with --zoom\n");return 64;
#endif
        }
        else if (!strcmp(argv[i],"--mouse")) {
#if defined(GENESIS_RINGS_WIDE) && defined(GENESIS_SDL2)
            mouse=1;zoom=1;
#else
            fprintf(stderr,"mouse support requires a Rings SDL2 build with --zoom or --widescreen\n");return 64;
#endif
        }
#ifdef GENESIS_RINGS_SAVES
        else if (!strcmp(argv[i],"--save-dir") && i+1<argc) {save_directory=argv[++i];if(!*save_directory)goto usage;}
        else if (!strcmp(argv[i],"--no-autosave"))autosave=0;
        else if (!strcmp(argv[i],"--load-slot") && i+1<argc) {load_slot=rings_save_slot_number(argv[++i]);if(load_slot<0)goto usage;}
        else if (!strcmp(argv[i],"--save-slot") && i+1<argc) {save_slot=rings_save_slot_number(argv[++i]);if(save_slot<0 || save_slot>=5)goto usage;}
#endif
        else if (!strcmp(argv[i],"--smooth-camera")) {
#ifdef GENESIS_RINGS_SMOOTH_CAMERA
            smooth_camera=1;zoom=1;
#else
            fprintf(stderr,"smooth camera support is not compiled in; rebuild Rings with --smooth-camera\n");return 64;
#endif
        }
#ifdef GENESIS_RINGS_SMOOTH_CAMERA
        else if (!strcmp(argv[i],"--camera-smooth-ms") && i+1<argc) {
            if(!parse_number(argv[++i],&smooth_ms) || smooth_ms<60 || smooth_ms>500)goto usage;
        }
#endif
        else if (!strcmp(argv[i],"--headless")) window=0;
        else if (!strcmp(argv[i],"--no-throttle")) no_throttle=1;
        else if (!strcmp(argv[i],"--dump-audio") && i+1<argc) audio_dump=argv[++i];
        else if (!strcmp(argv[i],"--resources-dir") && i+1<argc) {
#ifdef GENESIS_EXTERNAL_RESOURCES
            if(!argv[++i][0])goto usage;
#else
            fprintf(stderr,"this binary has embedded resources; rebuild with --resources-dir\n");return 64;
#endif
        }
        else if (!strcmp(argv[i],"--dump-vram") && i+1<argc) vram_dump=argv[++i];
        else if (!strcmp(argv[i],"--dump-z80") && i+1<argc) z80_dump=argv[++i];
        else if (!strcmp(argv[i],"--dump-frame") && i+1<argc) frame_dump=argv[++i];
        else goto usage;
    }
#ifdef GENESIS_RINGS_SMOOTH_CAMERA
    if(smooth_ms!=200 && !smooth_camera) {fprintf(stderr,"--camera-smooth-ms requires --smooth-camera\n");return 64;}
#endif
    if(font_path && !window) { fprintf(stderr,"--font requires --window\n");return 64; }
#if defined(GENESIS_RINGS_WIDE) && defined(GENESIS_SDL2)
    if(mouse && !window) {fprintf(stderr,"--mouse requires --window\n");return 64;}
#endif
    if(zoom && !window) { fprintf(stderr,"--zoom requires --window\n");return 64; }
    if(wide_dump && !widescreen) { fprintf(stderr,"--dump-wide-frame requires --widescreen\n");return 64; }
    if (no_throttle && !window) goto usage;
    if (audio_dump && audio_mode!=AUDIO_ON) goto usage;
#ifndef GENESIS_AUDIO
    if (audio_mode==AUDIO_ON) {
        fprintf(stderr,"sound support is not compiled in; rebuild with --sound ymfm\n");return 64;
    }
#endif
    if (window && !limit_set) limit=UINT64_MAX;
    CPU c={0}; c.rom=rom; c.rom_size=size; c.sr=0x2700;
#ifdef GENESIS_RINGS_WIDE
    RingsWide wide={0};
#endif
    c.io_tx[0]=c.io_tx[1]=0xff; c.io_tx[2]=0xfb;
    c.vdp.pal=(uint8_t)pal;
    c.eeprom.enabled=(uint8_t)ea_eeprom;
    c.audio_mode=audio_mode;
    if(audio_mode==AUDIO_ON && !audio_init(&c,audio_dump)) {
        fprintf(stderr,"audio initialization failed: %s\n",c.reason ? c.reason:"cannot write WAV header");
        audio_finish(&c);return 1;
    }
#ifdef GENESIS_RINGS_SAVES
    RingsSaves saves={0};rings_saves_open(&saves,&c,save_directory,autosave);
    if(!saves.enabled && (load_slot>=0 || save_slot>=0)) {audio_finish(&c);return 1;}
#endif
    c.a[7]=read_mem(&c,0,4); c.ssp=c.a[7]; c.pc=read_mem(&c,4,4)&0xffffff;
#ifdef GENESIS_SDL2
    SDLHost host={0};
#ifdef GENESIS_RINGS_SMOOTH_CAMERA
    host.camera.enabled=smooth_camera;host.camera.duration_ms=(unsigned)smooth_ms;
#endif
#ifdef GENESIS_RINGS_SAVES
    host.saves=&saves;
#endif
    host.no_throttle=no_throttle;host.wide_window=widescreen;
    if (window && !sdl_host_open(&host)) { sdl_host_close(&host); audio_finish(&c); return 1; }
#ifdef GENESIS_RINGS_WIDE
    host.mouse.enabled=mouse;
#endif
#ifdef GENESIS_RINGS_MENU_FONT
    if(window && font_path) {
        if(!rings_font_open(&host.font,font_path)) {
            fprintf(stderr,"cannot load external font '%s': %s\n",font_path,TTF_GetError());
            sdl_host_close(&host);audio_finish(&c);return 1;
        }
        c.vdp.font_enabled=1;
        for(unsigned ch=32;ch<127;++ch)
            c.vdp.font_supported[ch]=(uint8_t)!!TTF_GlyphIsProvided(host.font.font,(Uint16)ch);
    }
#endif
    if (window && audio_mode==AUDIO_ON) sdl_host_audio_open(&host,&c);
#endif
#ifdef GENESIS_RINGS_WIDE
    int presentation_requested=widescreen || zoom;
#if defined(GENESIS_RINGS_SAVES) && defined(GENESIS_SDL2)
    presentation_requested|=window;
#endif
    if(presentation_requested && !rings_wide_open(&c,&wide)) {
        fprintf(stderr,"cannot allocate Rings world presentation state\n");
#ifdef GENESIS_SDL2
        if(window)sdl_host_close(&host);
#endif
        audio_finish(&c);return 1;
    }
    c.vdp.wide_enabled=(uint8_t)widescreen;c.vdp.zoom_enabled=(uint8_t)zoom;
#endif
#if defined(GENESIS_RINGS_SAVES) && defined(GENESIS_SDL2)
    if(window)rings_settings_init(&host,&c,widescreen,zoom,mouse,smooth_camera);
#endif
#ifdef GENESIS_RINGS_SAVES
    if(load_slot>=0 && !rings_save_load(&saves,&c,load_slot)) {
#ifdef GENESIS_SDL2
        if(window)sdl_host_close(&host);
#endif
#ifdef GENESIS_RINGS_WIDE
        rings_wide_close(&c);
#endif
        audio_finish(&c);return 1;
    }
#ifdef GENESIS_SDL2
    if(window && saves.loaded)rings_save_host_loaded(&host,&c);
#endif
    uint64_t run_steps=0;
    while(run_steps<limit) {
        if(rings_save_observe(&saves,&c,window)) {
#ifdef GENESIS_SDL2
            sdl_host_rebase(&host,&c);
#endif
        }
#else
    while (c.steps<limit) {
#endif
#ifdef GENESIS_SDL2
        if (window) {
#ifdef GENESIS_RINGS_SAVES
            rings_settings_observe(&host,&c);
#endif
            int stopped=c.fault || (c.halted && !machine_can_wake(&c));
            if (c.master_cycles>=host.next_service || host.paused || stopped
#ifdef GENESIS_RINGS_SAVES
                || saves.menu || host.settings.menu
#endif
            ) {
                if (!sdl_host_service(&host,&c)) { user_closed=!host.error; host_error=host.error; break; }
            }
            stopped=c.fault || (c.halted && !machine_can_wake(&c));
            if (stopped && !limit_set) { sdl_host_stop(&host,&c); SDL_Delay(10); continue; }
            if (host.paused
#ifdef GENESIS_RINGS_SAVES
                || saves.menu || host.settings.menu
#endif
            ) { SDL_Delay(10); continue; }
        }
#endif
        if (c.fault) break;
        if (c.halted && !machine_can_wake(&c)) break;
#if defined(GENESIS_RINGS_WIDE) && defined(GENESIS_SDL2)
        if(window)rings_mouse_observe(&host,&c);
#endif
        if (trace) fprintf(stderr,"step=%" PRIu64 " pc=%06" PRIx32 " sr=%04x D0=%08" PRIx32 " A7=%08" PRIx32 "\n",c.steps,c.pc,c.sr,c.d[0],c.a[7]);
#ifdef GENESIS_RINGS_SAVES
        uint64_t before_steps=c.steps;
#endif
        machine_step(&c);
#ifdef GENESIS_RINGS_SAVES
        run_steps+=c.steps-before_steps;
#endif
    }
#ifdef GENESIS_RINGS_SAVES
    if(save_slot>=0 && !rings_save_write(&saves,&c,save_slot))host_error=1;
#endif
#ifdef GENESIS_SDL2
    if (window) sdl_host_close(&host);
#endif
#ifdef GENESIS_RINGS_WIDE
    rings_wide_close(&c);
#endif
    if(!audio_finish(&c))fail(&c,"cannot finalize audio WAV",c.pc);
    int terminal_halt=c.halted && !machine_can_wake(&c);
    printf("status=%s steps=%" PRIu64 " pc=%06" PRIx32 " sr=%04x\n", c.fault || host_error ? "fault" : user_closed ? "closed" : terminal_halt ? "halted" : "budget",c.steps,c.pc,c.sr);
    for (unsigned i=0; i<8; ++i) printf("D%u=%08" PRIx32 " A%u=%08" PRIx32 "\n",i,c.d[i],i,c.a[i]);
    printf("timing cycles=%" PRIu64 " master=%" PRIu64 " frames=%" PRIu64 " line=%u clock=%u interrupts=%" PRIu64 "\n",c.cycles,c.master_cycles,c.vdp.frames,c.vdp.line,c.vdp.line_clock,c.interrupts);
    if (pal) printf("console region=pal master_hz=%u lines_per_frame=%u\n",vdp_master_frequency(&c.vdp),vdp_frame_lines(&c.vdp));
    if (audio_mode!=AUDIO_STRICT) printf("audio mode=%s z80_execution=%s ym_writes=%" PRIu64 "\n",audio_mode==AUDIO_STUB ? "stub":audio_mode==AUDIO_MUTE ? "mute":"on",audio_mode==AUDIO_STUB ? "disabled":"enabled",c.ym2612_stub.writes);
#if defined(GENESIS_RINGS_SMOOTH_CAMERA) && defined(GENESIS_SDL2)
    if(window && smooth_camera)printf("camera transitions=%" PRIu64 " motion_frames=%" PRIu64 " duration_ms=%u\n",host.camera.transitions,host.camera.motion_frames,host.camera.duration_ms);
#endif
    if(audio_mode==AUDIO_ON)printf("sound samples=%" PRIu64 " rate=%u channels=2 peak=%u dropped=%" PRIu64 "\n",c.audio.frames,AUDIO_RATE,c.audio.peak,c.audio.dropped);
#ifdef GENESIS_RINGS_MENU_FONT
    if(font_path)printf("text renderer=rings-text captured=%" PRIu64 "+%" PRIu64 " visible=%u\n",
        c.vdp.font_captured[0],c.vdp.font_captured[1],c.vdp.font_visible);
#endif
#ifdef GENESIS_RINGS_WIDE
    if(widescreen)printf("wide mode=rings-experimental size=%ux%u scenes=%" PRIu64 " failures=%" PRIu64 " world=%u\n",
        rings_view_width(&c.vdp),c.vdp.frame_height,wide.scenes,wide.failures,c.vdp.wide_world_visible);
#ifdef GENESIS_SDL2
    if(mouse)printf("mouse mode=rings starts=%" PRIu64 " direction_reads=%" PRIu64 "\n",host.mouse.starts,host.mouse.reads);
    if(zoom)printf("zoom mode=rings-viewport scale=%u%% size=%ux%u scenes=%" PRIu64 " failures=%" PRIu64 " world=%u\n",
        c.vdp.native_scene ? 100:host.zoom_percent,rings_view_width(&c.vdp),c.vdp.frame_height,wide.scenes,wide.failures,c.vdp.zoom_world_visible);
#endif
#endif
    if (have_peek) printf("mem[%06" PRIx64 "]=%08" PRIx32 "\n",peek,read_mem(&c,(uint32_t)peek,4));
    if (c.fault) fprintf(stderr,"fault at %06" PRIx32 ": %s\n",c.fault_address,c.reason);
    if (vram_dump) {
        FILE *f=fopen(vram_dump,"wb");
        if (!f) { fprintf(stderr,"cannot open VRAM dump: %s\n",strerror(errno)); return 1; }
        size_t written=fwrite(c.vdp.vram,1,sizeof c.vdp.vram,f);
        int closed=fclose(f);
        if (written!=sizeof c.vdp.vram || closed) { fprintf(stderr,"cannot write VRAM dump\n"); return 1; }
        printf("vdp data_writes=%" PRIu64 " dma_bytes=%" PRIu64 " address=%04x\n",c.vdp.data_writes,c.vdp.dma_bytes,c.vdp.address);
    }
    if (z80_dump) {
        FILE *f=fopen(z80_dump,"wb");
        if (!f) { fprintf(stderr,"cannot open Z80 dump: %s\n",strerror(errno)); return 1; }
        size_t written=fwrite(c.z80_bus.ram,1,sizeof c.z80_bus.ram,f);
        int closed=fclose(f);
        if (written!=sizeof c.z80_bus.ram || closed) { fprintf(stderr,"cannot write Z80 dump\n"); return 1; }
        printf("z80 ram_writes=%" PRIu64 " bus_request=%u reset_released=%u\n",c.z80_bus.ram_writes,c.z80_bus.requested,c.z80_bus.reset_released);
        printf("z80 steps=%" PRIu64 " cycles=%" PRIu64 " pc=%04x sp=%04x psg_writes=%" PRIu64 "\n",c.z80_cpu.steps,c.z80_cpu.cycles,c.z80_cpu.pc,c.z80_cpu.sp,c.psg.writes);
        printf("z80 interrupts=%" PRIu64 " ei_delay=%u irq_line=%u\n",c.z80_cpu.interrupts,c.z80_cpu.ei_delay,c.z80_cpu.irq_line);
    }
    if (frame_dump) {
        if (!c.vdp.rendered_frames) { fprintf(stderr,"no supported visible frame has been rendered\n"); return 1; }
        FILE *f=fopen(frame_dump,"wb");
        if (!f) { fprintf(stderr,"cannot open frame dump: %s\n",strerror(errno)); return 1; }
        int header=fprintf(f,"P6\n%u %u\n255\n",c.vdp.frame_width,c.vdp.frame_height);
        size_t bytes=(size_t)c.vdp.frame_width*c.vdp.frame_height*3;
        size_t written=fwrite(c.vdp.frame,1,bytes,f); int closed=fclose(f);
        if (header<0 || written!=bytes || closed) { fprintf(stderr,"cannot write frame dump\n"); return 1; }
        printf("video rendered_frames=%" PRIu64 " size=%ux%u unsupported_mode=%u\n",c.vdp.rendered_frames,c.vdp.frame_width,c.vdp.frame_height,c.vdp.render_unsupported);
    }
#ifdef GENESIS_RINGS_WIDE
    if(wide_dump) {
        if(!c.vdp.rendered_frames) {fprintf(stderr,"no supported visible wide frame has been rendered\n");return 1;}
        FILE *f=fopen(wide_dump,"wb");
        if(!f) {fprintf(stderr,"cannot open wide frame dump: %s\n",strerror(errno));return 1;}
        int header=fprintf(f,"P6\n%u %u\n255\n",RINGS_WIDE_WIDTH,c.vdp.frame_height);
        size_t bytes=(size_t)RINGS_WIDE_WIDTH*c.vdp.frame_height*3;
        size_t written=fwrite(c.vdp.wide_frame,1,bytes,f);int closed=fclose(f);
        if(header<0 || written!=bytes || closed) {fprintf(stderr,"cannot write wide frame dump\n");return 1;}
    }
#endif
    return c.fault || host_error ? 1 : user_closed || terminal_halt ? 0 : 2;
usage:
#ifdef GENESIS_RINGS_SAVES
    fprintf(stderr,"save options: --save-dir directory --no-autosave --load-slot manual-1..5|auto-1..5 --save-slot manual-1..5\n");
#endif
    fprintf(stderr,"usage: %s [--window|--headless] [--no-throttle] [--region ntsc|pal] [--limit instruction-count] [--peek address] [--trace] [--audio strict|stub|mute|on] [--dump-audio file.wav] [--resources-dir directory] [--dump-vram file] [--dump-z80 file] [--dump-frame file.ppm] [--font font-file] [--widescreen] [--zoom] [--mouse] [--dump-wide-frame file.ppm] [--smooth-camera] [--camera-smooth-ms 60..500]\n",argv[0]); return 64;
}
#endif
#endif
