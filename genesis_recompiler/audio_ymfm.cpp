/* YM2612 adapter for GenesisRecomp. Upstream ymfm: ymfm/LICENSE (BSD-3-Clause).
   Events use YM input clocks (Genesis master / 7), not host wall time. */
#include <cstdint>
#include <limits>
#include <new>
#include <cstring>
#define GENESIS_AUDIO
#include "audio_backend.h"
#include "ymfm/ymfm_opn.h"

class GenesisYM final : public ymfm::ymfm_interface {
public:
    static constexpr uint64_t never=std::numeric_limits<uint64_t>::max();
    uint64_t now=0, sample_time=144, busy_end=0, timers[2]={never,never};
    ymfm::ym2612 chip;
    ymfm::ym2612::output_data previous{}, current{};
    GenesisYM() : chip(*this) { chip.reset(); }
    void ymfm_set_timer(uint32_t n, int32_t duration) override {
        if (n<2) timers[n]=duration<0 ? never:now+uint32_t(duration);
    }
    void ymfm_set_busy_end(uint32_t clocks) override { busy_end=now+clocks; }
    bool ymfm_is_busy() override { return now<busy_end; }
    void reset() {
        timers[0]=timers[1]=never;busy_end=now;sample_time=now+144;
        previous.clear();current.clear();chip.reset();
    }
    void advance(uint64_t master,int32_t stereo[2]) {
        uint64_t target=master/7;
        // A caller must never rewind the modeled clock.
        if(target<now)target=now;
        for (;;) {
            uint64_t event=sample_time;
            for(unsigned i=0;i<2;++i)if(timers[i]<event)event=timers[i];
            if(event>target)break;
            now=event;
            for(unsigned i=0;i<2;++i)if(timers[i]==event){
                timers[i]=never;m_engine->engine_timer_expired(i);
            }
            if(sample_time==event){previous=current;chip.generate(&current);sample_time+=144;}
        }
        now=target;
        // Causal linear interpolation adds one native FM-sample of latency.
        unsigned fraction=unsigned(144-(sample_time-now));
        for(unsigned i=0;i<2;++i)stereo[i]=previous.data[i]+
            int32_t((int64_t(current.data[i])-previous.data[i])*fraction/144);
    }
    void state(ymfm::ymfm_saved_state &s) {
        uint64_t *clocks[]={&now,&sample_time,&busy_end,&timers[0],&timers[1]};
        for(auto n:clocks) {
            uint32_t low=uint32_t(*n),high=uint32_t(*n>>32);
            s.save_restore(low);s.save_restore(high);
            if(!s.saving())*n=uint64_t(low)|(uint64_t(high)<<32);
        }
        s.save_restore(previous.data);s.save_restore(current.data);chip.save_restore(s);
    }
    std::vector<uint8_t> snapshot() {
        std::vector<uint8_t> bytes;ymfm::ymfm_saved_state s(bytes,true);state(s);return bytes;
    }
};
extern "C" void *genesis_ymfm_create(void) { return new(std::nothrow) GenesisYM; }
extern "C" void genesis_ymfm_destroy(void *chip) { delete static_cast<GenesisYM*>(chip); }
extern "C" void genesis_ymfm_reset(void *chip) { static_cast<GenesisYM*>(chip)->reset(); }
extern "C" void genesis_ymfm_advance(void *chip,uint64_t master,int32_t stereo[2]) {
    static_cast<GenesisYM*>(chip)->advance(master,stereo);
}
extern "C" uint8_t genesis_ymfm_read(void *chip,unsigned port) {
    return static_cast<GenesisYM*>(chip)->chip.read(port&3);
}
extern "C" void genesis_ymfm_write(void *chip,unsigned port,uint8_t value) {
    static_cast<GenesisYM*>(chip)->chip.write(port&3,value);
}
extern "C" size_t genesis_ymfm_state_size(void *chip) {
    try {return static_cast<GenesisYM*>(chip)->snapshot().size();}catch(...) {return 0;}
}
extern "C" int genesis_ymfm_save_state(void *chip,uint8_t *bytes,size_t size) {
    try {
        auto state=static_cast<GenesisYM*>(chip)->snapshot();
        if(state.size()!=size)return 0;
        std::memcpy(bytes,state.data(),size);return 1;
    }catch(...) {return 0;}
}
extern "C" void *genesis_ymfm_load_state(const uint8_t *bytes,size_t size) {
    GenesisYM *g=nullptr;
    try {
        g=new GenesisYM;if(g->snapshot().size()!=size) {delete g;return nullptr;}
        std::vector<uint8_t> state(bytes,bytes+size);ymfm::ymfm_saved_state s(state,false);g->state(s);
        bool valid=g->sample_time>g->now && g->sample_time-g->now<=144;
        for(auto timer:g->timers)valid&=timer==GenesisYM::never || timer>=g->now;
        for(unsigned i=0;i<2;++i)valid&=g->previous.data[i]>=-1048576 && g->previous.data[i]<=1048576 &&
                                      g->current.data[i]>=-1048576 && g->current.data[i]<=1048576;
        if(!valid) {delete g;return nullptr;}return g;
    }catch(...) {delete g;return nullptr;}
}

// Compile the selected, unmodified upstream sources into this optional object.
#include "ymfm/ymfm_adpcm.cpp"
#include "ymfm/ymfm_ssg.cpp"
#include "ymfm/ymfm_opn.cpp"
