"""Build the verified Rings of Power [!] revision using only local tools."""
import argparse
import hashlib
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from genesis_recompiler.build import compiler_target, windows_target
ROM_SHA256 = "36303fc447c433ebc69c3d4df86c783c86b383e0acead1c19595f13269e248f5"


def z80_images(rom):
    """Original uploads and the bootstrap's verified JP (HL) patch.

    The 68000 loader at $0EB856 copies $1576 bytes from $0EBB6E to Z80
    RAM. Images only describe static code; the game still performs every upload.
    The replacement driver starts with DI and polls its shared-RAM mailboxes.
    """
    boot = rom[0x2C4:0x2EA]
    driver = rom[0xEBB6E:0xED0E4]
    if len(boot) != 38 or len(driver) != 0x1576:
        raise ValueError("incomplete Rings of Power Z80 uploads")
    return boot, b"\xe9" + boot[1:], driver


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("rom", type=Path, help="Rings of Power (UE) [!].gen")
    parser.add_argument("--cc", default="cc", help="C compiler executable")
    parser.add_argument("--cxx", default="c++", help="C++17 compiler/linker for ymfm")
    parser.add_argument("--output", type=Path, help="executable path; defaults to build/rings-of-power/rings-of-power[.exe]")
    parser.add_argument("--sound", choices=("none", "ymfm"), default="ymfm", help="defaults to FM/PSG synthesis; none builds without the sound backend")
    parser.add_argument("--frontend", choices=("headless", "sdl2"), default="sdl2", help="defaults to the SDL2 window build; headless needs no SDL2")
    parser.add_argument("--text-renderer", choices=("none", "rings-text", "rings-menu"), default="none", help="rings-text enables live TTF/OTF text via SDL2_ttf; rings-menu is a compatibility alias; requires sdl2 frontend")
    parser.add_argument("--widescreen", action="store_true", help="include expanded world view in headless builds; window builds always include it; enable in Settings or at launch")
    parser.add_argument("--zoom", action="store_true", help="compatibility flag: window builds include zoom; enable in Settings or with --zoom at launch")
    parser.add_argument("--mouse", action="store_true", help="compatibility flag: window builds include mouse controls; enable in Settings or with --mouse at launch")
    parser.add_argument("--smooth-camera", action="store_true", help="compatibility flag: window builds include smooth scrolling; enable in Settings or at launch")
    args = parser.parse_args()
    if args.text_renderer != "none" and args.frontend != "sdl2":
        parser.error("external fonts require --frontend sdl2")
    if (args.zoom or args.mouse or args.smooth_camera) and args.frontend != "sdl2":
        parser.error("zoom, mouse movement and smooth camera require --frontend sdl2")
    try:
        rom_path = args.rom.resolve()
        rom = rom_path.read_bytes()
        if hashlib.sha256(rom).hexdigest() != ROM_SHA256:
            parser.error("wrong ROM revision: use Rings of Power (UE) [!].gen; expected SHA-256 " + ROM_SHA256)
        suffix = ".exe" if windows_target(compiler_target(args.cc)) else ""
        executable = args.output.resolve() if args.output else ROOT / "build" / "rings-of-power" / ("rings-of-power" + suffix)
        output = executable.parent
        images = z80_images(rom)
        image_paths = [output / name for name in ("z80-boot.bin", "z80-boot-jump.bin", "z80-driver.bin")]
        artifacts = [*image_paths, executable, output / "game.c", output / "analysis.json"]
        for path in artifacts:
            if path.resolve() == rom_path or (path.exists() and path.samefile(rom_path)):
                parser.error("the ROM must use a different path from all output artifacts")
        output.mkdir(parents=True, exist_ok=True)
        for path, image in zip(image_paths, images):
            path.write_bytes(image)
        return subprocess.run([
            sys.executable, "-m", "genesis_recompiler", str(rom_path),
            "--build", "--cc", args.cc, "--cxx", args.cxx, "--sound", args.sound,
            "--frontend", args.frontend, "-o", str(executable),
            "--text-renderer", args.text_renderer,
            "--emit-c", str(output / "game.c"),
            "--report", str(output / "analysis.json"),
            *[arg for path in image_paths for arg in ("--z80-image", str(path))],
            "--z80-image-entry", "2:0x38",
            "--cartridge", "ea-24c01", "--rings-saves",
            *(["--rings-widescreen"] if args.widescreen else []),
            *(["--rings-zoom"] if args.frontend == "sdl2" or args.zoom or args.mouse else []),
            *(["--rings-smooth-camera"] if args.frontend == "sdl2" or args.smooth_camera else []),
        ], cwd=ROOT).returncode
    except (OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
