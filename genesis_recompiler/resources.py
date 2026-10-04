"""Lossless ROM address map: compiled-code bytes plus external resource blobs."""
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re
import tempfile
import zlib
from .decode import Program


@dataclass(frozen=True)
class GraphicsRange:
    name: str
    offset: int
    size: int
    encoding: str = "rom-bytes"


@dataclass(frozen=True)
class Resource:
    kind: str
    path: str
    data: bytes
    # Each span is (ROM address, offset in this file, length).
    spans: tuple[tuple[int, int, int], ...]
    encoding: str = "rom-bytes"

    @property
    def crc32(self): return zlib.crc32(self.data)

    def describe(self):
        description = {"kind": self.kind, "file": self.path, "size": len(self.data),
                "sha256": hashlib.sha256(self.data).hexdigest(), "crc32": f"{self.crc32:08x}",
                "encoding": self.encoding,
                "spans": [{"rom_offset": a, "file_offset": b, "size": n} for a, b, n in self.spans]}
        if self.encoding == 'genesis-4bpp':
            description['tiles'] = len(self.data)//32
            description['preview'] = {'file': str(Path(self.path).with_suffix('.ppm')),
                                      'palette': 'grayscale indices; actual colors are supplied by game CRAM'}
        return description


@dataclass(frozen=True)
class ResourcePlan:
    rom_size: int
    rom_sha256: str
    code: bytes
    code_spans: tuple[tuple[int, int, int], ...]
    resources: tuple[Resource, ...]

    def manifest(self):
        return {"format": "genesis-resources-v1", "rom_sha256": self.rom_sha256,
                "rom_size": self.rom_size, "embedded_bytes": len(self.code),
                "external_bytes": sum(len(r.data) for r in self.resources),
                "embedded_spans": [{"rom_offset": a, "code_offset": b, "size": n}
                                   for a, b, n in self.code_spans],
                "resources": [r.describe() for r in self.resources]}


def _runs(mask, value):
    start = None
    for index, flag in enumerate(mask):
        if flag == value and start is None: start = index
        elif flag != value and start is not None:
            yield start, index-start
            start = None
    if start is not None: yield start, len(mask)-start


def _pack(rom, ranges):
    data, spans, offset = [], [], 0
    for address, count in ranges:
        data.append(rom[address:address+count]);spans.append((address, offset, count));offset += count
    return b''.join(data), tuple(spans)


def plan_resources(program: Program, graphics=()) -> ResourcePlan:
    rom = program.rom
    mask = bytearray(len(rom))
    # Vector/header reads and verified RAM uploads retain their original bytes.
    mask[:min(0x200, len(rom))] = b'\1'*min(0x200, len(rom))
    for inst in program.instructions.values():
        if inst.pc < len(rom): mask[inst.pc:inst.end] = b'\1'*len(inst.raw)
    for copy in program.ram_copies:
        mask[copy.rom_offset:copy.rom_offset+copy.size] = b'\1'*copy.size
    code, code_spans = _pack(rom, _runs(mask, 1))
    resources, names = [], set()
    for g in graphics:
        if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,63}', g.name) or g.name in names:
            raise ValueError('graphics names must be unique: 1..64 ASCII letters, digits, underscore or hyphen')
        names.add(g.name)
        if g.offset < 0 or g.size <= 0 or g.offset+g.size > len(rom):
            raise ValueError('graphics range must fit the ROM and have positive size')
        if g.encoding not in ('rom-bytes', 'genesis-4bpp'):
            raise ValueError('unsupported graphics encoding')
        if g.encoding == 'genesis-4bpp' and g.size % 32:
            raise ValueError('Genesis 4bpp tile banks must contain complete 32-byte tiles')
        if any(mask[g.offset:g.offset+g.size]):
            raise ValueError('graphics ranges must not overlap each other, vectors/header or translated code/RAM-copy sources')
        data = rom[g.offset:g.offset+g.size]
        digest = hashlib.sha256(data).hexdigest()
        resources.append(Resource('graphics', f'graphics/{g.name}-{digest}.bin', data, ((g.offset, 0, g.size),), g.encoding))
        mask[g.offset:g.offset+g.size] = b'\2'*g.size
    data, spans = _pack(rom, _runs(mask, 0))
    if data:
        digest = hashlib.sha256(data).hexdigest()
        resources.append(Resource('rom-data', f'data/rom-{digest}.bin', data, spans))
    return ResourcePlan(len(rom), hashlib.sha256(rom).hexdigest(), code, code_spans, tuple(resources))


def _check_path(path, protected):
    for other in protected:
        if path.resolve() == other.resolve() or (path.exists() and other.exists() and path.samefile(other)):
            raise ValueError('resource files and manifest must use different paths from inputs and output artifacts')


def _write_atomic(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=path.parent, prefix='.genesis-resource-', delete=False) as stream:
        temp = Path(stream.name)
        try:
            stream.write(data);stream.close();temp.replace(path)
        finally:
            temp.unlink(missing_ok=True)


def tile_preview(data, columns=16):
    """PPM palette-index atlas, without guessing the game's dynamic CRAM colors."""
    count = len(data)//32
    width, height = min(columns, count)*8, ((count+columns-1)//columns)*8
    pixels = bytearray(width*height*3)
    for tile in range(count):
        for y in range(8):
            for x in range(8):
                packed = data[tile*32+y*4+x//2]
                index = (packed >> (0 if x&1 else 4)) & 15
                at = ((tile//columns*8+y)*width+tile%columns*8+x)*3
                pixels[at:at+3] = bytes([index*17])*3
    return f'P6\n{width} {height}\n255\n'.encode()+pixels


def write_resources(plan: ResourcePlan, directory: Path, protected=(), manifest=True):
    targets = [directory/r.path for r in plan.resources]
    previews = [(directory/Path(r.path).with_suffix('.ppm'), tile_preview(r.data))
                for r in plan.resources if r.encoding == 'genesis-4bpp']
    for path in [*targets, *(p for p,_ in previews), directory/'manifest.json']:
        _check_path(path, protected)
    # Immutable hash-named files preserve older executables during failed builds.
    for resource, path in zip(plan.resources, targets):
        if path.exists():
            if path.read_bytes() != resource.data:
                raise ValueError(f'existing resource has changed: {path}; use a clean resource directory')
        else: _write_atomic(path, resource.data)
    for path, data in previews:
        if path.exists():
            if path.read_bytes() != data: raise ValueError(f'existing tile preview has changed: {path}')
        else: _write_atomic(path, data)
    if manifest:
        _write_atomic(directory/'manifest.json', (json.dumps(plan.manifest(), indent=2)+'\n').encode())
