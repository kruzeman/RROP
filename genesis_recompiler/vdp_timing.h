/* NTSC/PAL beam timing. Instruction-boundary events; transfers remain synchronous. */
#ifndef GENESIS_VDP_TIMING_H
#define GENESIS_VDP_TIMING_H
#define VDP_LINE_CLOCKS 3420u
#define VDP_NTSC_LINES 262u
static unsigned vdp_frame_lines(const VDP *v) { return v->pal ? 313:VDP_NTSC_LINES; }
static unsigned vdp_master_frequency(const VDP *v) { return v->pal ? 53203424:53693175; }
static unsigned vdp_visible_lines(const VDP *v) { return v->registers[1]&8 ? 240:224; }
static unsigned vdp_vint_clock(const VDP *v) { return v->registers[12]&1 ? 788:770; }
/* The bus read can cross the VINT event while the current instruction is
   finishing, before the CPU acknowledges IRQ6 at the next boundary. */
static int vdp_status_vint(const CPU *c) {
    const VDP *v=&c->vdp;
    if (v->vint_status) return 1;
    unsigned period=vdp_frame_lines(v)*VDP_LINE_CLOCKS;
    unsigned now=v->line*VDP_LINE_CLOCKS+v->line_clock;
    unsigned event=vdp_visible_lines(v)*VDP_LINE_CLOCKS+vdp_vint_clock(v);
    unsigned distance=(event+period-now)%period;
    return distance && distance<=c->instruction_cycles*7;
}
static int vdp_vblank(const VDP *v) {
    return !(v->registers[1]&0x40) || v->line>=vdp_visible_lines(v);
}
static int vdp_hblank(const VDP *v) {
    /* Approximate active/blank boundary; no pixel-fetch or FIFO scheduling. */
    return v->line_clock>=2560;
}
static void vdp_advance(CPU *c, unsigned clocks) {
    VDP *v=&c->vdp;
    while (clocks) {
        unsigned remaining=VDP_LINE_CLOCKS-v->line_clock;
        if (v->line==vdp_visible_lines(v) && v->line_clock<vdp_vint_clock(v))
            remaining=vdp_vint_clock(v)-v->line_clock;
        if (clocks<remaining) { v->line_clock=(uint16_t)(v->line_clock+clocks); break; }
        clocks-=remaining; v->line_clock=(uint16_t)(v->line_clock+remaining);
        if (v->line_clock<VDP_LINE_CLOCKS) {
            v->irq_v=1; v->vint_status=1;
            c->z80_cpu.irq_line=1;
            continue;
        }
        v->line_clock=0;
        c->z80_cpu.irq_line=0;
        if (v->line<vdp_visible_lines(v)) {
            if (v->hint_counter==0) { v->hint_counter=v->registers[10]; v->irq_h=1; }
            else --v->hint_counter;
        } else v->hint_counter=v->registers[10];
        if (++v->line==vdp_visible_lines(v)) {
            if (v->registers[1]&0x40) vdp_render(c);
        }
        if (v->line==vdp_frame_lines(v)) { v->line=0; ++v->frames; v->hint_counter=v->registers[10]; }
    }
}
static unsigned vdp_irq_level(const VDP *v) {
    if (v->irq_v && (v->registers[1]&0x20)) return 6;
    if (v->irq_h && (v->registers[0]&0x10)) return 4;
    return 0;
}
static void vdp_irq_ack(VDP *v, unsigned level) {
    if (level==6) { v->irq_v=0; v->vint_status=0; }
    else if (level==4) v->irq_h=0;
}
static uint16_t vdp_counter(const VDP *v) {
    unsigned vertical=v->line;
    unsigned maximum=v->pal ? (vdp_visible_lines(v)==224 ? 0x102:0x10a):
                             (vdp_visible_lines(v)==224 ? 0xea:0x106);
    if (vertical>maximum) vertical-=vdp_frame_lines(v);
    /* H32 has 171 counter slots; H40 interpolation is approximate because
       its clock divider varies around horizontal blanking. */
    unsigned slots=(v->registers[12]&1) ? 211:171;
    unsigned horizontal=v->line_clock*slots/VDP_LINE_CLOCKS;
    unsigned jump=(slots==211) ? 183:148;
    if (horizontal>=jump) horizontal+=256-slots;
    return (uint16_t)(((vertical&255)<<8)|(horizontal&255));
}
#endif
