#ifndef GENESIS_RINGS_OBJECT_DIAGNOSTICS_H
#define GENESIS_RINGS_OBJECT_DIAGNOSTICS_H
static unsigned rings_objects_word(const CPU *c,unsigned at) {
    return ((unsigned)c->ram[at]<<8)|c->ram[at+1];
}
static uint32_t rings_objects_long(const CPU *c,unsigned at) {
    return (rings_objects_word(c,at)<<16)|rings_objects_word(c,at+2);
}
static unsigned rings_objects_base(unsigned pool) {return pool ? 0xb0cc:0x02b4;}
static unsigned rings_objects_stride(unsigned pool) {return pool ? 12:52;}
static int rings_objects_used(unsigned pool,unsigned word) {
    return pool ? word!=9999:(word&15)!=0;
}
static void rings_objects_scan(RingsObjectDiagnostics *d,const CPU *c) {
    for(unsigned pool=0;pool<2;++pool) {
        unsigned used=0;
        for(unsigned slot=0;slot<RINGS_OBJECT_SLOTS;++slot) {
            unsigned word=rings_objects_word(c,rings_objects_base(pool)+slot*rings_objects_stride(pool));
            unsigned old=d->words[pool][slot];
            int active=rings_objects_used(pool,word),was=rings_objects_used(pool,old);
            used+=active;
            if(d->ready && old!=word) {
                RingsObjectEvent *e=&d->events[d->next];
                e->step=c->steps;e->frame=c->vdp.frames;e->pc=c->rings_pool_write_pc;
                e->before=(uint16_t)old;e->after=(uint16_t)word;e->pool=(uint8_t)pool;e->slot=(uint8_t)slot;
                d->next=(d->next+1)%RINGS_OBJECT_EVENTS;
                if(d->count<RINGS_OBJECT_EVENTS)++d->count;
                if(active && !was) {
                    ++d->allocations[pool];d->births[pool][slot]=c->steps;
                    d->creators[pool][slot]=c->rings_pool_write_pc;
                }
                if(!active && was)++d->releases[pool];
            }
            d->words[pool][slot]=(uint16_t)word;
        }
        if(used>d->peak[pool])d->peak[pool]=used;
    }
    d->ready=1;d->revision=c->rings_pool_revision;
}
static const char *rings_objects_error_name(unsigned code) {
    switch(code) {
        case 0x16:return "no free entry in 56-slot placement table";
        case 0x1a:return "no free entry in 56-slot actor table";
        case 0x15:return "placement cache conflict";
        case 0x18:return "object absent from placement cache";
        case 0x19:return "placement cache lookup failed";
        case 0x1b:return "invalid actor identifier";
        default:return "native internal error; cause requires investigation";
    }
}
static void rings_objects_report(RingsSaves *s,CPU *c) {
    char directory[1100],path[1200];
    if(!s->enabled)return;
    snprintf(directory,sizeof directory,"%s/diagnostics",s->directory);
    if(!rings_save_mkdir(directory)) {
        fprintf(stderr,"objects: cannot create diagnostics directory\n");return;
    }
    unsigned stack=c->a[7]&0xffff;
    int valid_stack=(c->a[7]&0xffffff)>=0xe00000 && stack<=0xfffa;
    unsigned code=valid_stack ? rings_objects_word(c,stack+4):0xffff;
    uint32_t caller=valid_stack ? rings_objects_long(c,stack):UINT32_MAX;
    snprintf(path,sizeof path,"%s/void-error.grs",directory);
    int captured=rings_save_write_path(s,c,path,"Emergency snapshot");
    snprintf(path,sizeof path,"%s/void-error.txt",directory);
#ifdef _WIN32
    wchar_t wide[1200];
    FILE *f=rings_save_wide(path,wide,1200) ? _wfopen(wide,L"wb"):NULL;
#else
    FILE *f=fopen(path,"wb");
#endif
    if(!f) {fprintf(stderr,"objects: cannot write error report\n");return;}
    fprintf(f,"Rings of Power native Void error\ncode=%u (0x%04x): %s\n"
        "return_pc=%06x pc=%06x step=%" PRIu64 " frame=%" PRIu64 "\n"
        "rom_hash=%016" PRIx64 " audio_mode=%d snapshot=%s\n"
        "mode=%u map_descriptor=%06x placement_count=%u\n",
        code,code,rings_objects_error_name(code),caller,c->pc,c->steps,c->vdp.frames,
        s->rom_hash,c->audio_mode,captured ? "void-error.grs":"FAILED",
        rings_objects_word(c,0xae),(unsigned)rings_objects_long(c,0xa7fc),rings_objects_word(c,0x96));
    for(unsigned i=0;i<8;++i)fprintf(f,"D%u=%08x A%u=%08x\n",i,c->d[i],i,c->a[i]);
    for(unsigned pool=0;pool<2;++pool) {
        unsigned used=0;
        for(unsigned slot=0;slot<RINGS_OBJECT_SLOTS;++slot)
            used+=rings_objects_used(pool,s->objects.words[pool][slot]);
        fprintf(f,"\npool=%s used=%u/56 peak=%u allocations=%" PRIu64 " releases=%" PRIu64 "\n",
            pool ? "placement":"actor",used,s->objects.peak[pool],
            s->objects.allocations[pool],s->objects.releases[pool]);
        for(unsigned slot=0;slot<RINGS_OBJECT_SLOTS;++slot) {
            unsigned at=rings_objects_base(pool)+slot*rings_objects_stride(pool);
            fprintf(f,"slot=%02u active=%d created_pc=%06x born_step=%" PRIu64 " raw=",
                slot,rings_objects_used(pool,s->objects.words[pool][slot]),
                s->objects.creators[pool][slot],s->objects.births[pool][slot]);
            for(unsigned j=0;j<rings_objects_stride(pool);++j)fprintf(f,"%02x",c->ram[at+j]);
            fputc('\n',f);
        }
    }
    fprintf(f,"\nLast %u slot-header changes (oldest first):\n",s->objects.count);
    unsigned first=(s->objects.next+RINGS_OBJECT_EVENTS-s->objects.count)%RINGS_OBJECT_EVENTS;
    for(unsigned i=0;i<s->objects.count;++i) {
        const RingsObjectEvent *e=&s->objects.events[(first+i)%RINGS_OBJECT_EVENTS];
        fprintf(f,"step=%" PRIu64 " frame=%" PRIu64 " pc=%06x pool=%u slot=%u %04x -> %04x\n",
            e->step,e->frame,e->pc,e->pool,e->slot,e->before,e->after);
    }
    int failed=ferror(f);if(fclose(f))failed=1;
    fprintf(stderr,"objects: Void error %u (%s); report %s: %s\n",code,
        rings_objects_error_name(code),failed ? "write failed":"written",path);
}
static void rings_objects_observe(RingsSaves *s,CPU *c) {
    RingsObjectDiagnostics *d=&s->objects;
    if(c->fault)return;
    if(!s->started && c->pc!=0x12fa0) {
        if(d->ready)memset(d,0,sizeof *d);
        return;
    }
    if(!d->ready || d->revision!=c->rings_pool_revision)rings_objects_scan(d,c);
    /* At entry, A7 holds return PC followed by the 16-bit native error code.
       Capture before the game clears/draws the fatal screen. */
    if(c->pc==0x12fa0) {
        if(!d->error_latched) {d->error_latched=1;rings_objects_report(s,c);}
    } else d->error_latched=0;
}
#endif
