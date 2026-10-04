"""Pinned MinGW SDL SDK and dependency packaging for Windows x86-64."""
from pathlib import Path, PurePosixPath
import hashlib
import os
import re
import shutil
import subprocess
import tarfile
import urllib.request
from .build import BuildError


SDK_PACKAGES = (
    ("SDL2", "2.32.10", "SDL", "83a5d74012311edc3c0d40ea6faecbe57ad692aa033fa5dc273cc937e3938ff2"),
    ("SDL2_ttf", "2.24.0", "SDL_ttf", "3a09e0a967ad53eca3ff2701de4d0df3369c0368739a1088a78d9d74908ef2c3"),
)
TARGET = "x86_64-w64-mingw32"
# DLLs supplied by supported Windows versions; never copy host system libraries.
SYSTEM_DLLS = set("advapi32 bcrypt cfgmgr32 combase comctl32 comdlg32 crypt32 d3d9 d3d11 dinput8 dwmapi dxgi gdi32 imm32 iphlpapi kernel32 msvcrt ntdll ole32 oleaut32 powrprof psapi rpcrt4 secur32 setupapi shell32 shlwapi ucrtbase user32 userenv usp10 version winmm winspool ws2_32".split())


def prepare_sdk(directory: Path) -> Path:
    """Download verified archives, extracting only regular files of our target."""
    directory = directory.resolve()
    prefix = directory / TARGET
    for name, version, repo, digest in SDK_PACKAGES:
        archive = directory / f"{name}-devel-{version}-mingw.tar.gz"
        directory.mkdir(parents=True, exist_ok=True)
        if not archive.exists():
            url = f"https://github.com/libsdl-org/{repo}/releases/download/release-{version}/{archive.name}"
            temporary = archive.with_suffix(".download")
            print(f"Downloading {name} {version}", flush=True)
            try:
                with urllib.request.urlopen(url, timeout=60) as response, temporary.open("wb") as out:
                    shutil.copyfileobj(response, out)
                if hashlib.sha256(temporary.read_bytes()).hexdigest() != digest:
                    raise BuildError(f"SDK checksum mismatch: {archive.name}")
                temporary.replace(archive)
            finally:
                temporary.unlink(missing_ok=True)
        if hashlib.sha256(archive.read_bytes()).hexdigest() != digest:
            raise BuildError(f"SDK checksum mismatch: {archive}; remove it and retry")
        with tarfile.open(archive) as tar:
            for member in tar:
                parts = PurePosixPath(member.name).parts
                if not parts or parts[0] != f"{name}-{version}":
                    continue
                if len(parts) == 2 and parts[1] == "LICENSE.txt":
                    relative = PurePosixPath("licenses", name + ".txt")
                elif len(parts) > 2 and parts[1] == TARGET:
                    relative = PurePosixPath(*parts[2:])
                else:
                    continue
                if member.isdir():
                    continue
                if not member.isfile() or ".." in relative.parts or relative.is_absolute():
                    raise BuildError(f"unsafe SDK archive member: {member.name}")
                destination = prefix / relative
                destination.parent.mkdir(parents=True, exist_ok=True)
                with tar.extractfile(member) as source, destination.open("wb") as out:
                    shutil.copyfileobj(source, out)
    # Official release .pc files contain the release builder's absolute path.
    # Rewrite only our local copy and keep pkg-config isolated from Linux SDL.
    for pc in (prefix / "lib" / "pkgconfig").glob("*.pc"):
        text = pc.read_text(encoding="utf-8")
        pc.write_text(re.sub(r"^prefix=.*$", lambda _: "prefix=" + prefix.as_posix(), text, flags=re.M), encoding="utf-8")
    return prefix


def sdk_environment(prefix: Path) -> dict[str, str]:
    env = dict(os.environ)
    env["PKG_CONFIG_LIBDIR"] = str(prefix / "lib" / "pkgconfig")
    env["PKG_CONFIG_PATH"] = ""
    env.pop("PKG_CONFIG_SYSROOT_DIR", None)
    return env


def imported_dlls(binary: Path, objdump: str) -> list[str]:
    result = subprocess.run([objdump, "-p", str(binary)], capture_output=True, text=True)
    if result.returncode:
        raise BuildError(f"cannot inspect Windows imports: {binary}\n{result.stderr}")
    if "pei-x86-64" not in result.stdout:
        raise BuildError(f"expected a Windows x86-64 PE binary: {binary}")
    return re.findall(r"DLL Name:\s*(\S+)", result.stdout)


def bundle_dlls(binary: Path, destination: Path, prefix: Path, compiler: str, objdump: str) -> list[str]:
    """Resolve every non-system import recursively; fail on missing DLLs."""
    destination.mkdir(parents=True, exist_ok=True)
    sdk_dlls = {p.name.lower(): p for p in (prefix / "bin").glob("*.dll")}
    # Debian keeps runtime DLLs in the target's lib directory; MSYS2 keeps
    # them beside gcc.exe. GCC's -print-file-name does not always search bin.
    compiler_path = Path(shutil.which(compiler) or compiler).resolve()
    compiler_dlls = {p.name.lower(): p for p in compiler_path.parent.glob("*.dll")}
    pending, seen, copied = [binary], set(), []
    while pending:
        for name in imported_dlls(pending.pop(), objdump):
            lower = name.lower()
            if lower in seen:
                continue
            seen.add(lower)
            if lower.removesuffix(".dll") in SYSTEM_DLLS or lower.startswith(("api-ms-win-", "ext-ms-win-")):
                continue
            source = sdk_dlls.get(lower) or compiler_dlls.get(lower)
            if source is None:
                result = subprocess.run([compiler, "-print-file-name=" + name], capture_output=True, text=True)
                candidate = Path(result.stdout.strip())
                if result.returncode == 0 and candidate.is_file():
                    source = candidate
            if source is None:
                raise BuildError(f"missing Windows runtime dependency: {name}")
            target = destination / name
            if source.resolve() != target.resolve():
                shutil.copy2(source, target)
            copied.append(name)
            pending.append(target)
    return sorted(copied)
