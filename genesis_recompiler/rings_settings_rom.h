/* Read-only menu resource extension for the verified Rings ROM. */
#ifndef GENESIS_RINGS_SETTINGS_ROM_H
#define GENESIS_RINGS_SETTINGS_ROM_H
#if defined(GENESIS_RINGS_SAVES) && defined(GENESIS_SDL2)
static uint8_t rings_settings_rom_byte(const CPU *c,unsigned offset) {
    if(offset==11)return 9;
    if(offset<124)return c->rom[0xccff4+offset];
    static const uint8_t row[14]={'S','e','t','t','i','n','g','s',0,0,0,0,0xfd,1};
    return row[offset-124];
}
#endif
#endif
