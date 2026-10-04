import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
from .decode import RamCodeCopy, analyze
from .emit import emit
from .build import build_executable
from .z80 import analyze_z80
from .resources import GraphicsRange, plan_resources, write_resources


def address(text):
    try:
        value = int(text, 0)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("use decimal or a 0x-prefixed address") from exc
    if not 0 <= value <= 0xFFFFFF:
        raise argparse.ArgumentTypeError("address must fit the 24-bit bus")
    return value


def graphics_range(text):
    try:
        name, offset, size = text.split(":")
        return GraphicsRange(name, int(offset, 0), int(size, 0))
    except ValueError as exc:
        raise argparse.ArgumentTypeError("use NAME:ROM_OFFSET:BYTES, for example title:0x10000:0x2000") from exc


def tile_range(text):
    value = graphics_range(text)
    return GraphicsRange(value.name, value.offset, value.size, 'genesis-4bpp')


def z80_overlay(text):
    try:
        location, raw = text.split(":", 1)
        pc, data = int(location, 0), bytes.fromhex(raw)
        if not data or pc < 0 or pc + len(data) > 8192:
            raise ValueError("overlay must fit the 8 KiB Z80 RAM")
        return pc, data
    except ValueError as exc:
        raise argparse.ArgumentTypeError("use ADDRESS:HEXBYTES, for example 0x0:e9; overlay must fit Z80 RAM") from exc


def ram_copy(text):
    try:
        source, destination, size = (int(part, 0) for part in text.split(":"))
        return RamCodeCopy(source, destination, size)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("use ROM_OFFSET:RAM_ADDRESS:BYTES, for example 0x6d96a:0xff9d2e:0xc8") from exc


def z80_image_entry(text):
    try:
        index, pc = (int(part, 0) for part in text.split(':'))
        if index < 0 or not 0 <= pc < 0x4000:
            raise ValueError('invalid image entry')
        return index, pc
    except ValueError as exc:
        raise argparse.ArgumentTypeError('use IMAGE_INDEX:RAM_PC; image indices start at zero and PCs must fit RAM/mirror') from exc


def trap_data(text):
    try:
        number, count = (int(part, 0) for part in text.split(':'))
        if not 0 <= number <= 15 or not 0 <= count <= 256 or count & 1:
            raise ValueError('invalid trap annotation')
        return number, count
    except ValueError as exc:
        raise argparse.ArgumentTypeError('use TRAP_NUMBER:BYTES; number 0..15, even inline data length 0..256') from exc


def main(argv=None):
    parser = argparse.ArgumentParser(description="Statically recompile reachable MC68000 code from a raw Genesis ROM to C or a native executable.")
    parser.add_argument("rom", type=Path)
    parser.add_argument("-o", "--output", type=Path, required=True, help="C source path, or executable path with --build")
    parser.add_argument("--build", action="store_true", help="compile the translation into an executable with the ROM embedded")
    parser.add_argument("--cc", default="cc", help="C compiler executable; defaults to cc, may be a cross compiler")
    parser.add_argument("--cxx", default="c++", help="C++17 compiler/linker for the optional ymfm sound module; select the matching cross compiler if needed")
    parser.add_argument("--sound", choices=("none", "ymfm"), default="none", help="optional FM/PSG synthesis; ymfm requires --build and a C++17 compiler; the CPU translation remains C11")
    parser.add_argument("--frontend", choices=("headless", "sdl2"), default="headless", help="optional SDL2 window/input support; requires --build and SDL2 development files")
    parser.add_argument("--text-renderer", choices=("none", "rings-text", "rings-menu"), default="none", help="optional external SDL2_ttf fonts from live text calls in the verified Rings of Power [!] ROM; rings-menu is a compatibility alias; requires --build --frontend sdl2")
    parser.add_argument("--rings-widescreen", action="store_true", help="compile the experimental 400-pixel Rings of Power scene presenter; verified [!] ROM only; requires --build")
    parser.add_argument("--rings-saves", action="store_true", help="persistent five manual and five automatic full-state slots; verified Rings [!] ROM only; requires --build")
    parser.add_argument("--rings-zoom", action="store_true", help="compile mouse-wheel world zoom in the verified Rings ROM; requires --build --frontend sdl2")
    parser.add_argument("--emit-c", type=Path, help="also retain generated C when using --build")
    parser.add_argument("--entry", type=address, action="append", default=[], help="additional code entry point, repeatable")
    parser.add_argument("--noreturn", type=address, action="append", default=[], help="known function which does not return to its direct caller; omit call fall-through discovery, preserve runtime stack operations; repeatable")
    parser.add_argument("--trap-data", type=trap_data, action="append", default=[], help="verified TRAP handler ABI TRAP_NUMBER:BYTES of inline parameters; affects static discovery only, the original handler must advance the stacked return PC; repeatable")
    parser.add_argument("--m68k-copy", type=ram_copy, action="append", default=[], help="statically translate a known ROM-to-work-RAM code copy ROM_OFFSET:RAM_ADDRESS:BYTES; checks instruction bytes at runtime, does not upload them; repeatable for disjoint copies")
    parser.add_argument("--m68k-mutable-address", type=address, action="append", default=[], help="RAM instruction PC of a verified MOVE with self-modifying absolute-long source; guard opcode/destination and read the declared address operand as data; repeatable")
    parser.add_argument("--z80-image", type=Path, action="append", default=[], help="Z80 RAM code image for static analysis only (1..8192 bytes), repeatable; runtime RAM is populated by the game")
    parser.add_argument("--z80-entry", type=address, action="append", default=[], help="additional Z80 RAM code entry, repeatable")
    parser.add_argument("--z80-image-entry", type=z80_image_entry, action="append", default=[], help="additional entry for one image IMAGE_INDEX:RAM_PC (zero-based --z80-image order); repeatable")
    parser.add_argument("--z80-overlay", type=z80_overlay, action="append", default=[], help="compile an additional modified-code variant ADDRESS:HEXBYTES, repeatable")
    parser.add_argument("--z80-mutable-immediate", type=address, action="append", default=[], help="instruction address of a verified self-modified two-byte Z80 LD r,n; compile all 256 operand variants with opcode guards; repeatable")
    parser.add_argument("--z80-mutable-displacement", type=address, action="append", default=[], help="verified IX/IY memory instruction with a self-modified displacement; compile 256 signed byte variants with other bytes guarded; repeatable")
    parser.add_argument("--cartridge", choices=("plain", "ea-24c01"), default="plain", help="explicit cartridge wiring profile; ea-24c01 enables 128-byte serial EEPROM at $200001")
    parser.add_argument("--report", type=Path, help="write analysis JSON and disassembly")
    parser.add_argument("--allow-partial", action="store_true", help="emit even with decode errors; execution faults if it reaches missing code")
    parser.add_argument("--resources-dir", type=Path, help="export external ROM data and a manifest here; executable embeds only translated code bytes and vectors/header")
    parser.add_argument("--graphics-range", type=graphics_range, action="append", default=[], help="verified graphics blob NAME:ROM_OFFSET:BYTES; original encoding, repeatable; requires --resources-dir")
    parser.add_argument("--tile-range", type=tile_range, action="append", default=[], help="verified raw Genesis 4bpp tile bank NAME:ROM_OFFSET:BYTES; exports original bytes and grayscale PPM atlas")
    parser.add_argument("--rings-smooth-camera", action="store_true", help="compile optional smooth Rings outdoor scrolling; requires --build --frontend sdl2")
    args = parser.parse_args(argv)
    if args.text_renderer != "none" and (not args.build or args.frontend != "sdl2"):
        parser.error("--text-renderer rings-text requires --build --frontend sdl2")
    if args.rings_saves and not args.build:
        parser.error("--rings-saves requires --build")
    if args.rings_widescreen and not args.build:
        parser.error("--rings-widescreen requires --build")
    if args.rings_zoom and (not args.build or args.frontend != "sdl2"):
        parser.error("--rings-zoom requires --build --frontend sdl2")
    if args.rings_smooth_camera and (not args.build or args.frontend != "sdl2"):
        parser.error("--rings-smooth-camera requires --build --frontend sdl2")
    if (args.graphics_range or args.tile_range) and args.resources_dir is None:
        parser.error("--graphics-range requires --resources-dir")
    if args.emit_c and not args.build:
        parser.error("--emit-c requires --build")
    if args.sound != "none" and not args.build:
        parser.error("--sound requires --build; generated C can be linked manually with the sound object and -DGENESIS_AUDIO")
    if args.frontend != "headless" and not args.build:
        parser.error("--frontend requires --build; emitted C can be compiled separately with -DGENESIS_SDL2")
    if (args.z80_entry or args.z80_image_entry or args.z80_overlay or args.z80_mutable_immediate or args.z80_mutable_displacement) and not args.z80_image:
        parser.error("Z80 entry/overlay/mutable options require --z80-image")
    if any(pc >= 0x4000 for pc in args.z80_entry):
        parser.error("--z80-entry must be in Z80 RAM or its mirror (0..0x3fff)")
    try:
        paths = [args.rom, *args.z80_image, args.output]
        if args.report: paths.append(args.report)
        if args.emit_c: paths.append(args.emit_c)
        for index, path in enumerate(paths):
            for other in paths[:index]:
                if path.exists() and other.exists() and path.samefile(other):
                    raise ValueError("input files and all output artifacts must use different paths")
        paths = [p.resolve() for p in paths]
        if len(paths) != len(set(paths)):
            raise ValueError("input files and all output artifacts must use different paths")
        rom = args.rom.read_bytes()
        if args.text_renderer in ("rings-text", "rings-menu") and hashlib.sha256(rom).hexdigest() != "36303fc447c433ebc69c3d4df86c783c86b383e0acead1c19595f13269e248f5":
            raise ValueError("Rings text renderer requires the verified Rings of Power (UE) [!] ROM revision")
        if (args.rings_widescreen or args.rings_zoom or args.rings_smooth_camera) and hashlib.sha256(rom).hexdigest() != "36303fc447c433ebc69c3d4df86c783c86b383e0acead1c19595f13269e248f5":
            raise ValueError("Rings widescreen requires the verified Rings of Power (UE) [!] ROM revision")
        if args.rings_saves and hashlib.sha256(rom).hexdigest() != "36303fc447c433ebc69c3d4df86c783c86b383e0acead1c19595f13269e248f5":
            raise ValueError("Rings saves require the verified Rings of Power (UE) [!] ROM revision")
        if not 8 <= len(rom) <= 0x400000:
            raise ValueError("expected a raw, unswapped ROM between 8 bytes and 4 MiB; .smd and banked ROMs are not supported")
        entry = int.from_bytes(rom[4:8], "big") & 0xFFFFFF
        interrupt_targets = {level: int.from_bytes(rom[(24+level)*4:(25+level)*4], "big") & 0xFFFFFF for level in (4,6) if len(rom) >= (25+level)*4}
        interrupt_targets = {level: target for level, target in interrupt_targets.items()
                             if not target&1 and (8 <= target < len(rom) or any(
                                 copy.address <= target < copy.address+copy.size for copy in args.m68k_copy))}
        program = analyze(rom, [entry, *interrupt_targets.values(), *args.entry], args.m68k_copy, args.noreturn, args.m68k_mutable_address, args.trap_data)
        for level in (4, 6):
            target = int.from_bytes(rom[(24+level)*4:(25+level)*4], 'big') & 0xffffff
            if not target & 1 and any(copy.address <= target < copy.address+copy.size for copy in program.ram_copies):
                interrupt_targets[level] = target
        zprogram = analyze_z80([path.read_bytes() for path in args.z80_image], args.z80_entry, args.z80_overlay, args.z80_mutable_immediate, args.z80_image_entry, args.z80_mutable_displacement) if args.z80_image else None
        header = rom[0x100:0x110].decode("ascii", "replace").strip() if len(rom) >= 0x110 else ""
        resource_plan = plan_resources(program, [*args.graphics_range, *args.tile_range]) if args.resources_dir is not None else None
        report = {
            "rom_sha256": hashlib.sha256(rom).hexdigest(),
            "rom_bytes": len(rom), "reset_pc": entry,
            "cartridge": args.cartridge,
            "sound_backend": args.sound,
            "resources": resource_plan.manifest() if resource_plan else None,
            "interrupt_targets": interrupt_targets,
            "noreturn_targets": list(program.noreturn),
            "trap_targets": program.trap_targets,
            "trap_inline_data": [{"number": number, "bytes": count} for number, count in program.trap_data],
            "initial_sp": int.from_bytes(rom[:4], "big"), "console_header": header,
            "instruction_count": program.instruction_count,
            "instruction_addresses": len(program.instructions),
            "errors": [{"pc": pc, "message": message} for pc, message in sorted(program.errors.items())],
            "m68k_ram_variant_errors": program.ram_variant_errors,
            "indirect_transfers": program.indirect,
            "jump_tables": [{"pc": pc, **table} for pc, table in sorted(program.jump_tables.items())],
            "return_tables": [{"pc": pc, **table} for pc, table in sorted(program.return_tables.items())],
            "ram_callbacks": [{"pc": pc, **callback} for pc, callback in sorted(program.ram_callbacks.items())],
            "memory_callbacks": [{"pc": pc, **callback} for pc, callback in sorted(program.memory_callbacks.items())],
            "pointer_tables": [{"pc": pc, **table} for pc, table in sorted(program.pointer_tables.items())],
            "value_transfers": [{"pc": pc, **transfer} for pc, transfer in sorted(program.value_transfers.items())],
            "inline_pointer_tables": [{"pc": pc, **table} for pc, table in sorted(program.inline_pointer_tables.items())],
            "inline_relative_tables": [{"pc": pc, **table} for pc, table in sorted(program.inline_relative_tables.items())],
            "m68k_ram_copies": [{"rom_offset": copy.rom_offset, "address": copy.address, "size": copy.size} for copy in program.ram_copies],
            "m68k_ram_uploads": program.ram_uploads,
            "m68k_auto_mutable_addresses": list(program.auto_mutable_addresses),
            "m68k_mutable_addresses": list(program.mutable_addresses),
            "m68k_ram_variants": [{"pc": pc, "rom_offset": v.image.rom_offset + pc - v.image.address,
                "bytes": v.instruction.raw.hex(), "assembly": str(v.instruction),
                "mutable_address": v.mutable_address} for pc, variants in sorted(program.ram_variants.items())
                for v in variants],
            "unrolled_blocks": [{"pc": pc, **block} for pc, block in sorted(program.unrolled_blocks.items())],
            "instructions": [{"pc": pc, "bytes": inst.raw.hex(), "assembly": str(inst)} for pc, inst in sorted(program.instructions.items())],
            "z80": {
                "instruction_variants": sum(len(variants) for variants in zprogram.instructions.values()) if zprogram else 0,
                "mutable_immediates": list(zprogram.mutable_immediates) if zprogram else [],
                "image_entries": [{"image": index, "pc": pc} for index, pc in zprogram.image_entries] if zprogram else [],
                "mutable_displacements": list(zprogram.mutable_displacements) if zprogram else [],
                "errors": zprogram.errors if zprogram else [],
                "instructions": [{"pc": pc, "bytes": inst.raw.hex(), "operation": inst.op, "args": inst.args} for pc, variants in sorted(zprogram.instructions.items()) for inst in variants] if zprogram else [],
            },
        }
        incomplete = program.errors or program.ram_variant_errors or (zprogram and zprogram.errors)
        if resource_plan and not incomplete:
            write_resources(resource_plan, args.resources_dir, paths, manifest=False)
        if args.report:
            args.report.parent.mkdir(parents=True, exist_ok=True)
            args.report.write_text(json.dumps(report, indent=2) + "\n")
        print(f"reset=${entry:06x}, ROM={len(rom)} bytes, translated={program.instruction_count} instructions")
        for pc, message in sorted(program.errors.items()): print(f"${pc:06x}: {message}", file=sys.stderr)
        for error in program.ram_variant_errors:
            if error['pc'] not in program.errors:
                print(f"RAM ${error['pc']:06x} image ${error['rom_offset']:06x}: {error['message']}", file=sys.stderr)
        if zprogram:
            print(f"Z80 translated={report['z80']['instruction_variants']} guarded instruction variants")
            for error in zprogram.errors:
                print(f"Z80 ${error['pc']:04x} variant {error['variant']}: {error['message']}", file=sys.stderr)
        if program.indirect:
            print("indirect transfers present; add --entry addresses for targets not otherwise discovered", file=sys.stderr)
        if incomplete and not args.allow_partial:
            print("translation stopped; use --allow-partial for an explicitly incomplete build", file=sys.stderr)
            return 1
        if resource_plan:
            write_resources(resource_plan, args.resources_dir, paths, manifest=False)
        relative = os.path.relpath(args.resources_dir.resolve(), args.output.resolve().parent) if resource_plan else "resources"
        source = emit(program, zprogram, args.cartridge, resource_plan, relative)
        if args.text_renderer in ("rings-text", "rings-menu"):
            source = "#define GENESIS_RINGS_MENU_FONT 1\n" + source
        if args.rings_widescreen or args.rings_zoom or args.rings_smooth_camera:
            source = "#define GENESIS_RINGS_WIDE 1\n" + source
        if args.rings_smooth_camera:
            source = "#define GENESIS_RINGS_SMOOTH_CAMERA 1\n" + source
        if args.rings_saves:
            source = "#define GENESIS_RINGS_SAVES 1\n" + source
        if args.build:
            if args.emit_c:
                args.emit_c.parent.mkdir(parents=True, exist_ok=True)
                args.emit_c.write_text(source)
            build_executable(source, args.output, args.cc, args.frontend, args.sound, args.cxx, args.text_renderer, args.rings_widescreen or args.rings_zoom or args.rings_smooth_camera)
            print("built executable with " + ("external resources" if resource_plan else "ROM embedded") + "; compatibility is limited to the supported CPU and memory runtime")
        else:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(source)
        if resource_plan:
            write_resources(resource_plan, args.resources_dir, paths)
            print(f"external resources={report['resources']['external_bytes']} bytes; embedded={len(resource_plan.code)} bytes; manifest={args.resources_dir / 'manifest.json'}")
        print(f"wrote {args.output}")
        return 0
    except (OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
