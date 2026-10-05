/* Host preferences, deliberately separate from saved game state. */
#ifndef GENESIS_RINGS_SETTINGS_STATE_H
#define GENESIS_RINGS_SETTINGS_STATE_H
#if defined(GENESIS_RINGS_SAVES) && defined(GENESIS_SDL2)
typedef struct {
    int ready,menu,selected,controls,control_selected;
    int remap;
    uint8_t remap_binding[4];
    uint32_t remap_held;
    int enhanced,wide,fullscreen,smooth,zoom,mouse,help;
    unsigned saved_zoom;
    char path[1200],message[160];
    SDL_Texture *paper_texture;
    uint8_t paper[96*64*4];
    unsigned paper_width,panel_height,panel_width;
} RingsSettings;
#endif
#endif
