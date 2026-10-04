"""Cross-build Rings of Power with all features and a ready-to-run Windows zip."""
import argparse
import json
from pathlib import Path
import shutil
import subprocess
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from genesis_recompiler.build import BuildError, compiler_target
from genesis_recompiler.windows import TARGET, bundle_dlls, prepare_sdk, sdk_environment


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("rom", type=Path)
    parser.add_argument("--cc", default=TARGET + "-gcc")
    parser.add_argument("--cxx", default=TARGET + "-g++")
    parser.add_argument("--objdump", default=TARGET + "-objdump")
    parser.add_argument("--sdk-dir", type=Path, default=ROOT / "build" / "windows-sdk")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "build" / "rings-windows")
    args = parser.parse_args()
    try:
        root = args.output_dir.resolve()
        package = root / "RROP-Windows-x64"
        rom_path = args.rom.resolve()
        archive = root / "RROP-Windows-x64.zip"
        if package in rom_path.parents or rom_path == archive:
            raise BuildError("keep the input ROM outside the generated Windows package and zip paths")
        if compiler_target(args.cc) != TARGET or compiler_target(args.cxx) != TARGET:
            raise BuildError("this package requires matching x86_64-w64-mingw32 C and C++ compilers")
        # Validate the input before any downloads, just like the native helper.
        from examples.build_rings_of_power import ROM_SHA256
        import hashlib
        if hashlib.sha256(args.rom.read_bytes()).hexdigest() != ROM_SHA256:
            raise BuildError("wrong ROM revision: use Rings of Power (UE) [!].gen")
        prefix = prepare_sdk(args.sdk_dir)
        root.mkdir(parents=True, exist_ok=True)
        # Build artifacts stay outside the distributable: game.c contains ROM data.
        binary = root / "artifacts" / "rings-of-power.exe"
        result = subprocess.run([
            sys.executable, str(ROOT / "examples" / "build_rings_of_power.py"), str(args.rom.resolve()),
            "--cc", args.cc, "--cxx", args.cxx, "--output", str(binary),
            "--sound", "ymfm", "--frontend", "sdl2", "--text-renderer", "rings-text",
            "--widescreen", "--zoom", "--mouse", "--smooth-camera",
        ], cwd=ROOT, env=sdk_environment(prefix))
        if result.returncode:
            return result.returncode
        # Replace only our dedicated package directory after a successful build.
        if package.exists():
            shutil.rmtree(package)
        package.mkdir()
        executable = package / binary.name
        shutil.copy2(binary, executable)
        dlls = bundle_dlls(executable, package, prefix, args.cc, args.objdump)
        shutil.copytree(prefix / "licenses", package / "licenses")
        shutil.copy2(ROOT / "genesis_recompiler" / "ymfm" / "LICENSE", package / "licenses" / "ymfm.txt")
        compiler_path = Path(shutil.which(args.cc) or args.cc).resolve()
        # Debian cross-toolchain and MSYS2 both install runtime license notices.
        share = compiler_path.parent.parent / "share"
        for name in ("gcc-mingw-w64-base", "mingw-w64-common"):
            notice = share / "doc" / name / "copyright"
            if notice.is_file():
                shutil.copy2(notice, package / "licenses" / (name + ".txt"))
        for name in ("gcc-libs", "winpthreads", "mingw-w64-winpthreads"):
            notice = share / "licenses" / name
            if notice.is_dir():
                shutil.copytree(notice, package / "licenses" / name)
        # SDL's Windows main converts Unicode command-line arguments to UTF-8.
        # Use the Windows system font rather than shipping a proprietary font.
        launcher = '@echo off\r\ncd /d "%~dp0"\r\nrings-of-power.exe --window --audio on --widescreen --zoom --smooth-camera --mouse --font "%WINDIR%/Fonts/arial.ttf" %*\r\nif errorlevel 1 pause\r\n'
        (package / "Play.cmd").write_bytes(launcher.encode("ascii"))
        for name in ("README.md", "README.ru.md", "LICENSE", "THIRD_PARTY_NOTICES.md"):
            shutil.copy2(ROOT / name, package / name)
        shutil.copytree(ROOT / "docs", package / "docs")
        (package / "build-info.json").write_text(json.dumps({
            "target": TARGET, "dlls": dlls, "features": ["ymfm", "rings-text", "widescreen", "zoom", "smooth-camera", "mouse", "saves", "settings"],
        }, indent=2) + "\n", encoding="utf-8")
        temporary = archive.with_suffix(".tmp")
        with zipfile.ZipFile(temporary, "w", zipfile.ZIP_DEFLATED) as out:
            for path in sorted(package.rglob("*")):
                if path.is_file():
                    out.write(path, str(path.relative_to(root)))
        temporary.replace(archive)
        print(f"Windows package: {archive}\nLaunch Play.cmd on Windows; keep the DLLs beside the executable")
        return 0
    except (OSError, ValueError, zipfile.BadZipFile) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
