/* Functional Mode 5 VDP state. Transfers complete synchronously; no renderer. */
#ifndef GENESIS_VDP_STATE_H
#define GENESIS_VDP_STATE_H
#ifdef GENESIS_RINGS_MENU_FONT
typedef struct {
    uint32_t pattern, run;
    uint16_t entry;
    uint8_t ch;
} RingsTextMark;
typedef struct {
    uint32_t run;
    uint16_t x,y;
    uint8_t ch,layer,rgb[3];
} RingsTextVisible;
#endif
typedef struct {
    uint8_t registers[24], vram[65536];
    uint16_t cram[64], vsram[40];
    uint16_t address, bus_value;
    uint8_t code, command_pending, fill_pending;
    uint64_t data_reads, data_writes, dma_bytes;
    uint16_t line, line_clock;
    uint8_t hint_counter, irq_h, irq_v, vint_status, pal;
    uint64_t frames;
    uint8_t frame[320*240*3], render_unsupported;
    uint16_t frame_width, frame_height;
    uint64_t rendered_frames;
#ifdef GENESIS_RINGS_WIDE
#ifdef GENESIS_RINGS_SMOOTH_CAMERA
    RingsCameraSnapshot camera;
    RingsNativeMotion native_motion;
#endif
    uint8_t wide_hud_active;
    uint8_t native_scene; /* Derived frame policy, not a saved user preference. */
    uint8_t wide_enabled,wide_world_visible,wide_frame[400*240*3];
    uint8_t zoom_enabled,zoom_world_visible;
    uint16_t zoom_focus_x,zoom_focus_y;
    uint8_t zoom_scene[960*704],zoom_mask[400*240],zoom_restore[400*240];
    uint8_t zoom_lift[960*704];
    uint8_t zoom_background[400*240*3],zoom_palette[16*3];
#ifdef GENESIS_RINGS_MENU_FONT
    uint8_t wide_font_frame[400*240*3];
#endif
#endif
#ifdef GENESIS_RINGS_MENU_FONT
    /* Presentation-only snapshot; never changes VRAM or the console RGB frame. */
    uint8_t font_enabled, font_hide, font_supported[128];
    RingsTextMark font_marks[32768];
    RingsTextVisible font_cells[1200];
    uint16_t font_count, font_visible;
    uint8_t font_mask[320*240], font_frame[320*240*3];
    uint64_t font_captured[2];
    uint32_t font_run, font_source, font_frame_pointer, font_offset;
    uint16_t font_attributes, font_bank;
    uint8_t font_writer;
#endif
} VDP;
#ifdef GENESIS_RINGS_WIDE
static int rings_view_wide(const VDP *v) {
    return v->wide_enabled && !v->native_scene;
}
#endif
#endif
