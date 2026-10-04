/* Clocked stereo PCM, DC removal, bounded host buffering and little-endian WAV.
   The chip state advances independently of playback and file output. */
#ifndef GENESIS_AUDIO_H
#define GENESIS_AUDIO_H
static void audio_sync(CPU *c);
static void audio_le32(uint8_t *p,uint32_t value) {
    for(unsigned i=0;i<4;++i)p[i]=(uint8_t)(value>>(i*8));
}
static int audio_wav_flush(Audio *a) {
    if(!a->wav || !a->wav_count)return !a->error;
    uint8_t bytes[AUDIO_WAV_FRAMES*4];
    unsigned size=a->wav_count*4;
    if(a->wav_bytes+size>UINT32_MAX-36u){a->error=1;return 0;}
    for(unsigned i=0;i<a->wav_count*2;++i){
        uint16_t sample=(uint16_t)a->wav_buffer[i];
        bytes[i*2]=(uint8_t)sample;bytes[i*2+1]=(uint8_t)(sample>>8);
    }
    if(fwrite(bytes,1,size,a->wav)!=size){a->error=1;return 0;}
    a->wav_bytes+=size;a->wav_count=0;return 1;
}
static int audio_init(CPU *c,const char *wav_path) {
    Audio *a=&c->audio;
    if(a->initialized)return !a->error;
#ifndef GENESIS_AUDIO
    (void)wav_path;fail(c,"sound backend not compiled; rebuild with --sound ymfm",c->pc);return 0;
#else
    a->fm=genesis_ymfm_create();
    if(!a->fm){fail(c,"cannot allocate FM sound state",c->pc);return 0;}
    a->initialized=1;
    a->cursor=c->master_cycles;
    a->sample_index=c->master_cycles*AUDIO_RATE/vdp_master_frequency(&c->vdp)+1;
    a->next_sample=a->sample_index*vdp_master_frequency(&c->vdp)/AUDIO_RATE;
    psg_audio_init(&c->psg,c->master_cycles);
    if(wav_path){
        a->wav=fopen(wav_path,"wb");
        if(!a->wav){fail(c,"cannot open audio WAV",c->pc);return 0;}
        uint8_t header[44]={0};
        memcpy(header,"RIFF",4);memcpy(header+8,"WAVEfmt ",8);
        audio_le32(header+16,16);header[20]=1;header[22]=2;
        audio_le32(header+24,AUDIO_RATE);audio_le32(header+28,AUDIO_RATE*4);
        header[32]=4;header[34]=16;memcpy(header+36,"data",4);
        if(fwrite(header,1,sizeof header,a->wav)!=sizeof header){
            a->error=1;fail(c,"cannot write audio WAV header",c->pc);return 0;
        }
    }
    return 1;
#endif
}
static void audio_sample(CPU *c,const int32_t fm[2],int32_t psg) {
    Audio *a=&c->audio;int16_t stereo[2];
    for(unsigned ch=0;ch<2;++ch){
        int32_t input=fm[ch]*3/4+psg;
        int32_t output=input-a->previous_input[ch]+(int32_t)((int64_t)a->filter[ch]*32717/32768);
        a->previous_input[ch]=input;a->filter[ch]=output;
        if(output>32767)output=32767;
        if(output< -32768)output=-32768;
        unsigned level=(unsigned)(output<0 ? -output:output);if(level>a->peak)a->peak=level;
        stereo[ch]=(int16_t)output;
    }
    ++a->frames;
    if(a->wav && !a->error){
        a->wav_buffer[a->wav_count*2]=stereo[0];a->wav_buffer[a->wav_count*2+1]=stereo[1];
        if(++a->wav_count==AUDIO_WAV_FRAMES)audio_wav_flush(a);
    }
    if(a->playback){
        if(a->count==AUDIO_RING_FRAMES){a->read=(a->read+1)%AUDIO_RING_FRAMES;--a->count;++a->dropped;}
        unsigned at=(a->read+a->count)%AUDIO_RING_FRAMES;
        a->ring[at*2]=stereo[0];a->ring[at*2+1]=stereo[1];++a->count;
    }
}
static void audio_sync(CPU *c) {
    if(c->audio_mode!=AUDIO_ON || c->fault)return;
    Audio *a=&c->audio;
    if(!a->initialized && !audio_init(c,NULL))return;
#ifdef GENESIS_AUDIO
    uint64_t target=c->master_cycles;
    if(target<a->cursor){fail(c,"sound clock cannot rewind",c->pc);return;}
    int32_t fm[2];
    while(a->next_sample<=target){
        psg_audio_advance(&c->psg,a->next_sample);
        genesis_ymfm_advance(a->fm,a->next_sample,fm);
        uint64_t width=a->next_sample-a->cursor;
        int32_t psg=width ? (int32_t)(c->psg.area/(int64_t)width):0;
        c->psg.area=0;audio_sample(c,fm,psg);
        a->cursor=a->next_sample;
        ++a->sample_index;a->next_sample=a->sample_index*vdp_master_frequency(&c->vdp)/AUDIO_RATE;
    }
    // Preserve partial PSG integration when a register changes between samples.
    psg_audio_advance(&c->psg,target);genesis_ymfm_advance(a->fm,target,fm);
    if(a->error)fail(c,"cannot write audio WAV",c->pc);
#endif
}
static uint8_t audio_fm_read(CPU *c,unsigned port) {
    if(c->audio_mode!=AUDIO_ON)return ym2612_stub_read(c,port);
    audio_sync(c);
#ifdef GENESIS_AUDIO
    if(!c->fault)return genesis_ymfm_read(c->audio.fm,port);
#endif
    return 0;
}
static void audio_fm_write(CPU *c,unsigned port,uint8_t value) {
    if(c->audio_mode==AUDIO_ON){
        audio_sync(c);
#ifdef GENESIS_AUDIO
        if(c->fault)return;
        genesis_ymfm_write(c->audio.fm,port,value);
#endif
    }
    ym2612_stub_write(c,port,value);
}
static void audio_fm_reset(CPU *c) {
    if(c->audio_mode!=AUDIO_ON)return;
    audio_sync(c);
#ifdef GENESIS_AUDIO
    if(!c->fault)genesis_ymfm_reset(c->audio.fm);
#endif
}
static unsigned audio_pop(CPU *c,int16_t *output,unsigned frames) {
    Audio *a=&c->audio;if(frames>a->count)frames=a->count;
    for(unsigned i=0;i<frames;++i){
        output[i*2]=a->ring[a->read*2];output[i*2+1]=a->ring[a->read*2+1];
        a->read=(a->read+1)%AUDIO_RING_FRAMES;
    }
    a->count-=frames;return frames;
}
static int audio_finish(CPU *c) {
    Audio *a=&c->audio;
    if(a->wav){
        audio_wav_flush(a);
        uint8_t value[4];audio_le32(value,(uint32_t)a->wav_bytes+36);
        if(fseek(a->wav,4,SEEK_SET) || fwrite(value,1,4,a->wav)!=4)a->error=1;
        audio_le32(value,(uint32_t)a->wav_bytes);
        if(fseek(a->wav,40,SEEK_SET) || fwrite(value,1,4,a->wav)!=4)a->error=1;
        if(fclose(a->wav))a->error=1;
        a->wav=NULL;
    }
#ifdef GENESIS_AUDIO
    if(a->fm)genesis_ymfm_destroy(a->fm);
#endif
    a->fm=NULL;a->initialized=0;
    return !a->error;
}
#endif
