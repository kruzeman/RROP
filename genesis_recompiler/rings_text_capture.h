/* Observer for the verified Rings of Power [!] text writers. It does not
   replace instructions, decode opcodes, or read devices through the CPU bus. */
#ifndef GENESIS_RINGS_TEXT_CAPTURE_H
#define GENESIS_RINGS_TEXT_CAPTURE_H
static uint32_t rings_text_pattern(const VDP *v,unsigned tile) {
    uint32_t hash=2166136261u;
    for(unsigned i=0;i<32;++i)hash=(hash^v->vram[tile*32+i])*16777619u;
    return hash;
}
static void rings_text_invalidate(VDP *v,unsigned address) {
    if(v->font_enabled)v->font_marks[(address&65535)/2].ch=0;
}
static int rings_text_peek(const CPU *c,uint32_t address,unsigned size,uint32_t *value) {
    uint32_t result=0;
    for(unsigned i=0;i<size;++i) {
        unsigned at=(address+i)&0xffffff;
        unsigned byte;
        if(at>=0xff0000)byte=c->ram[at&65535];
        #if defined(GENESIS_RINGS_SAVES) && defined(GENESIS_SDL2)
        else if(c->rings_settings_enabled && at>=0x400000 && at<0x400000+138)
            byte=rings_settings_rom_byte(c,at-0x400000);
#endif
        else if(at<c->rom_size)byte=c->rom[at];
        else return 0;
        result=(result<<8)|byte;
    }
    *value=result;return 1;
}
static void rings_text_capture(CPU *c,uint16_t value) {
    VDP *v=&c->vdp;
    /* $00D9F2 is the MOVE.W to the data port inside the shared word writer.
       Stack return addresses distinguish the verified text callers. */
    if(!v->font_enabled || c->pc!=0xd9f2)return;
    uint32_t caller,ch,attributes,bank;
    if(!rings_text_peek(c,c->a[7],4,&caller) ||
       !rings_text_peek(c,c->a[0]+c->d[4],1,&ch) ||
       !rings_text_peek(c,c->a[6]+22,2,&attributes) ||
       !rings_text_peek(c,0xff8640,2,&bank) || ch<32 || ch>126)return;
    unsigned delta,writer;
    switch(caller) {
        case 0x11192: delta=ch-32;writer=0;break;
        case 0x11290: delta=ch-64;writer=1;break;
        case 0x1121c: if(ch!=' ')return;delta=0;writer=1;break;
        case 0x11238: if(ch!='.')return;delta=0x1b;writer=1;break;
        case 0x11252: if(ch!=',')return;delta=0x1c;writer=1;break;
        case 0x1126c: if(ch!='-')return;delta=0x1d;writer=1;break;
        default:return;
    }
    if(value!=(uint16_t)(bank+attributes+delta))return;
    ++v->font_captured[writer];
    /* Consecutive source bytes in one writer invocation form a text run.
       Starting over, changing the caller frame/layout, or skipping a byte
       starts a new run, even for adjacent strings with identical contents. */
    uint32_t source=c->a[0]&0xffffff,frame=c->a[6]&0xffffff,offset=c->d[4];
    if(!v->font_run || !offset || source!=v->font_source || frame!=v->font_frame_pointer ||
       writer!=v->font_writer || attributes!=v->font_attributes || bank!=v->font_bank ||
       offset!=v->font_offset+1) {
        if(!++v->font_run) {
            memset(v->font_marks,0,sizeof v->font_marks);
            v->font_run=1;
        }
    }
    v->font_source=source;v->font_frame_pointer=frame;v->font_offset=offset;
    v->font_writer=(uint8_t)writer;v->font_attributes=(uint16_t)attributes;v->font_bank=(uint16_t)bank;
    RingsTextMark *mark=&v->font_marks[v->address/2];
    /* Spaces retain provenance for word spacing, without making an ink texture. */
    mark->entry=value;mark->ch=(uint8_t)ch;mark->run=v->font_run;
    mark->pattern=rings_text_pattern(v,value&0x7ff);
}
#endif
