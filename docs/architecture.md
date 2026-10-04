# Architecture

RROP keeps the shared engine's internal Python package name
`genesis_recompiler`. The user-facing target is the verified Rings of Power ROM.

## Build pipeline

1. `examples/build_rings_of_power.py` validates the ROM hash and extracts the
   original Z80 bootstrap, its verified patched variant and the sound driver.
2. `decode.py`, `discovery.py`, `callback_discovery.py` and `ram_discovery.py`
   discover reachable 68000 code and supported indirect-call patterns.
3. `z80.py` translates declared sound-code images and guards their instruction
   variants against the actual bytes in Z80 RAM.
4. `emit.py` emits C operations and embeds the runtime headers and game data.
5. `build.py` compiles C11 operations and the optional C++17 ymfm adapter.
   `windows.py` supplies verified MinGW SDKs and resolves packaged DLL imports.

The generated program dispatches translated operations. It does not decode
arbitrary 68000 opcodes at runtime. Undiscovered addresses remain execution faults.

## Console runtime

`runtime.h` owns CPU state, the memory bus and the execution loop.
The original 64 KiB work RAM is retained; a modern host does not automatically
expand the game's fixed tables or change its 16-bit arithmetic.

The VDP modules implement tile/sprite rendering, palette/video memory and
frame/interrupt timing. Z80 bus/CPU modules execute statically translated sound
code. `audio_ymfm.cpp` adapts the BSD-licensed ymfm YM2612 implementation; PSG
and sample mixing are handled by the audio modules. SDL2 presents video and
collects host input. Timing and hardware behavior remain experimental.

## Rings presentation and input

`rings_wide_*`, `rings_zoom.h` and `rings_window.h` build the expanded outdoor
view, compose its interface and map it to the actual window. These depend on
verified game render routines and are specific to this ROM revision.
`rings_scene.h` identifies fixed interiors and battles for native presentation.

`rings_text_capture.h`, `rings_text.h` and `rings_font_sdl.h` capture the game's
text and redraw it with an external font. They do not substitute a fixed list
of translated dialogue strings. `rings_camera*` interpolates visual map motion;
it does not accelerate game logic. `rings_mouse*` submits directional movement
and native A + direction requests rather than implementing independent pathfinding.

`rings_settings_*` manages host preferences and adds Settings entry points to
verified menus. The old `GenesisRecomp Settings 1` file marker is deliberately
retained for compatibility, as are save-directory names.

## Saves and diagnostics

`save_state.h` serializes machine sections. `rings_saves.h` handles slots,
checksums, atomic replacement and the wall-clock autosave schedule.
Loading a checkpoint restores its RAM; it does not call the original EEPROM
loader or recreate the game's temporary object tables.

`rings_object_diagnostics*` tracks the headers of the game's two 56-entry
tables. `write8` marks header changes; the outer loop collects host history
after each translated instruction. At native error-handler entry `$012FA0`,
it writes a report and a separate emergency checkpoint. No cleanup or error
suppression is performed. See [diagnostics](diagnostics.md).

## Source layout

| Directory | Contents |
| --- | --- |
| `genesis_recompiler/` | Translator, runtime and vendored ymfm |
| `examples/` | Linux/Windows game builders and synthetic demo generator |
| `tests/` | Core and Rings regression checks |
| `docs/` | English documentation and Russian companion guides |
| `build/`, `roms/` | Local generated/private inputs; excluded from Git |

Other game profiles, experiments and generated artifacts from GenesisRecomp
are not part of this extracted project.
