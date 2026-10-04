"""Compile a generated C translation without a shell or runtime ROM file."""
from pathlib import Path
from importlib.resources import files
import os
import shlex
import subprocess
import tempfile


class BuildError(ValueError):
    pass


def compiler_target(compiler: str) -> str:
    """Query GCC/Clang's target instead of guessing from the host or filename."""
    try:
        result = subprocess.run([compiler, "-dumpmachine"], capture_output=True, text=True)
    except FileNotFoundError as exc:
        raise BuildError(f"C compiler not found: {compiler}; select one with --cc") from exc
    return result.stdout.strip() if result.returncode == 0 else ""


def windows_target(target: str) -> bool:
    return "mingw" in target or "windows" in target


def sdl2_flags() -> tuple[list[str], list[str]]:
    """Ask the installed development package for flags; never invoke a shell."""
    flags = []
    for option in ("--cflags", "--libs"):
        try:
            result = subprocess.run([os.environ.get("PKG_CONFIG", "pkg-config"), option, "sdl2"], capture_output=True, text=True)
        except FileNotFoundError as exc:
            raise BuildError("SDL2 builds require pkg-config and SDL2 development files; on Ubuntu/Debian install pkg-config libsdl2-dev") from exc
        if result.returncode:
            raise BuildError("SDL2 development files not found; on Ubuntu/Debian install pkg-config libsdl2-dev")
        flags.append(shlex.split(result.stdout))
    return flags[0], flags[1]


def sdl2_ttf_flags() -> tuple[list[str], list[str]]:
    flags = []
    for option in ("--cflags", "--libs"):
        try:
            result = subprocess.run([os.environ.get("PKG_CONFIG", "pkg-config"), option, "SDL2_ttf"], capture_output=True, text=True)
        except FileNotFoundError as exc:
            raise BuildError("external fonts require pkg-config and SDL2_ttf development files") from exc
        if result.returncode:
            raise BuildError("SDL2_ttf development files not found; Ubuntu/Debian: libsdl2-ttf-dev; Arch: sdl2_ttf")
        flags.append(shlex.split(result.stdout))
    return flags[0], flags[1]


def build_audio_backend(output: Path, compiler: str = "c++") -> None:
    """Build one optional sound object from vendored, revision-pinned sources."""
    output = output.absolute()
    output.parent.mkdir(parents=True, exist_ok=True)
    resources = files("genesis_recompiler")
    with tempfile.TemporaryDirectory(prefix=".genesis-sound-", dir=output.parent) as work:
        root = Path(work)
        for name in ("audio_backend.h", "audio_ymfm.cpp"):
            (root / name).write_bytes(resources.joinpath(name).read_bytes())
        (root / "ymfm").mkdir()
        for resource in resources.joinpath("ymfm").iterdir():
            if resource.is_file():
                (root / "ymfm" / resource.name).write_bytes(resource.read_bytes())
        binary = root / "sound.o"
        try:
            result = subprocess.run([compiler, "-std=c++17", "-O2", "-c", str(root / "audio_ymfm.cpp"), "-o", str(binary)], capture_output=True, text=True)
        except FileNotFoundError as exc:
            raise BuildError(f"sound requires a C++17 compiler: {compiler}; select one with --cxx or build with --sound none") from exc
        if result.returncode or not binary.is_file():
            raise BuildError("sound backend compilation failed:\n" + (result.stderr or result.stdout))
        binary.replace(output)


def build_executable(source: str, output: Path, compiler: str = "cc", frontend: str = "headless", sound: str = "none", cxx: str = "c++", text_renderer: str = "none", rings_widescreen: bool = False) -> None:
    if frontend not in ("headless", "sdl2"):
        raise BuildError("unsupported frontend")
    if sound not in ("none", "ymfm"):
        raise BuildError("unsupported sound backend")
    if text_renderer not in ("none", "rings-text", "rings-menu"):
        raise BuildError("unsupported text renderer")
    if text_renderer != "none" and frontend != "sdl2":
        raise BuildError("external fonts require --frontend sdl2")
    target = compiler_target(compiler)
    windows = windows_target(target)
    if windows and sound == "ymfm" and compiler_target(cxx) != target:
        raise BuildError("Windows sound builds require matching C/C++ targets; select the MinGW C++ compiler with --cxx")
    cflags, libs = sdl2_flags() if frontend == "sdl2" else ([], [])
    if frontend == "sdl2":
        cflags = ["-DGENESIS_SDL2", *cflags]
    if rings_widescreen:
        cflags += ["-DGENESIS_RINGS_WIDE=1"]
    if text_renderer in ("rings-text", "rings-menu"):
        ttf_cflags, ttf_libs = sdl2_ttf_flags()
        cflags += ["-DGENESIS_RINGS_MENU_FONT=1", *ttf_cflags]
        libs += ttf_libs
    if windows:
        # CPU/world buffers exceed Windows' default 1 MiB stack. Keep a console
        # for fault diagnostics and avoid GCC/C++ runtime DLL dependencies.
        libs += ["-Wl,--stack,16777216", "-static-libgcc", "-mconsole"]
        if sound == "ymfm":
            libs += ["-static-libstdc++"]
    output = output.absolute()
    output.parent.mkdir(parents=True, exist_ok=True)
    # Keep the previous executable intact if compilation fails. The temporary
    # directory shares its filesystem so publishing the result is an atomic move.
    with tempfile.TemporaryDirectory(prefix=".genesis-build-", dir=output.parent) as work:
        root = Path(work)
        # An explicit .exe suffix also works on Unix and prevents Windows cross
        # compilers from silently appending a suffix to the expected output path.
        c_file, binary = root / "translation.c", root / "program.exe"
        c_file.write_text(source, encoding="utf-8")
        command = [compiler, "-std=c11", "-O2", "-Wno-unused-function", *cflags, str(c_file), "-o", str(binary), *libs]
        if sound == "ymfm":
            backend, translation = root / "sound.o", root / "translation.o"
            build_audio_backend(backend, cxx)
            command = [compiler, "-std=c11", "-O2", "-Wno-unused-function", "-DGENESIS_AUDIO", *cflags, "-c", str(c_file), "-o", str(translation)]
        try:
            result = subprocess.run(command, capture_output=True, text=True)
        except FileNotFoundError as exc:
            raise BuildError(f"C compiler not found: {compiler}; select one with --cc") from exc
        if result.returncode:
            details = result.stderr.strip() or result.stdout.strip() or "no diagnostics"
            raise BuildError(f"C compilation failed (exit {result.returncode}):\n{details}")
        if sound == "ymfm":
            result = subprocess.run([cxx, str(translation), str(backend), "-o", str(binary), *libs], capture_output=True, text=True)
            if result.returncode:
                raise BuildError("sound executable linking failed:\n" + (result.stderr or result.stdout))
        if not binary.is_file():
            raise BuildError("C compiler exited successfully without producing an executable")
        binary.replace(output)
