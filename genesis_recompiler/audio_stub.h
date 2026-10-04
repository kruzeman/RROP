/* Explicit silent debug mode. Register storage only; no YM timers or synthesis. */
#ifndef GENESIS_AUDIO_STUB_H
#define GENESIS_AUDIO_STUB_H
static uint8_t ym2612_stub_read(CPU *c, unsigned port) {
    (void)c; (void)port;
    /* Ready, not busy; no timer overflow. This is a stub status, not FM timing. */
    return 0;
}
static void ym2612_stub_write(CPU *c, unsigned port, uint8_t value) {
    YM2612Stub *y=&c->ym2612_stub;
    unsigned bank=(port>>1)&1;
    if (port&1) y->registers[bank][y->address[bank]]=value;
    else y->address[bank]=value;
    ++y->writes;
}
#endif
