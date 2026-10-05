# RROP — Rings of Power Recompiled

[Русская версия](README.ru.md) · [Build and play](docs/usage.md) · [Settings](docs/settings.md)

[![Support RROP on Ko-fi](https://storage.ko-fi.com/cdn/kofi2.png)](https://ko-fi.com/O6R42871XC)

If RROP is useful to you, you can buy the author a coffee. Thank you for supporting development!

RROP translates the Sega Genesis / Mega Drive version of **Rings of Power**
into a native Linux or Windows executable. It statically recompiles Motorola
68000 and the game's Z80 sound code to C, with a runtime for the console's
memory, video, input and sound hardware.

The project focuses on one verified game revision, with optional improvements:

- Widescreen world rendering that adapts to the window's aspect ratio.
- Viewport zoom from 50% to 100% and smooth outdoor camera scrolling.
- Live replacement of the game's text with an external TTF/OTF font.
- Mouse movement and the game's native automatic walking.
- YM2612/PSG sound, Linux builds and Windows x64 packaging.
- Five manual saves and five rotating autosaves, every five minutes of active play.
- In-game Settings and save menus styled using the game's parchment.
- Diagnostic reports and emergency snapshots for native Void errors.

Classic presentation remains selectable. Interiors and battles use the original
viewport at 100% zoom to avoid repeating fixed scenes outside their boundaries.
This branch also adds [indoor camera and hero smoothing](docs/native-motion.md).

## Screenshots

### Widescreen and zoom

| Closer view | Zoomed-out view |
| --- | --- |
| ![Widescreen world with a closer zoom](docs/images/widescreen-close.png) | ![Widescreen world zoomed out](docs/images/widescreen-zoomed-out.png) |

### Original viewport with zoom

| Closer view | Zoomed-out view |
| --- | --- |
| ![Original game viewport with a closer zoom](docs/images/original-viewport-close.png) | ![Original game viewport zoomed out](docs/images/original-viewport-zoomed-out.png) |

### Settings

![In-game Settings menu with parchment styling](docs/images/settings.png)

Screenshots were captured during development under the previous GenesisRecomp name.

## Quick start on Linux

Install Python 3.10+, a C11/C++17 compiler, pkg-config, SDL2 and SDL2_ttf development
packages. On Ubuntu/Debian:

```sh
sudo apt install git python3 build-essential pkg-config libsdl2-dev libsdl2-ttf-dev fonts-dejavu-core
git clone https://github.com/kruzeman/RROP.git
cd RROP
mkdir -p roms
```

Place your own `Rings of Power (UE) [!].gen` in `roms`, then:

```sh
python3 examples/build_rings_of_power.py 'roms/Rings of Power (UE) [!].gen' \
  --text-renderer rings-text
./build/rings-of-power/rings-of-power --window --audio on \
  --widescreen --zoom --smooth-camera --mouse \
  --font /usr/share/fonts/truetype/dejavu/DejaVuSans.ttf
```

Use **F10**, **Esc**, or **System → Settings** to change features; choose **Exit**
there to quit. Arrow keys move; **Z/X/C** are Genesis **A/B/C**.
See the [manual](docs/usage.md) for Windows, other Linux distributions,
controls, saves and troubleshooting.

## Game data and compatibility

The required raw 1 MiB ROM has SHA-256:

```text
36303fc447c433ebc69c3d4df86c783c86b383e0acead1c19595f13269e248f5
```

**This repository contains the tool's source, not the game.** Supply your own ROM.
Generated C, executable files and Windows packages embed game data and are not
included in the source repository. RROP's license does not grant rights to the
original game, its artwork, music or fonts.

Compatibility is experimental; a complete playthrough is not verified. Missing
translations can still stop execution. Native long-session errors are monitored,
but their underlying cause has not yet been fixed. Full-machine saves preserve
game RAM and do not perform the original EEPROM loader's cleanup.

## Development

See [architecture](docs/architecture.md), [contributing](CONTRIBUTING.md) and
[Void diagnostics](docs/diagnostics.md). Core regression tests use synthetic
programs; optional original-ROM checks skip when the ROM is absent.

The project was extracted from the Rings of Power development in
[GenesisRecomp](https://github.com/kruzeman/GenesisRecomp), source commit
`5a3207c` (see [provenance](docs/provenance.md) for the full revision).
The shared engine retains the internal Python package name `genesis_recompiler`.

RROP's original code is [MIT licensed](LICENSE). The bundled ymfm sources retain
their BSD-3-Clause license; see [third-party notices](THIRD_PARTY_NOTICES.md).
