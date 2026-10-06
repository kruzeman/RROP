"""Emit decoded operations as C; no runtime opcode decode or interpreter."""
from importlib.resources import files
from collections import defaultdict
import json
from .decode import EA, Instruction, Program
from .z80 import ZProgram, emit_z80
from .cycles import instruction_cycles


def literal(value): return f"0x{value & 0xFFFFFFFF:08x}u"


class Emitter:
    def __init__(self): self.lines = []; self.pc = None
    def put(self, code): self.lines.append("        " + code)

    def address(self, ea: EA, name: str, size: int):
        m, r, v = ea.mode, ea.reg, ea.value
        if m in (2, 3, 4):
            increment = 2 if r == 7 and size == 1 else size
            if m == 4: self.put(f"c->a[{r}] -= {increment};")
            expr = f"c->a[{r}]"
        elif m == 5: expr = f"c->a[{r}] + {literal(v)}"
        elif m == 6: expr = f"c->a[{r}] + {literal(v)} + index_value(c, {literal(ea.index)})"
        elif m == 7 and r <= 2: expr = literal(v)
        elif m == 7 and r == 3: expr = f"{literal(v)} + index_value(c, {literal(ea.index)})"
        else: raise ValueError("effective address has no address")
        self.put(f"uint32_t {name} = {expr};")

    def prepare(self, ea, name, size):
        if ea.mode not in (0, 1) and not (ea.mode == 7 and ea.reg == 4):
            self.address(ea, name + "_addr", size)

    def read(self, ea, name, size):
        if ea.mode in (0, 1): expr = f"c->{'d' if ea.mode == 0 else 'a'}[{ea.reg}] & {literal((1 << (size*8))-1)}"
        elif ea.mode == 7 and ea.reg == 4:
            expr = literal(ea.value)
            # Verified Rings menu bounds. The SDL-only host flag keeps headless
            # execution and every other ROM on the original five-item menu.
            replacement = {(0x1593c, 5): 6, (0x1596a, 5): 6, (0x1594c, 4): 5}.get((self.pc, ea.value))
            if replacement is not None:
                self.put("#if defined(GENESIS_RINGS_SAVES) && defined(GENESIS_SDL2)")
                self.put(f"uint32_t {name} = c->rings_settings_enabled ? {literal(replacement)} : {expr};")
                self.put("#else")
                self.put(f"uint32_t {name} = {expr};")
                self.put("#endif")
                self.put("if (c->fault) return;")
                return
        else:
            expr = f"read_mem(c, {name}_addr, {size})"
        self.put(f"uint32_t {name} = {expr};")
        self.put("if (c->fault) return;")

    def post(self, ea, size):
        if ea.mode == 3:
            increment = 2 if ea.reg == 7 and size == 1 else size
            self.put(f"c->a[{ea.reg}] += {increment};")

    def write(self, ea, name, size, expr="result"):
        if ea.mode == 0:
            mask = (1 << (size*8))-1
            self.put(f"c->d[{ea.reg}] = (c->d[{ea.reg}] & {literal(~mask)}) | ({expr} & {literal(mask)});")
        elif ea.mode == 1: self.put(f"c->a[{ea.reg}] = {expr};")
        else:
            self.put(f"write_mem(c, {name}_addr, {size}, {expr});")
            self.put("if (c->fault) return;")

    def instruction(self, i: Instruction, mutable_source_address=False):
        self.lines = []
        self.pc = i.pc
        self.put(f"/* {i.pc:06x}: {i} */")
        self.put(f"c->instruction_cycles = {instruction_cycles(i)};")
        op, size = i.op, i.size
        if op == "NOP": pass
        elif op == "TRAP":
            self.put("uint16_t saved_sr = c->sr;")
            self.put("set_sr(c, (saved_sr | 0x2000u) & ~0x8000u);")
            self.put(f"push32(c, {literal(i.end)}); if (c->fault) return;")
            self.put("c->a[7] -= 2; write_mem(c, c->a[7], 2, saved_sr); if (c->fault) return;")
            self.put(f"uint32_t target = read_mem(c, {literal((32+i.value)*4)}, 4); if (c->fault) return;")
            self.put("c->pc = target & 0xffffff; return;")
        elif op == "ILLEGAL":
            self.put('fail(c, "68000 ILLEGAL instruction (exception not implemented)", c->pc); return;')
        elif op in ("LINE_A", "LINE_F"):
            self.put(f'fail(c, "68000 {op} opcode ${i.value:04x} (exception not implemented)", c->pc); return;')
        elif op == "STOP":
            self.put('if (!(c->sr & 0x2000)) { fail(c, "STOP privilege violation", c->pc); return; }')
            self.put(f"set_sr(c, {literal(i.value)}); c->halted = 1;")
        elif op in ("TO_USP", "FROM_USP"):
            self.put('if (!(c->sr & 0x2000)) { fail(c, "USP privilege violation", c->pc); return; }')
            if op == "TO_USP": self.put(f"c->usp = c->a[{i.dst.reg}];")
            else: self.put(f"c->a[{i.dst.reg}] = c->usp;")
        elif op in ("TO_SR", "TO_CCR", "SR_OR", "SR_AND", "SR_EOR", "CCR_OR", "CCR_AND", "CCR_EOR"):
            if op == "TO_SR" or op.startswith("SR_"):
                self.put('if (!(c->sr & 0x2000)) { fail(c, "SR privilege violation", c->pc); return; }')
            self.prepare(i.src, "src", size)
            self.read(i.src, "src", size)
            self.post(i.src, size)
            if op == "TO_SR": self.put("set_sr(c, src);")
            elif op == "TO_CCR": self.put("c->sr = (uint16_t)((c->sr & ~31u) | (src & 31));")
            else:
                operator = {"OR": "|", "AND": "&", "EOR": "^"}[op.split("_")[1]]
                if op.startswith("SR_"): self.put(f"set_sr(c, c->sr {operator} src);")
                else: self.put(f"c->sr = (uint16_t)((c->sr & ~31u) | ((c->sr {operator} src) & 31));")
        elif op == "FROM_SR":
            self.prepare(i.dst, "dst", size)
            self.write(i.dst, "dst", size, "c->sr")
            self.post(i.dst, size)
        elif op in ("MOVEM_LOAD", "MOVEM_STORE"):
            ea = i.src if op == "MOVEM_LOAD" else i.dst
            if ea.mode == 4: self.put(f"uint32_t target = c->a[{ea.reg}];")
            else: self.address(ea, "target", size)
            self.put(f"movem(c, {literal(i.value)}, target, {ea.mode}, {ea.reg}, {size}, {int(op == 'MOVEM_LOAD')});")
            self.put("if (c->fault) return;")
        elif op == "LINK":
            self.put(f"push32(c, c->a[{i.dst.reg}]); if (c->fault) return;")
            self.put(f"c->a[{i.dst.reg}] = c->a[7]; c->a[7] += {literal(i.value)};")
        elif op == "UNLK":
            self.put(f"c->a[7] = c->a[{i.dst.reg}];")
            self.put("uint32_t saved = pop32(c); if (c->fault) return;")
            self.put(f"c->a[{i.dst.reg}] = saved;")
        elif op in ("RTE", "RTR"):
            if op == "RTE": self.put('if (!(c->sr & 0x2000)) { fail(c, "RTE privilege violation", c->pc); return; }')
            self.put("uint32_t saved_sr = read_mem(c, c->a[7], 2); if (c->fault) return;")
            self.put("uint32_t target = read_mem(c, c->a[7] + 2, 4); if (c->fault) return;")
            self.put("c->a[7] += 6;")
            if op == "RTE": self.put("set_sr(c, saved_sr);")
            else: self.put("c->sr = (uint16_t)((c->sr & ~31u) | (saved_sr & 31));")
            self.put("c->pc = target & 0xffffff; return;")
        elif op == "RTS":
            self.put("uint32_t target = pop32(c); if (c->fault) return;")
            self.put("c->pc = target & 0xffffff; return;")
        elif op in ("BCC", "BSR", "DBCC"):
            if op == "BSR":
                self.put(f"push32(c, {literal(i.end)}); if (c->fault) return;")
                self.put(f"c->pc = {literal(i.target)}; return;")
            elif op == "BCC":
                self.put(f"c->pc = condition(c, {i.condition}) ? {literal(i.target)} : {literal(i.end)}; return;")
            else:
                r = i.dst.reg
                self.put(f"if (!condition(c, {i.condition})) {{")
                self.put(f"    uint32_t low = (c->d[{r}] - 1u) & 0xffff;")
                self.put(f"    c->d[{r}] = (c->d[{r}] & 0xffff0000u) | low;")
                self.put(f"    if (low != 0xffff) {{ c->pc = {literal(i.target)}; return; }}")
                self.put("}")
        elif op in ("LEA", "PEA", "JMP", "JSR"):
            if mutable_source_address:
                self.put(f"uint32_t target = read_mem(c, {literal(i.pc+2)}, 4);")
                self.put("if (c->fault) return;")
            else:
                self.address(i.src, "target", 4)
            if op == "LEA": self.put(f"c->a[{i.dst.reg}] = target;")
            elif op == "PEA": self.put("push32(c, target); if (c->fault) return;")
            else:
                if op == "JSR": self.put(f"push32(c, {literal(i.end)}); if (c->fault) return;")
                self.put("c->pc = target & 0xffffff; return;")
        elif op == "MOVEQ":
            self.put(f"c->d[{i.dst.reg}] = {literal(i.value)};")
            self.put(f"logic_flags(c, c->d[{i.dst.reg}], 4);")
        elif op in ("ADDQ", "SUBQ") and i.dst.mode == 1:
            self.put(f"c->a[{i.dst.reg}] {'-=' if op == 'SUBQ' else '+='} {i.value};")
        elif op in ("ADDA", "SUBA", "CMPA"):
            self.prepare(i.src, "src", size)
            self.read(i.src, "src", size)
            self.post(i.src, size)
            source = "sign_extend(src, 2)" if size == 2 else "src"
            if op == "CMPA": self.put(f"(void)arithmetic(c, c->a[{i.dst.reg}], {source}, 4, 1, 1);")
            else: self.put(f"c->a[{i.dst.reg}] {'-=' if op == 'SUBA' else '+='} {source};")
        elif op == "EXG":
            self.read(i.src, "src", 4)
            self.read(i.dst, "dst", 4)
            self.write(i.src, "src", 4, "dst")
            self.write(i.dst, "dst", 4, "src")
        else:
            is_shift = op in ("ASL", "ASR", "LSL", "LSR", "ROXL", "ROXR", "ROL", "ROR")
            source_size = 4 if is_shift or op in ("BTST", "BCHG", "BCLR", "BSET") else size
            if i.src:
                if mutable_source_address:
                    self.put(f"uint32_t src_addr = read_mem(c, {literal(i.pc+2)}, 4);")
                    self.put("if (c->fault) return;")
                else:
                    self.prepare(i.src, "src", source_size)
                self.read(i.src, "src", source_size)
                self.post(i.src, source_size)
            dest_size = 4 if op in ("MULU", "MULS", "DIVU", "DIVS") else size
            self.prepare(i.dst, "dst", dest_size)
            if op not in ("MOVE", "MOVEA"):
                # CLR on the original 68000 performs a read before its write.
                self.read(i.dst, "dst", dest_size)
            if op in ("MOVE", "MOVEA"):
                self.put(f"uint32_t result = {'sign_extend(src, 2)' if op == 'MOVEA' and size == 2 else 'src'};")
            elif op == "CLR":
                self.put("(void)dst; uint32_t result = 0;")
            elif op == "TST": self.put("uint32_t result = dst;")
            elif op in ("ADDQ", "SUBQ", "ADDI", "SUBI", "CMPI", "ADD", "SUB", "CMP", "NEG"):
                operand = str(i.value) + "u" if op.endswith("Q") else "src"
                if op == "NEG": operand = "dst"
                sub = int(op in ("SUBQ", "SUBI", "CMPI", "SUB", "CMP", "NEG"))
                self.put(f"uint32_t result = arithmetic(c, {'0' if op == 'NEG' else 'dst'}, {operand}, {size}, {sub}, {int(op in ('CMPI', 'CMP'))});")
            elif op in ("ADDX", "SUBX", "NEGX"):
                self.put(f"uint32_t result = extended_arithmetic(c, {'0' if op == 'NEGX' else 'dst'}, {'dst' if op == 'NEGX' else 'src'}, {size}, {int(op != 'ADDX')});")
            elif op in ("ABCD", "SBCD"):
                self.put(f"uint32_t result = bcd_arithmetic(c, dst, src, {int(op != 'ABCD')});")
            elif op == "NBCD": self.put("uint32_t result = bcd_negate(c, dst);")
            elif op in ("ORI", "ANDI", "EORI", "OR", "AND", "EOR"):
                self.put(f"uint32_t result = dst {{}} src;".format({"ORI": "|", "ANDI": "&", "EORI": "^", "OR":"|", "AND":"&", "EOR":"^"}[op]))
            elif op == "NOT": self.put("uint32_t result = ~dst;")
            elif op == "SWAP": self.put("uint32_t result = (dst << 16) | (dst >> 16);")
            elif op == "EXT": self.put(f"uint32_t result = sign_extend(dst, {1 if size == 2 else 2});")
            elif op == "SCC": self.put(f"(void)dst; uint32_t result = condition(c, {i.condition}) ? 255:0;")
            elif op in ("BTST", "BCHG", "BCLR", "BSET"):
                self.put(f"uint32_t bit = 1u << (src % {size * 8});")
                self.put("c->sr = (uint16_t)((c->sr & ~F_Z) | (dst & bit ? 0:F_Z));")
                expr = {"BTST":"dst", "BCHG":"dst ^ bit", "BCLR":"dst & ~bit", "BSET":"dst | bit"}[op]
                self.put(f"uint32_t result = {expr};")
            elif is_shift:
                kind = {"AS":0, "LS":1, "ROX":2, "RO":3}[op[:-1]]
                self.put(f"uint32_t result = shift_value(c, dst, src, {size}, {kind}, {int(op.endswith('L'))});")
            elif op in ("MULU", "MULS"):
                self.put("uint32_t result = " + ("(uint32_t)(signed_bits(dst, 2) * signed_bits(src, 2));" if op == "MULS" else "(dst & 0xffff) * src;"))
            elif op in ("DIVU", "DIVS"):
                self.put(f"uint32_t result = divide_value(c, dst, src, {int(op == 'DIVS')}); if (c->fault) return;")
            else: raise ValueError(f"unimplemented emission: {op}")
            if op not in ("TST", "CMPI", "CMP", "BTST"): self.write(i.dst, "dst", dest_size)
            else: self.put("(void)result;")
            self.post(i.dst, dest_size)
            if op in ("MOVE", "CLR", "TST", "ORI", "ANDI", "EORI", "OR", "AND", "EOR", "NOT", "EXT", "SWAP", "MULU", "MULS"):
                self.put(f"logic_flags(c, result, {dest_size});")
        self.put(f"c->pc = {literal(i.end)};")
        self.put("return;")
        return "\n".join(self.lines)


def emit(program: Program, z80: ZProgram | None = None, cartridge: str = "plain", resources=None, resource_directory="resources") -> str:
    if cartridge not in ("plain", "ea-24c01"):
        raise ValueError("unsupported cartridge profile")
    runtime = files("genesis_recompiler").joinpath("runtime.h").read_text()
    for header in ("rings_camera_state.h", "vdp_state.h", "vdp.h", "z80_bus_state.h", "z80_bus.h", "z80_cpu_state.h", "z80_runtime.h", "psg_state.h", "psg.h", "eeprom_state.h", "eeprom.h", "vdp_timing.h", "vdp_render.h", "scheduler.h", "audio_state.h", "audio_backend.h", "audio_stub_state.h", "audio_stub.h", "audio.h", "controller.h", "sdl_frontend.h", "rings_startup_sdl.h", "rings_text_capture.h", "rings_text.h", "rings_font_sdl.h", "rings_wide_state.h", "rings_scene.h", "rings_wide_render.h", "rings_wide_compose.h", "rings_zoom.h", "rings_saves.h", "rings_object_diagnostics_state.h", "rings_object_diagnostics.h", "save_state.h", "rings_saves_sdl.h", "rings_camera.h", "rings_hud.h", "rings_mouse.h", "rings_mouse_sdl.h", "rings_settings_rom.h", "rings_window.h", "rings_settings_state.h", "rings_settings_sdl.h"):
        runtime = runtime.replace(f'#include "{header}"', files("genesis_recompiler").joinpath(header).read_text())
    data = resources.code if resources else program.rom
    rom_rows = ["    " + ",".join(f"0x{b:02x}" for b in data[start:start+16]) + "," for start in range(0, len(data), 16)]
    lines = ["/* Generated by genesis-recompiler. Original ROM required at translation time. */"]
    if resources:
        lines += ["#ifndef _POSIX_C_SOURCE", "#define _POSIX_C_SOURCE 200809L", "#endif", "#define GENESIS_EXTERNAL_RESOURCES"]
    lines += [runtime, f"static const uint8_t {'rom_code' if resources else 'rom_data'}[] = {{", *rom_rows, "};"]
    if resources:
        lines += [files("genesis_recompiler").joinpath("resources.h").read_text(), "static const ResourceSpan rom_code_spans[] = {"]
        lines += [f"    {{{a},{b},{n}}}," for a,b,n in resources.code_spans]
        lines += ["};"]
        for index, resource in enumerate(resources.resources):
            lines += [f"static const ResourceSpan resource_spans_{index}[] = {{"]
            lines += [f"    {{{a},{b},{n}}}," for a,b,n in resource.spans]
            lines += ["};"]
        lines += ["static const ROMResource rom_resources[] = {"]
        for index, resource in enumerate(resources.resources):
            lines += [f"    {{{json.dumps(resource.path)},{len(resource.data)},0x{resource.crc32:08x}u,resource_spans_{index},{len(resource.spans)}}},"]
        if not resources.resources: lines += ["    {NULL,0,0,NULL,0},"]
        lines += ["};"]
    emitter = Emitter()
    pages = defaultdict(list)
    for pc, inst in sorted(program.instructions.items()):
        pages[pc >> 12].append(inst)
    missing = '    default: fail(c, "PC has no translated instruction (unsupported or undiscovered code)", c->pc); return;'
    for page, instructions in pages.items():
        lines += [f"static void translated_page_{page:x}(CPU *c) {{", "    switch (c->pc) {"]
        for inst in instructions:
            lines.append(f"    case {literal(inst.pc)}: {{")
            variants = program.ram_variants.get(inst.pc, [])
            for variant in variants:
                operation, image = variant.instruction, variant.image
                offset = image.rom_offset + operation.pc - image.address
                spans = ((0, 2), (6, len(operation.raw)-6)) if variant.mutable_address else ((0, len(operation.raw)),)
                checks = [f'memcmp(c->ram + {literal((operation.pc & 0xffff)+start)}, c->rom + {literal(offset+start)}, {length}) == 0' for start, length in spans if length]
                lines += [f'        if ({" && ".join(checks)}) {{',
                          emitter.instruction(operation, variant.mutable_address), '        }']
            if variants:
                lines.append('        fail(c, "68000 RAM instruction bytes do not match static translation", c->pc); return;')
            else:
                lines.append(emitter.instruction(inst))
            lines.append('    }')
        lines += [missing, "    }", "}"]
    lines += ["static void translated_step(CPU *c) {", "    switch (c->pc >> 12) {"]
    for page in pages: lines.append(f"    case {literal(page)}: translated_page_{page:x}(c); return;")
    if resources:
        main = f"return resource_main(argc, argv, {json.dumps(resource_directory, ensure_ascii=False)}, {resources.rom_size}, rom_code, rom_code_spans, {len(resources.code_spans)}, rom_resources, {len(resources.resources)}, {int(cartridge=='ea-24c01')});"
    else:
        main = f"return run_main(argc, argv, rom_data, sizeof rom_data, {int(cartridge=='ea-24c01')});"
    lines += [missing, "    }", "}", "#ifndef GENESIS_NO_MAIN",
              f"int main(int argc, char **argv) {{ {main} }}", "#endif", emit_z80(z80), ""]
    return "\n".join(lines)
