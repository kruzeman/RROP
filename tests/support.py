"""Shared generated-C compilation fixtures, without inherited test methods."""
from pathlib import Path
import subprocess
import tempfile
import unittest
from genesis_recompiler.decode import analyze
from genesis_recompiler.emit import emit


def rom_with(code):
    rom = bytearray(0x400)
    rom[:8] = bytes.fromhex("00ffff00 00000200")
    raw = bytes.fromhex(code)
    rom[0x200:0x200+len(raw)] = raw
    return bytes(rom)


class CompiledTestCase(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self): self.temp.cleanup()

    def compile(self, source):
        path = self.root / "translation.c"
        path.write_text(source)
        binary = self.root / "translation"
        result = subprocess.run(["cc", "-std=c11", "-O2", "-Wall", "-Wextra", "-Werror", "-Wno-unused-function", str(path), "-o", str(binary)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        return binary

    def execute(self, rom, args=(), entries=()):
        p = analyze(rom, [0x200, *entries])
        self.assertEqual(p.errors, {})
        exe = self.compile(emit(p))
        return subprocess.run([str(exe), *args], capture_output=True, text=True)
