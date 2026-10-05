# Build and play

[Русская версия](usage-ru.md) · [Home](../README.md)

## Required ROM

Use the raw, big-endian `Rings of Power (UE) [!].gen`, exactly 1,048,576 bytes.
The build script verifies SHA-256:

```text
36303fc447c433ebc69c3d4df86c783c86b383e0acead1c19595f13269e248f5
```

Renaming a different dump does not make it compatible. ZIP/7z and interleaved
SMD images are not direct inputs. Store your own ROM in the ignored `roms/`
directory. No ROM download is provided by this project.

## Linux

Requirements: Python 3.10+, a C11 compiler, C++17 compiler, pkg-config, SDL2
and SDL2_ttf development files. The Python tools use the standard library;
no pip installation is needed for a checkout build.

Ubuntu/Debian:

```sh
sudo apt update
sudo apt install git python3 build-essential pkg-config libsdl2-dev libsdl2-ttf-dev fonts-dejavu-core
```

Arch Linux:

```sh
sudo pacman -S --needed git python base-devel sdl2 sdl2_ttf ttf-dejavu
```

Fedora:

```sh
sudo dnf install git python3 gcc gcc-c++ make pkgconf-pkg-config SDL2-devel SDL2_ttf-devel dejavu-sans-fonts
```

Clone and build:

```sh
git clone https://github.com/kruzeman/RROP.git
cd RROP
mkdir -p roms
# Place your own ROM in roms/ before the next command.
python3 examples/build_rings_of_power.py 'roms/Rings of Power (UE) [!].gen' \
  --text-renderer rings-text
```

Compilation may take several minutes. Output is
`build/rings-of-power/rings-of-power`. Window builds include widescreen, zoom,
smooth camera, mouse controls, saves and Settings. The sound backend defaults
to `ymfm`. `--text-renderer rings-text` additionally compiles external-font
support; without it SDL2_ttf is not required.

Launch with enhancements:

```sh
./build/rings-of-power/rings-of-power --window --audio on \
  --widescreen --zoom --smooth-camera --mouse \
  --font /usr/share/fonts/truetype/dejavu/DejaVuSans.ttf
```

The example font path applies to Debian/Ubuntu. On other distributions provide
an existing TTF/OTF path; `fc-match -f '%{file}\n' 'DejaVu Sans'` can locate one.
Fonts are not bundled. The original text can be used by omitting `--font`.

The launcher `./run-rings-of-power.sh` starts the local build and forwards
additional runtime arguments. For example:

```sh
./run-rings-of-power.sh --widescreen --zoom --smooth-camera --mouse
```

Choose **Classic** in Settings for the original presentation. Saved Settings
take precedence over launch defaults.

## macOS (experimental)

Use the same build script as Linux. Requirements are Python 3.10+, Clang
from Command Line Tools, SDL2 and pkg-config. External fonts additionally
require SDL2_ttf. No Python package installation is needed.

Install any missing dependencies:

```sh
xcode-select --install
brew install python pkgconf sdl2-compat
# Optional, for external text rendering:
brew install sdl2_ttf
```

Homebrew provides the [SDL2 compatibility layer](https://formulae.brew.sh/formula/sdl2-compat)
and [SDL2_ttf](https://formulae.brew.sh/formula/sdl2_ttf). An existing SDL2
installation also works.

Place your verified ROM in `roms/`, then run from the project directory:

```sh
python3 examples/build_rings_of_power.py 'roms/Rings of Power (UE) [!].gen'
./run-rings-of-power.command
```

The launcher also opens with a double-click in Finder. Saves and Settings
are stored in the project's `saves/` directory. For external fonts, build
with `--text-renderer rings-text` and launch with `--font /path/to/font.ttf`.

Check the tools without a game ROM using `make demo` and `make test`.
Window tests use SDL's dummy driver; verify a visible window and audible
sound by launching the game from a regular Terminal or Finder session.
The executable targets the current Mac; a universal `.app` and portable
library bundle are not packaged yet.

## Windows

### Cross-build from Linux

Ubuntu/Debian dependencies:

```sh
sudo apt install python3 gcc-mingw-w64-x86-64 g++-mingw-w64-x86-64 \
  binutils-mingw-w64-x86-64 pkg-config ca-certificates
python3 examples/build_rings_windows.py 'roms/Rings of Power (UE) [!].gen'
```

The helper uses `x86_64-w64-mingw32-gcc`, matching `g++` and `objdump`.
If your toolchain explicitly requires the POSIX variants:

```sh
python3 examples/build_rings_windows.py 'roms/Rings of Power (UE) [!].gen' \
  --cc x86_64-w64-mingw32-gcc-posix --cxx x86_64-w64-mingw32-g++-posix
```

The first build downloads the pinned SDL2 2.32.10 and SDL2_ttf 2.24.0 MinGW SDKs
and verifies their checksums. They are cached in `build/windows-sdk`.
Linux SDL development packages are not used for cross-compilation.

### Build on Windows

Install [MSYS2](https://www.msys2.org/) and open its **UCRT64** terminal.
Run `pacman -Syu`; reopen UCRT64 and repeat if requested. Then:

```sh
pacman -S --needed git mingw-w64-ucrt-x86_64-python \
  mingw-w64-ucrt-x86_64-gcc mingw-w64-ucrt-x86_64-binutils \
  mingw-w64-ucrt-x86_64-pkgconf
git clone https://github.com/kruzeman/RROP.git
cd RROP
mkdir -p roms
# Add your ROM, then:
python examples/build_rings_windows.py 'roms/Rings of Power (UE) [!].gen' \
  --cc gcc --cxx g++ --objdump objdump
```

### Run the result

The output is `build/rings-windows/RROP-Windows-x64.zip`. Extract the entire
archive and run **Play.cmd**. Keep the DLLs beside `rings-of-power.exe`.
The target computer does not need Python, WSL or a compiler. The launcher uses
Windows' installed Arial font; change `--font` to use another font.

PowerShell example:

```powershell
.\rings-of-power.exe --window --audio on --widescreen --zoom --smooth-camera --mouse `
  --font "$env:WINDIR/Fonts/arial.ttf"
```

The ZIP contains game data embedded in the executable; it is a local build
artifact, not a public release produced by this source repository.

## Controls

| Input | Action |
| --- | --- |
| Arrow keys | Genesis directions |
| Z / X / C | Genesis A / B / C |
| Enter | Genesis Start; confirm host menus |
| F10 | Open/close Settings |
| Esc | Open Settings; back within host menus |
| Settings → Exit | Quit |
| F5 / F9 | Choose a manual save / load slot |
| Space | Pause/resume gameplay |
| Tab, held | Fast-forward |
| Mouse wheel | Zoom 50–100% when Zoom is enabled |
| Middle mouse button / 0 | Reset zoom to 100% |
| Left mouse button, held | Move toward the cursor in the outdoor world |
| Right mouse button | One native A + direction automatic-walk request |

Mouse walking is directional, not arbitrary point-and-click pathfinding.
Native automatic walking stops at intersections and interactive objects.
Menus and fixed scenes do not receive outdoor mouse-walking requests.
SDL2 gamepads work in Classic and Enhanced. By default, D-pad/left stick move,
and controller X/A/B are Genesis A/B/C. Back opens Settings; LB/RB open save/load.
**Control settings** enables/disables gamepad input and selects one of two layouts.
See [gamepad controls](gamepads.md) for mappings and hotplug behavior.
**System → Help** toggles the on-screen controller hint, which defaults to off.

## Saves and Settings

There are five manual slots and five rotating autosaves. Autosaves run every
five minutes of active wall-clock play; paused gameplay and host menus do not
count. The original Save/Load/Continue entry points open the host slot chooser.
Use Up/Down and Enter, X or Z to select; Esc returns.

Default directories:

| Platform | Location |
| --- | --- |
| Linux with absolute `XDG_STATE_HOME` | `$XDG_STATE_HOME/genesisrecomp/rings-of-power` |
| Other Linux | `~/.local/state/genesisrecomp/rings-of-power` |
| Windows | `%LOCALAPPDATA%/GenesisRecomp/rings-of-power` |

These legacy paths are retained so existing saves and Settings remain available.
Use `--save-dir /path/to/saves` to select another location.
Files are `manual-1.grs` … `manual-5.grs`, `auto-1.grs` … `auto-5.grs`
and `settings.cfg`. Back up that directory before updating builds.

Saves require the same ROM revision and audio mode; load a save made with
`--audio on` using `--audio on`. Linux and Windows share the format, but
compatibility across future source revisions is not guaranteed. Settings are
stored separately and are not replaced by loading a slot.

These are full-machine checkpoints, including RAM, CPU, video and sound state.
They do not perform the temporary-table cleanup of the original EEPROM loader.
See [Void diagnostics](diagnostics.md) for the long-session issue.

## Headless and troubleshooting

A minimal build does not need SDL or the audio compiler:

```sh
python3 examples/build_rings_of_power.py 'roms/Rings of Power (UE) [!].gen' \
  --frontend headless --sound none
./build/rings-of-power/rings-of-power --headless --audio stub --limit 1000000
```

This uses the same default output path and replaces the previous window build.
To keep both, supply `--output build/rings-headless/rings-of-power` at build time.

- `--sound ymfm` is a **build** option; `--audio on` is a **runtime** option.
  If sound was not compiled in, rebuild with the default sound backend.
  `--audio stub` disables Z80 execution and is silent.
- `wrong ROM revision`: compare the dump's checksum, not just its filename.
- A missing SDL/pkg-config error: install development packages, not only runtime libraries.
- Missing Windows DLLs: extract the whole ZIP; do not copy only the executable.
- Launch flags seem ineffective: persisted `settings.cfg` takes precedence.
  Change Settings, or close the game and remove only that file to reset defaults.
- `status=budget` after a bounded headless run means the instruction limit was reached.
  `status=fault` or `execution stopped` requires the reported address and source revision.
- A Void error writes `diagnostics/void-error.txt` and, when possible,
  `diagnostics/void-error.grs` beside saves. It is monitored, not yet repaired.

After pulling changes, rebuild the executable. `git pull` does not update a
previously compiled binary.
