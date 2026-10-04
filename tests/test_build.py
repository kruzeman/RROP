import contextlib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from examples.make_demo import make_demo
from genesis_recompiler.cli import main


class BuildTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="genesis build tests ")
        self.root = Path(self.temp.name)
        self.rom = self.root / "demo.bin"
        self.rom.write_bytes(make_demo())
        self.output = self.root / "nested" / "demo"

    def tearDown(self): self.temp.cleanup()

    def invoke(self, *options):
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()) as stderr:
            status = main([str(self.rom), "--build", "-o", str(self.output), *options])
        return status, stderr.getvalue()

    def test_build_standalone_binary_and_retain_artifacts(self):
        source = self.root / "sources" / "demo.c"
        report = self.root / "reports" / "demo.json"
        status, error = self.invoke("--emit-c", str(source), "--report", str(report), "--cc", shutil.which("cc"))
        self.assertEqual(status, 0, error)
        self.assertTrue(source.exists())
        data = json.loads(report.read_text())
        self.assertEqual(data["instruction_count"], 10)
        self.assertEqual(len(data["rom_sha256"]), 64)
        # The generated executable needs neither the original ROM nor its C.
        self.rom.unlink()
        source.unlink()
        result = subprocess.run([str(self.output), "--peek", "0xff0000"], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("mem[ff0000]=00000008", result.stdout)
        self.assertEqual(list(self.output.parent.glob(".genesis-build-*")), [])

    def test_missing_compiler_preserves_previous_executable(self):
        self.output.parent.mkdir()
        self.output.write_bytes(b"previous executable")
        status, error = self.invoke("--cc", str(self.root / "missing compiler"))
        self.assertEqual(status, 1)
        self.assertIn("compiler not found", error)
        self.assertEqual(self.output.read_bytes(), b"previous executable")
        self.assertEqual(list(self.output.parent.glob(".genesis-build-*")), [])

    def test_headless_build_reports_window_unavailable(self):
        status, error = self.invoke()
        self.assertEqual(status, 0, error)
        result = subprocess.run([str(self.output), '--window'], capture_output=True, text=True)
        self.assertEqual(result.returncode, 64)
        self.assertIn('rebuild with --frontend sdl2', result.stderr)

    def test_frontend_option_requires_build(self):
        with self.assertRaises(SystemExit) as result, contextlib.redirect_stderr(io.StringIO()):
            main([str(self.rom), '-o', str(self.output), '--frontend', 'sdl2'])
        self.assertEqual(result.exception.code, 2)

    def test_failed_compilation_preserves_previous_executable(self):
        self.output.parent.mkdir()
        self.output.write_bytes(b"previous executable")
        compiler = self.root / "failing compiler"
        compiler.write_text("#!/bin/sh\nprintf 'intentional diagnostic\\n' >&2\nexit 7\n")
        compiler.chmod(0o700)
        status, error = self.invoke("--cc", str(compiler))
        self.assertEqual(status, 1)
        self.assertIn("exit 7", error)
        self.assertIn("intentional diagnostic", error)
        self.assertEqual(self.output.read_bytes(), b"previous executable")

    def test_success_without_binary_is_a_failure(self):
        status, error = self.invoke("--cc", shutil.which("true"))
        self.assertEqual(status, 1)
        self.assertIn("without producing an executable", error)
        self.assertFalse(self.output.exists())

    def test_artifact_paths_cannot_alias_rom(self):
        original = self.rom.read_bytes()
        status, error = self.invoke("--emit-c", str(self.rom))
        self.assertEqual(status, 1)
        self.assertIn("different paths", error)
        alias = self.root / "hardlink.bin"
        os.link(self.rom, alias)
        status, error = self.invoke("--report", str(alias))
        self.assertEqual(status, 1)
        self.assertEqual(self.rom.read_bytes(), original)

    def test_unsupported_code_does_not_build(self):
        rom = bytearray(make_demo())
        rom[0x200:0x202] = bytes.fromhex("4e70")
        self.rom.write_bytes(rom)
        status, error = self.invoke()
        self.assertEqual(status, 1)
        self.assertIn("unsupported opcode", error)
        self.assertFalse(self.output.exists())

    def test_z80_inputs_are_guarded_reported_and_preserved(self):
        image = self.root / "z80.bin"
        image.write_bytes(bytes.fromhex("af e9"))
        report = self.root / "report.json"
        status, error = self.invoke("--z80-image", str(image), "--z80-overlay", "0:e9", "--cartridge", "ea-24c01", "--report", str(report))
        self.assertEqual(status, 0, error)
        data = json.loads(report.read_text())
        self.assertEqual(data["z80"]["instruction_variants"], 3)
        self.assertEqual(data["z80"]["errors"], [])
        self.assertEqual(data["cartridge"], "ea-24c01")
        status, error = self.invoke("--z80-image", str(image), "--emit-c", str(image))
        self.assertEqual(status, 1)
        self.assertIn("different paths", error)
        self.assertEqual(image.read_bytes(), bytes.fromhex("af e9"))

    def test_unsupported_z80_prevents_build(self):
        image = self.root / "z80.bin"
        image.write_bytes(bytes.fromhex("ed 00"))
        status, error = self.invoke("--z80-image", str(image))
        self.assertEqual(status, 1)
        self.assertIn("unsupported Z80", error)
        self.assertFalse(self.output.exists())

    def test_z80_argument_validation(self):
        for options in (("--z80-mutable-displacement", "0"), ("--z80-overlay", "0:e9"), ("--z80-mutable-immediate", "0"), ("--z80-image-entry", "0:0"), ("--z80-image", str(self.rom), "--z80-overlay", "0x2000:aa"), ("--z80-image", str(self.rom), "--z80-entry", "0x4000")):
            with self.subTest(options=options), self.assertRaises(SystemExit) as error:
                self.invoke(*options)
            self.assertEqual(error.exception.code, 2)

    def test_image_specific_z80_entry_is_validated_and_reported(self):
        image=self.root/'z80.bin';image.write_bytes(bytes.fromhex('76 00 00 3e 12 76'))
        report=self.root/'report.json'
        status,error=self.invoke('--z80-image',str(image),'--z80-image-entry','0:3','--report',str(report))
        self.assertEqual(status,0,error)
        self.assertEqual(json.loads(report.read_text())['z80']['image_entries'],[{'image':0,'pc':3}])
        status,error=self.invoke('--z80-image',str(image),'--z80-image-entry','1:3')
        self.assertEqual(status,1)
        self.assertIn('existing zero-based image',error)

    def test_mutable_z80_operand_is_reported_and_requires_an_instruction(self):
        image = self.root / "z80.bin"
        image.write_bytes(bytes.fromhex("3e 00 76"))
        report = self.root / "report.json"
        status, error = self.invoke("--z80-image", str(image), "--z80-mutable-immediate", "0", "--report", str(report))
        self.assertEqual(status, 0, error)
        z80 = json.loads(report.read_text())["z80"]
        self.assertEqual(z80["mutable_immediates"], [0])
        self.assertEqual(z80["instruction_variants"], 257)
        status, error = self.invoke("--z80-image", str(image), "--z80-mutable-immediate", "1")
        self.assertEqual(status, 1)
        self.assertIn("two-byte LD r,n", error)
        self.assertEqual(image.read_bytes(), bytes.fromhex("3e 00 76"))

    def test_region_cli_runs_pal_and_rejects_invalid_values(self):
        status, error = self.invoke()
        self.assertEqual(status, 0, error)
        result = subprocess.run([str(self.output), "--region", "pal", "--peek", "0xff0000"], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("console region=pal master_hz=53203424 lines_per_frame=313", result.stdout)
        self.assertIn("mem[ff0000]=00000008", result.stdout)
        for options in (("--region",), ("--region", "japan")):
            result = subprocess.run([str(self.output), *options], capture_output=True, text=True)
            self.assertEqual(result.returncode, 64)

    def test_interrupt_vectors_are_static_analysis_roots(self):
        rom=bytearray(self.rom.read_bytes())
        rom[0x78:0x7c]=(0x300).to_bytes(4,"big")
        rom[0x300:0x302]=bytes.fromhex("4e73")
        self.rom.write_bytes(rom)
        report=self.root/"report.json"
        status,error=self.invoke("--report",str(report))
        self.assertEqual(status,0,error)
        data=json.loads(report.read_text())
        self.assertEqual(data["interrupt_targets"],{"6":0x300})
        self.assertTrue(any(i["pc"]==0x300 for i in data["instructions"]))


if __name__ == "__main__": unittest.main()
