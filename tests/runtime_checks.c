/* Included after a generated translation by the integration test. */
#include <assert.h>

static int64_t signed_value(uint32_t value, unsigned size) {
    int64_t range=INT64_C(1)<<(size*8);
    return value >= (uint64_t)(range/2) ? (int64_t)value-range : value;
}
static void check_pair(uint32_t d, uint32_t s, unsigned size) {
    uint64_t range=UINT64_C(1)<<(size*8), mask=range-1;
    int64_t sd=signed_value(d,size), ss=signed_value(s,size);
    for (int sub=0; sub<2; ++sub) {
        int64_t mathematical=sub ? sd-ss : sd+ss;
        uint32_t expected=(uint32_t)(sub ? (uint64_t)d-s : (uint64_t)d+s)&(uint32_t)mask;
        unsigned carry=sub ? d<s : (uint64_t)d+s>=range;
        unsigned overflow=mathematical < -(int64_t)(range/2) || mathematical >= (int64_t)(range/2);
        unsigned flags=(carry ? F_C|F_X:0) | (overflow ? F_V:0) |
                       (expected==0 ? F_Z:0) | (expected>=range/2 ? F_N:0);
        CPU c={0}; c.sr=0xa71f;
        assert(arithmetic(&c,d,s,size,sub,0)==expected);
        assert(c.sr==(0xa700|flags));
    }
    CPU c={0}; c.sr=0xa710;
    arithmetic(&c,d,s,size,1,1);
    assert(c.sr & F_X);
    int expected_conditions[]={1,0,d>s,d<=s,d>=s,d<s,d!=s,d==s,
        !(c.sr&F_V),!!(c.sr&F_V),!(c.sr&F_N),!!(c.sr&F_N),sd>=ss,sd<ss,sd>ss,sd<=ss};
    for (unsigned cond=0; cond<16; ++cond) assert(condition(&c,cond)==expected_conditions[cond]);
    for (unsigned x=0; x<2; ++x) for (unsigned z=0; z<2; ++z) for (unsigned sub=0; sub<2; ++sub) {
        c.sr=(uint16_t)(0xa700|(x ? F_X:0)|(z ? F_Z:0));
        int64_t mathematical=sub ? sd-ss-x : sd+ss+x;
        uint32_t expected=(uint32_t)(sub ? (uint64_t)d-s-x : (uint64_t)d+s+x)&(uint32_t)mask;
        unsigned carry=sub ? (uint64_t)s+x>d : (uint64_t)d+s+x>=range;
        unsigned overflow=mathematical < -(int64_t)(range/2) || mathematical >= (int64_t)(range/2);
        unsigned flags=(carry ? F_C|F_X:0) | (overflow ? F_V:0) |
            (expected==0 && z ? F_Z:0) | (expected>=range/2 ? F_N:0);
        assert(extended_arithmetic(&c,d,s,size,(int)sub)==expected);
        assert(c.sr==(0xa700|flags));
    }
}
int main(void) {
    for (uint32_t d=0; d<256; ++d)
        for (uint32_t s=0; s<256; ++s) check_pair(d,s,1);
    for (unsigned size=2; size<=4; size+=2) {
        uint32_t mask=mask_for(size), sign=1u<<(size*8-1);
        uint32_t values[]={0,1,2,sign-2,sign-1,sign,sign+1,mask-1,mask};
        for (unsigned d=0; d<9; ++d)
            for (unsigned s=0; s<9; ++s) check_pair(values[d],values[s],size);
        uint32_t seed=12345;
        for (unsigned i=0; i<10000; ++i) {
            seed=seed*1664525u+1013904223u; uint32_t d=seed&mask;
            seed=seed*1664525u+1013904223u; check_pair(d,seed&mask,size);
        }
    }
    CPU c={0}; c.rom=rom_data; c.rom_size=sizeof rom_data;
    write_mem(&c,0xff0040,4,0x12345678);
    assert(read_mem(&c,0xe00040,4)==0x12345678);
    assert(read_mem(&c,0xf10040,4)==0x12345678);
    c.sr=0xa71f; logic_flags(&c,0,1); assert(c.sr==0xa714);
    logic_flags(&c,0x80,1); assert(c.sr==0xa718);
    c.d[0]=0xffff8000; assert(index_value(&c,0x0000)==0xffff8000);
    c.d[0]=0x12348000; assert(index_value(&c,0x0800)==0x12348000);
    c.sr=F_X; assert(shift_value(&c,0x80,0,1,0,1)==0x80); assert(c.sr==(F_X|F_N));
    c.sr=F_X; assert(shift_value(&c,0x80,0,1,2,0)==0x80); assert(c.sr==(F_X|F_N|F_C));
    c.sr=0; assert(shift_value(&c,0x80,8,1,0,0)==0xff); assert(c.sr==(F_N|F_C|F_X));
    c.sr=0; assert(shift_value(&c,0x80,8,1,1,0)==0); assert(c.sr==(F_Z|F_C|F_X));
    c.sr=0; assert(shift_value(&c,0x80,9,1,1,0)==0); assert(c.sr==F_Z);
    c.sr=F_X; assert(shift_value(&c,0x81,8,1,3,1)==0x81); assert(c.sr==(F_N|F_X|F_C));
    c.sr=0; assert(shift_value(&c,0x40,1,1,0,1)==0x80); assert(c.sr==(F_N|F_V));
    c.sr=F_X; assert(shift_value(&c,0,1,1,2,1)==1); assert(c.sr==0);
    c.sr=0; assert(divide_value(&c,0x80000000,0xffff,1)==0x80000000); assert(c.sr==F_V);
    c.sr=F_X; assert(divide_value(&c,0xfffffffe,2,1)==0x0000ffff); assert(c.sr==(F_X|F_N));
    write_mem(&c,0xff0001,2,1); assert(c.fault);
    return 0;
}
