/* Active-low three-button pad pins, selected by TH; output pins override inputs. */
#ifndef GENESIS_CONTROLLER_H
#define GENESIS_CONTROLLER_H
enum {
    PAD_UP=1, PAD_DOWN=2, PAD_LEFT=4, PAD_RIGHT=8,
    PAD_A=16, PAD_B=32, PAD_C=64, PAD_START=128
};
static uint8_t controller_pins(uint8_t buttons, int th) {
    uint8_t pins=(uint8_t)(th ? 0x7f:0x33);
    pins &= (uint8_t)~(buttons & (th ? 15:3));
    if (buttons & (th ? PAD_B:PAD_A)) pins &= (uint8_t)~0x10;
    if (buttons & (th ? PAD_C:PAD_START)) pins &= (uint8_t)~0x20;
    return pins;
}
#endif
