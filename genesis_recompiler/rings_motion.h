/* Execute bitmap work with host CPU capacity, pace world turns separately,
   and resolve ordinary player steps at the suspended main-loop boundary. */
#ifndef GENESIS_RINGS_MOTION_H
#define GENESIS_RINGS_MOTION_H
#if defined(GENESIS_RINGS_WIDE) && defined(GENESIS_SDL2)
static int rings_motion_scene(const CPU *c) {
    return c->wide && c->wide->motion.enabled && c->vdp.zoom_world_visible &&
        (c->vdp.wide_enabled || c->vdp.zoom_enabled) && !rings_scene_native(c) &&
        !rings_scene_word(c,0xac) && !rings_scene_word(c,0x110) &&
        !rings_scene_word(c,0x112) && !rings_scene_word(c,0x128) &&
        !rings_scene_word(c,0x11e);
}
static int rings_motion_revision(CPU *c) {
    /* Independent guards for the routines entered and the main-loop boundary.
       Translation still requires the full verified ROM SHA-256. */
    const unsigned at[]={0xd2be,0x24984,0x1b918,0x1b950,0x1b9ee,0x1386a};
    const unsigned op[]={0x4a79,0x4e56,0x4e56,0x4a79,0x4fef,0x4e56};
    if(c->rom_size<0x100000)return 0;
    for(unsigned i=0;i<sizeof at/sizeof *at;++i)if(read_mem(c,at[i],2)!=op[i])return 0;
    return !c->fault;
}
static unsigned rings_motion_direction(unsigned pad) {
    return pad==PAD_UP ? 0:pad==PAD_RIGHT ? 1:pad==PAD_DOWN ? 2:pad==PAD_LEFT ? 3:4;
}
static void rings_motion_blank(CPU *c) {
    /* Only the bitmap traversal bypasses this presentation wait. Device clocks
       and their real VBlank IRQs advance normally in the subsequent idle time. */
    c->d[0]&=0xffff0000u;logic_flags(c,0,2);c->pc=pop32(c)&0xffffff;
}
static uint64_t rings_motion_draw_time(CPU *source) {
    CPU *c=source->wide->shadow;memcpy(c,source,sizeof *c);c->wide=NULL;
    c->vdp.wide_enabled=c->vdp.zoom_enabled=0;c->audio_mode=AUDIO_STUB;
    uint64_t start=c->master_cycles;unsigned steps=0;
    while(!c->fault && !c->halted && c->pc!=0x1b9ee && steps++<1000000) {
        if(machine_interrupt(c))continue;
        c->instruction_cycles=0;translated_step(c);machine_advance(c,c->instruction_cycles);
    }
    if(c->fault || c->halted || c->pc!=0x1b9ee)return 0;
    /* This reference traversal accounts for native IRQs and VBlank waits; its
       RAM, devices and elapsed clocks are never applied to the live console. */
    return c->master_cycles-start;
}
static int rings_motion_player(CPU *source,unsigned direction) {
    RingsMotion *m=&source->wide->motion;CPU *c=source->wide->shadow;
    unsigned actor=rings_scene_word(source,0x2b2),record=0x2b4+actor*52;
    if(actor>=56 || (rings_scene_word(source,record)&15)!=1)return 0;
    unsigned sprite=rings_scene_word(source,record+4);
    if(sprite>=56)return 0;
    unsigned queue=0xe30+actor*72;
    if(source->ram[queue]!=source->ram[queue+1])return 0;
    memcpy(c,source,sizeof *c);c->wide=NULL;c->audio_mode=AUDIO_STUB;
    unsigned sp=c->a[7],low=sp,steps=0;uint64_t cycles=0;
    c->a[7]-=2;write_mem(c,c->a[7],2,direction);
    c->a[7]-=2;write_mem(c,c->a[7],2,actor);push32(c,0xffffff);c->pc=0x24984;
    while(!c->fault && !c->halted && c->pc!=0xffffff && steps++<100000) {
        if(c->a[7]<low)low=c->a[7];
        if(c->pc==0x1386a)break;
        c->instruction_cycles=0;translated_step(c);cycles+=c->instruction_cycles;
    }
    if(c->fault || c->halted || c->pc!=0xffffff || low<0xff0000 || sp-low>4096 ||
       rings_scene_identity(source)!=rings_scene_identity(c) || rings_scene_native(c) ||
       rings_scene_word(c,0xac) || rings_scene_word(c,0x110) || rings_scene_word(c,0x112) ||
       rings_scene_word(c,0x128) || rings_scene_word(c,0x11e) ||
       rings_scene_word(c,0xe16)!=rings_scene_word(source,0xe16) ||
       memcmp(&c->vdp,&source->vdp,sizeof c->vdp) ||
       memcmp(&c->z80_bus,&source->z80_bus,sizeof c->z80_bus) ||
       memcmp(&c->psg,&source->psg,sizeof c->psg) ||
       memcmp(&c->ym2612_stub,&source->ym2612_stub,sizeof c->ym2612_stub))return 0;
    /* Reject effects on other actors; scripted/vehicle/event movement falls
       back to the original command/actor path with its direction retained. */
    for(unsigned i=0;i<56;++i) {
        if(i!=actor && memcmp(c->ram+0x2b4+i*52,source->ram+0x2b4+i*52,52))return 0;
        if(i!=sprite && memcmp(c->ram+0xb0cc+i*12,source->ram+0xb0cc+i*12,12))return 0;
    }
    for(unsigned at=low;at<sp;++at)c->ram[at&65535]=source->ram[at&65535];
    memcpy(source->ram,c->ram,sizeof source->ram);source->steps+=steps;
#ifdef GENESIS_RINGS_SAVES
    source->rings_pool_revision=c->rings_pool_revision;source->rings_pool_write_pc=c->rings_pool_write_pc;
#endif
    m->player_budget+=cycles*7;++m->moves;return 1;
}
static int rings_motion_redraw(CPU *c) {
    uint32_t d[8],a[8],pc=c->pc;uint16_t sr=c->sr;
    memcpy(d,c->d,sizeof d);memcpy(a,c->a,sizeof a);
    c->ram[0x99]=1;push32(c,0xffffff);c->pc=0x1b918;unsigned steps=0;
    while(!c->fault && !c->halted && c->pc!=0xffffff && steps++<1000000) {
        if(c->pc==0x1386a) {rings_motion_blank(c);continue;}
        rings_wide_observe(c);translated_step(c);
    }
    int ok=!c->fault && !c->halted && c->pc==0xffffff;
    c->steps+=steps;c->pc=pc;c->sr=sr;memcpy(c->d,d,sizeof d);memcpy(c->a,a,sizeof a);
    c->instruction_cycles=0;
    if(!ok && !c->fault)fail(c,"responsive drawing traversal did not complete",pc);
    return ok;
}
static int rings_motion_before(CPU *c) {
    if(!c->wide)return 0;
    RingsMotion *m=&c->wide->motion;
    if(!m->enabled)return 0;
    if(!m->verified) {
        if(!rings_motion_revision(c)) {m->enabled=0;return 0;}m->verified=1;
    }
    if(c->pc==0x1386a && m->drawing) {rings_motion_blank(c);++c->steps;return 1;}
    if(c->pc==0x1b9ee && m->drawing) {m->drawing=0;m->finish=1;}
    if(c->pc==0x2155e) {
        if(rings_motion_scene(c)) {m->turn=c->master_cycles;m->active=1;}
        else m->active=0;
    }
    if(c->pc==0x1b950 && m->active && rings_motion_scene(c) && !m->drawing) {
        uint64_t budget=rings_motion_draw_time(c);
        if(budget && budget<=2ull*vdp_master_frequency(&c->vdp)) {
            m->draw_budget=budget;m->drawing=1;++m->passes;
        } else {++m->timing_failures;m->active=0;}
    }
    if(c->pc==0x24984 && m->active && read_mem(c,c->a[7]+4,2)==rings_scene_word(c,0x2b2) &&
       read_mem(c,c->a[7]+6,2)<4)m->next_step=c->master_cycles+m->period;
    if(c->pc!=0xd2be || !m->active)return 0;
    if(m->finish) {
        m->period=c->master_cycles-m->turn+m->draw_budget+m->player_budget;
        m->due=m->turn+m->period;m->player_budget=0;m->finish=0;
    }
    if(!rings_motion_scene(c)) {m->active=0;return 0;}
    if(c->master_cycles>=m->due)return 0;
    RingsPadIntent *p=m->intent;
    unsigned pad=c->pad_buttons[0];
    if(!pad && p && p->pending && c->master_cycles<=p->deadline)pad=p->pending;
    unsigned direction=rings_motion_direction(pad);
    if(direction<4 && !m->fallback && c->master_cycles>=m->next_step) {
        ++m->attempts;
        if(rings_motion_player(c,direction)) {
            if(p)p->pending=0;
            rings_motion_redraw(c);
        } else {m->fallback=pad;++m->rejected;}
        m->next_step=c->master_cycles+m->period;
    }
    c->instruction_cycles=0;machine_advance(c,256);++c->steps;return 1;
}
#endif
#endif
