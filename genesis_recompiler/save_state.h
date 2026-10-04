/* Pointer-free, little-endian versioned machine snapshots for Rings saves.
   Host files, SDL resources, ROM data and the shadow CPU are never persisted. */
#ifndef GENESIS_SAVE_STATE_H
#define GENESIS_SAVE_STATE_H
#ifdef GENESIS_RINGS_SAVES
enum { SAVE_MAX_BYTES=16*1024*1024, SAVE_HEADER_BYTES=64 };
typedef struct {uint8_t *data;size_t size,capacity,pos;int reading,error;} SaveCodec;
static void save_bytes(SaveCodec *s,void *data,size_t size) {
    if(s->error || size>SAVE_MAX_BYTES || s->pos>SAVE_MAX_BYTES-size) {s->error=1;return;}
    if(s->reading) {
        if(s->pos>s->size || size>s->size-s->pos) {s->error=1;return;}
        memcpy(data,s->data+s->pos,size);
    } else {
        size_t end=s->pos+size;
        if(end>s->capacity) {
            size_t capacity=s->capacity ? s->capacity:4096;
            while(capacity<end)capacity*=2;
            uint8_t *next=realloc(s->data,capacity);
            if(!next) {s->error=1;return;}
            s->data=next;s->capacity=capacity;
        }
        memcpy(s->data+s->pos,data,size);if(end>s->size)s->size=end;
    }
    s->pos+=size;
}
static uint64_t save_scalar(SaveCodec *s,uint64_t value,unsigned width) {
    uint8_t bytes[8]={0};
    if(!s->reading)for(unsigned i=0;i<width;++i)bytes[i]=(uint8_t)(value>>(i*8));
    save_bytes(s,bytes,width);value=0;
    for(unsigned i=0;i<width;++i)value|=(uint64_t)bytes[i]<<(i*8);
    return value;
}
#define SAVE_U8(v) do { (v)=(uint8_t)save_scalar(s,(uint8_t)(v),1); } while(0)
#define SAVE_U16(v) do { (v)=(uint16_t)save_scalar(s,(uint16_t)(v),2); } while(0)
#define SAVE_U32(v) do { (v)=(uint32_t)save_scalar(s,(uint32_t)(v),4); } while(0)
#define SAVE_U64(v) do { (v)=save_scalar(s,(uint64_t)(v),8); } while(0)
#define SAVE_I32(v) do { (v)=(int32_t)save_scalar(s,(uint32_t)(v),4); } while(0)
#define SAVE_I64(v) do { (v)=(int64_t)save_scalar(s,(uint64_t)(v),8); } while(0)
#define SAVE_RAW(v) save_bytes(s,(v),sizeof(v))
#define SAVE_ARRAY(v,kind) do {for(unsigned si=0;si<sizeof(v)/sizeof(*(v));++si)kind((v)[si]);} while(0)
static void save_core(SaveCodec *s,CPU *c) {
    SAVE_ARRAY(c->d,SAVE_U32);SAVE_ARRAY(c->a,SAVE_U32);SAVE_U32(c->pc);
    SAVE_U32(c->usp);SAVE_U32(c->ssp);SAVE_U16(c->sr);SAVE_RAW(c->ram);
    SAVE_RAW(c->io_data);SAVE_RAW(c->io_control);SAVE_RAW(c->tmss);SAVE_RAW(c->io_tx);
    SAVE_RAW(c->io_serial_control);SAVE_RAW(c->pad_buttons);
    SAVE_U64(c->steps);SAVE_U64(c->cycles);SAVE_U64(c->master_cycles);SAVE_U64(c->interrupts);
    SAVE_U32(c->instruction_cycles);SAVE_U32(c->z80_divider);SAVE_U8(c->halted);SAVE_U8(c->audio_mode);
    VDP *v=&c->vdp;
    SAVE_RAW(v->registers);SAVE_RAW(v->vram);SAVE_ARRAY(v->cram,SAVE_U16);SAVE_ARRAY(v->vsram,SAVE_U16);
    SAVE_U16(v->address);SAVE_U16(v->bus_value);SAVE_U8(v->code);SAVE_U8(v->command_pending);SAVE_U8(v->fill_pending);
    SAVE_U64(v->data_reads);SAVE_U64(v->data_writes);SAVE_U64(v->dma_bytes);
    SAVE_U16(v->line);SAVE_U16(v->line_clock);SAVE_U8(v->hint_counter);SAVE_U8(v->irq_h);SAVE_U8(v->irq_v);
    SAVE_U8(v->vint_status);SAVE_U8(v->pal);SAVE_U64(v->frames);SAVE_RAW(v->frame);
    SAVE_U8(v->render_unsupported);SAVE_U16(v->frame_width);SAVE_U16(v->frame_height);SAVE_U64(v->rendered_frames);
    Z80Bus *b=&c->z80_bus;
    SAVE_RAW(b->ram);SAVE_U8(b->requested);SAVE_U8(b->reset_released);SAVE_U16(b->bank);SAVE_U64(b->ram_writes);
    Z80CPU *z=&c->z80_cpu;
    SAVE_RAW(z->r8);SAVE_RAW(z->alternate);SAVE_U8(z->a);SAVE_U8(z->f);SAVE_U8(z->a_alt);SAVE_U8(z->f_alt);
    SAVE_U8(z->i);SAVE_U8(z->r);SAVE_U8(z->iff1);SAVE_U8(z->iff2);SAVE_U8(z->im);SAVE_U8(z->halted);
    SAVE_U8(z->irq_line);SAVE_U8(z->ei_delay);SAVE_U16(z->pc);SAVE_U16(z->sp);SAVE_U16(z->ix);SAVE_U16(z->iy);
    SAVE_U16(z->wz);SAVE_I64(z->debt);SAVE_U64(z->steps);SAVE_U64(z->cycles);SAVE_U64(z->interrupts);
    PSG *p=&c->psg;
    SAVE_ARRAY(p->tone,SAVE_U16);SAVE_RAW(p->volume);SAVE_U8(p->noise);SAVE_U8(p->latch);SAVE_U16(p->noise_lfsr);
    SAVE_U64(p->writes);SAVE_ARRAY(p->counter,SAVE_U16);SAVE_U8(p->polarity);SAVE_U64(p->cursor);
    SAVE_U64(p->next_tick);SAVE_I64(p->area);
    EEPROM *e=&c->eeprom;
    SAVE_RAW(e->data);SAVE_RAW(e->pending);SAVE_U8(e->dirty);SAVE_U8(e->page);SAVE_U8(e->enabled);SAVE_U8(e->initialized);
    SAVE_U8(e->sda);SAVE_U8(e->scl);SAVE_U8(e->output);SAVE_U8(e->phase);SAVE_U8(e->bits);SAVE_U8(e->shift);
    SAVE_U8(e->address);SAVE_U8(e->reading);SAVE_U8(e->ack_clock);SAVE_U8(e->master_ack);
    SAVE_U64(e->starts);SAVE_U64(e->stops);SAVE_U64(e->reads);SAVE_U64(e->writes);
    SAVE_RAW(c->ym2612_stub.address);SAVE_RAW(c->ym2612_stub.registers);SAVE_U64(c->ym2612_stub.writes);
    Audio *a=&c->audio;
    SAVE_U64(a->cursor);SAVE_U64(a->next_sample);SAVE_U64(a->sample_index);SAVE_U64(a->frames);
    SAVE_ARRAY(a->previous_input,SAVE_I32);SAVE_ARRAY(a->filter,SAVE_I32);SAVE_U32(a->peak);SAVE_U8(a->initialized);
}
#ifdef GENESIS_RINGS_MENU_FONT
static void save_font(SaveCodec *s,VDP *v) {
    for(unsigned i=0;i<32768;++i) {
        RingsTextMark *m=&v->font_marks[i];SAVE_U32(m->pattern);SAVE_U32(m->run);SAVE_U16(m->entry);SAVE_U8(m->ch);
    }
    for(unsigned i=0;i<1200;++i) {
        RingsTextVisible *m=&v->font_cells[i];SAVE_U32(m->run);SAVE_U16(m->x);SAVE_U16(m->y);
        SAVE_U8(m->ch);SAVE_U8(m->layer);SAVE_RAW(m->rgb);
    }
    SAVE_U8(v->font_hide);SAVE_U16(v->font_count);SAVE_U16(v->font_visible);SAVE_RAW(v->font_mask);SAVE_RAW(v->font_frame);
    SAVE_ARRAY(v->font_captured,SAVE_U64);SAVE_U32(v->font_run);SAVE_U32(v->font_source);
    SAVE_U32(v->font_frame_pointer);SAVE_U32(v->font_offset);SAVE_U16(v->font_attributes);
    SAVE_U16(v->font_bank);SAVE_U8(v->font_writer);
}
#endif
#ifdef GENESIS_RINGS_WIDE
static void save_wide_video(SaveCodec *s,VDP *v) {
    SAVE_U8(v->wide_world_visible);SAVE_RAW(v->wide_frame);
#ifdef GENESIS_RINGS_MENU_FONT
    SAVE_RAW(v->wide_font_frame);
#endif
    SAVE_U8(v->zoom_world_visible);
    SAVE_U16(v->zoom_focus_x);SAVE_U16(v->zoom_focus_y);SAVE_RAW(v->zoom_scene);SAVE_RAW(v->zoom_mask);
    SAVE_RAW(v->zoom_restore);SAVE_RAW(v->zoom_lift);SAVE_RAW(v->zoom_background);SAVE_RAW(v->zoom_palette);
}
static void save_wide(SaveCodec *s,RingsWide *w) {
    SAVE_RAW(w->work);SAVE_RAW(w->scene);SAVE_RAW(w->zoom_work);SAVE_RAW(w->zoom_scene);
    SAVE_RAW(w->lift_work);SAVE_RAW(w->lift_scene);SAVE_I32(w->tile_ground_y);SAVE_I32(w->resource_ground);
    SAVE_U8(w->resource_actor);SAVE_U8(w->zoom_pending);SAVE_U8(w->zoom_valid);SAVE_U8(w->grid);
    SAVE_U8(w->pending);SAVE_U8(w->valid);SAVE_U8(w->tracking_hero);SAVE_U16(w->bank);
    SAVE_U16(w->work_focus_x);SAVE_U16(w->work_focus_y);SAVE_U16(w->focus_x);SAVE_U16(w->focus_y);
    SAVE_U64(w->scenes);SAVE_U64(w->failures);SAVE_U64(w->submissions);
}
#endif
#undef SAVE_U8
#undef SAVE_U16
#undef SAVE_U32
#undef SAVE_U64
#undef SAVE_I32
#undef SAVE_I64
#undef SAVE_RAW
#undef SAVE_ARRAY
static uint64_t save_rom_hash(const CPU *c) {
    uint64_t hash=UINT64_C(14695981039346656037);
    for(size_t i=0;i<c->rom_size;++i)hash=(hash^c->rom[i])*UINT64_C(1099511628211);
    return hash;
}
static uint32_t save_crc(const uint8_t *p,size_t size) {
    uint32_t crc=~0u;
    for(size_t i=0;i<size;++i) {
        crc^=p[i];for(unsigned b=0;b<8;++b)crc=(crc>>1)^(0xedb88320u&(0u-(crc&1)));
    }
    return ~crc;
}
static void save_put(uint8_t *p,uint64_t value,unsigned width) {
    for(unsigned i=0;i<width;++i)p[i]=(uint8_t)(value>>(i*8));
}
static uint64_t save_get(const uint8_t *p,unsigned width) {
    uint64_t value=0;for(unsigned i=0;i<width;++i)value|=(uint64_t)p[i]<<(i*8);return value;
}
static size_t save_section(SaveCodec *s,unsigned tag) {
    save_scalar(s,tag,4);size_t at=s->pos;save_scalar(s,0,4);return at;
}
static void save_section_end(SaveCodec *s,size_t at) {
    if(!s->error)save_put(s->data+at,s->pos-at-4,4);
}
static int save_valid(const CPU *c);
static int save_encode(CPU *c,SaveCodec *s) {
    if(c->fault || !save_valid(c))return 0;
    size_t at=save_section(s,1);save_core(s,c);save_section_end(s,at);
#ifdef GENESIS_RINGS_MENU_FONT
    at=save_section(s,2);save_font(s,&c->vdp);save_section_end(s,at);
#endif
#ifdef GENESIS_RINGS_WIDE
    at=save_section(s,3);save_wide_video(s,&c->vdp);save_section_end(s,at);
    if(c->wide) {at=save_section(s,4);save_wide(s,c->wide);save_section_end(s,at);}
    /* Optional presentation flag. Old files omit it; old readers skip it. */
    at=save_section(s,6);save_scalar(s,c->vdp.wide_hud_active,1);save_section_end(s,at);
#endif
    if(c->audio_mode==AUDIO_ON) {
#ifdef GENESIS_AUDIO
        if(!c->audio.initialized || !c->audio.fm)return 0;
        size_t size=genesis_ymfm_state_size(c->audio.fm);
        if(!size || size>65536)return 0;
        uint8_t *bytes=malloc(size);if(!bytes)return 0;
        int ok=genesis_ymfm_save_state(c->audio.fm,bytes,size);
        if(ok) {at=save_section(s,5);save_bytes(s,bytes,size);save_section_end(s,at);}
        free(bytes);if(!ok)return 0;
#else
        return 0;
#endif
    }
    save_scalar(s,0,4);save_scalar(s,0,4);return !s->error;
}
static int save_valid(const CPU *c) {
    if(c->pc&1 || c->pc>=c->rom_size || c->instruction_cycles || c->cycles>UINT64_MAX/7 ||
       c->master_cycles!=c->cycles*7 || c->z80_divider>=15 || c->audio_mode>AUDIO_ON)return 0;
    const VDP *v=&c->vdp;
    if(v->pal>1 || v->line>=vdp_frame_lines(v) || v->line_clock>=VDP_LINE_CLOCKS ||
       v->frame_width>320 || v->frame_height>240 || v->code>63 || v->command_pending>1 ||
       v->fill_pending>1 || c->z80_bus.bank>511 || c->z80_cpu.im>2 || c->eeprom.phase>EE_WAIT ||
       c->eeprom.address>=128 || c->eeprom.bits>8)return 0;
    if(c->audio_mode==AUDIO_ON) {
        const Audio *a=&c->audio;
        if(!a->initialized || a->cursor>c->master_cycles || a->next_sample<=c->master_cycles ||
           a->sample_index>UINT64_MAX/vdp_master_frequency(v) ||
           a->next_sample!=a->sample_index*vdp_master_frequency(v)/AUDIO_RATE)return 0;
    }
#ifdef GENESIS_RINGS_MENU_FONT
    if(v->font_count>1200 || v->font_visible>1200)return 0;
#endif
    return 1;
}
/* Decode into a separate machine and optional presentation buffer. A bad file
   must not change the running CPU, chip or any host-owned pointer. */
static int save_decode(CPU *live,uint8_t *bytes,size_t size) {
    CPU *next=calloc(1,sizeof *next);if(!next)return 0;
    next->rom=live->rom;next->rom_size=live->rom_size;
#if defined(GENESIS_RINGS_SAVES) && defined(GENESIS_SDL2)
    next->rings_settings_enabled=live->rings_settings_enabled;
#endif
#ifdef GENESIS_RINGS_MENU_FONT
    next->vdp.font_enabled=live->vdp.font_enabled;
    memcpy(next->vdp.font_supported,live->vdp.font_supported,sizeof next->vdp.font_supported);
#endif
#ifdef GENESIS_RINGS_WIDE
    RingsWide *wide=NULL;
    if(live->wide) {wide=calloc(1,sizeof *wide);if(!wide) {free(next);return 0;}next->wide=wide;}
    next->vdp.wide_enabled=live->vdp.wide_enabled;next->vdp.zoom_enabled=live->vdp.zoom_enabled;
#endif
    SaveCodec in={0};in.data=bytes;in.size=size;in.reading=1;
    unsigned seen=0;int end=0;
    while(!in.error && in.pos<in.size) {
        unsigned tag=(unsigned)save_scalar(&in,0,4);size_t length=(size_t)save_scalar(&in,0,4);
        if(in.error || length>in.size-in.pos) {in.error=1;break;}
        if(!tag) {end=!length && in.pos==in.size;break;}
        if(tag<=6 && (seen&(1u<<tag))) {in.error=1;break;}
        if(tag<=6)seen|=1u<<tag;
        SaveCodec part={0};part.data=in.data+in.pos;part.size=length;part.reading=1;
        switch(tag) {
            case 1:save_core(&part,next);break;
#ifdef GENESIS_RINGS_MENU_FONT
            case 2:save_font(&part,&next->vdp);break;
#endif
#ifdef GENESIS_RINGS_WIDE
            case 3:save_wide_video(&part,&next->vdp);break;
            case 6:next->vdp.wide_hud_active=(uint8_t)save_scalar(&part,0,1);
                if(next->vdp.wide_hud_active>1)part.error=1;
                break;
            case 4:if(wide)save_wide(&part,wide);else part.pos=length;break;
#endif
            case 5:
#ifdef GENESIS_AUDIO
                if(length<=65536)next->audio.fm=genesis_ymfm_load_state(part.data,length);
                if(!next->audio.fm)part.error=1;
#else
                part.error=1;
#endif
                part.pos=length;break;
            default:part.pos=length;break;
        }
        if(part.error || part.pos!=length)in.error=1;
        in.pos+=length;
    }
    int ok=end && !in.error && (seen&2) && save_valid(next) && next->audio_mode==live->audio_mode;
    if(next->audio_mode==AUDIO_ON && !(seen&32))ok=0;
    if(next->audio_mode!=AUDIO_ON && (seen&32))ok=0;
    if(ok && !audio_wav_flush(&live->audio))ok=0;
    if(ok) {
        next->audio.wav=live->audio.wav;next->audio.wav_bytes=live->audio.wav_bytes;
        next->audio.playback=live->audio.playback;next->audio.dropped=live->audio.dropped;
#ifdef GENESIS_AUDIO
        if(live->audio.fm)genesis_ymfm_destroy(live->audio.fm);
#endif
#ifdef GENESIS_RINGS_WIDE
        if(wide) {void *shadow=live->wide->shadow;memcpy(live->wide,wide,sizeof *wide);live->wide->shadow=shadow;}
        next->wide=live->wide;
        /* Old saves can contain expanded room/battle caches. Derive the
           presentation from restored RAM before the first paused draw. */
        rings_scene_snapshot(next);
#endif
        memcpy(live,next,sizeof *live);
    } else {
#ifdef GENESIS_AUDIO
        if(next->audio.fm)genesis_ymfm_destroy(next->audio.fm);
#endif
    }
#ifdef GENESIS_RINGS_WIDE
    free(wide);
#endif
    free(next);return ok;
}
#endif
#endif
