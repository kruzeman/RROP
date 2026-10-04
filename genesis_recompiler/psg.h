/* Integrated Genesis PSG: three tones and 16-bit periodic/white noise. */
#ifndef GENESIS_PSG_H
#define GENESIS_PSG_H
static void psg_write(CPU *c, uint8_t value) {
    if(c->audio_mode==AUDIO_ON)audio_sync(c);
    PSG *p=&c->psg;
    if (value&0x80) p->latch=(value>>4)&7;
    unsigned channel=p->latch>>1;
    if (p->latch&1) p->volume[channel]=value&15;
    else if (channel==3) { p->noise=value&7; p->noise_lfsr=0x8000; p->counter[3]=(p->noise&3)==3 ? (p->tone[2] ? p->tone[2]:1):(uint16_t)(16u<<(p->noise&3)); }
    else if (value&0x80) p->tone[channel]=(uint16_t)((p->tone[channel]&0x3f0)|(value&15));
    else p->tone[channel]=(uint16_t)((p->tone[channel]&15)|((value&63)<<4));
    ++p->writes;
}
static void psg_audio_init(PSG *p,uint64_t master) {
    for(unsigned i=0;i<4;++i){p->volume[i]=15;p->counter[i]=1;}
    p->counter[3]=16;p->noise_lfsr=0x8000;
    p->cursor=master;p->next_tick=(master/240+1)*240;p->area=0;p->polarity=0;
}
static int32_t psg_audio_level(const PSG *p) {
    // 2 dB attenuation steps. The final entry is hardware silence.
    static const int16_t amplitude[16]={2048,1627,1292,1026,815,648,514,408,325,258,205,163,129,103,81,0};
    int32_t output=0;
    for(unsigned i=0;i<3;++i)output+=(p->polarity&(1u<<i) ? 1:-1)*amplitude[p->volume[i]&15];
    output+=(p->noise_lfsr&1 ? 1:-1)*amplitude[p->volume[3]&15];
    return output;
}
static void psg_audio_advance(PSG *p,uint64_t target) {
    while(p->next_tick<=target){
        p->area+=(int64_t)psg_audio_level(p)*(int64_t)(p->next_tick-p->cursor);
        p->cursor=p->next_tick;p->next_tick+=240; // master / 15 / 16
        for(unsigned i=0;i<3;++i)if(--p->counter[i]==0){
            p->counter[i]=p->tone[i] ? p->tone[i]:1;p->polarity^=(uint8_t)(1u<<i);
        }
        if(--p->counter[3]==0){
            unsigned rate=p->noise&3;
            p->counter[3]=rate==3 ? (p->tone[2] ? p->tone[2]:1):(uint16_t)(16u<<rate);
            p->polarity^=8;
            if(p->polarity&8){
                unsigned feedback=p->noise&4 ? (p->noise_lfsr^(p->noise_lfsr>>3))&1:p->noise_lfsr&1;
                p->noise_lfsr=(uint16_t)((p->noise_lfsr>>1)|(feedback<<15));
            }
        }
    }
    p->area+=(int64_t)psg_audio_level(p)*(int64_t)(target-p->cursor);p->cursor=target;
}
#endif
