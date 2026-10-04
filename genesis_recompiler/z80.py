"""Static Z80 RAM-image translation. Compiled variants are guarded, never decoded at runtime."""
from dataclasses import dataclass, field, replace


class Z80DecodeError(ValueError):
    pass


@dataclass(frozen=True)
class ZInstruction:
    pc: int
    end: int
    op: str
    args: tuple = ()
    cycles: int = 4
    raw: bytes = b""

    def successors(self):
        if self.op in ("JP_REG", "RET", "RETN", "HALT"): return []
        if self.op == "JP": return [self.args[0]]
        if self.op in ("JR", "DJNZ", "JP_CC", "CALL", "CALL_CC"):
            target = self.args[-1]
            if self.op == "JR" and self.args[0] == -1: return [target]
            return [self.end, target]
        return [self.end]


class ZDecoder:
    def __init__(self, image: bytes, pc: int):
        self.image, self.start, self.pc = image, pc, pc
        self.raw = bytearray()

    def byte(self):
        if not 0 <= self.pc < 0x4000: raise Z80DecodeError("Z80 code outside RAM/mirror")
        value = self.image[self.pc & 0x1FFF]
        self.pc += 1
        self.raw.append(value)
        return value

    def word(self): return self.byte() | (self.byte() << 8)

    def decode(self):
        w = self.byte()
        op, args, cycles = "", (), 4
        if w == 0x00: op = "NOP"
        elif w == 0x76: op = "HALT"
        elif w in (0xF3, 0xFB): op = "DI" if w == 0xF3 else "EI"
        elif w in (0x08, 0xD9): op = "EX_AF" if w == 0x08 else "EXX"
        elif w == 0xEB: op = "EX_DE_HL"
        elif w == 0x2f: op = "CPL"
        elif w in (0x37, 0x3f): op = "CCF" if w == 0x3f else "SCF"
        elif w in (0x07, 0x0f, 0x17, 0x1f): op, args = "ROTATE_A", ((w >> 3)&3,)
        elif w == 0xE9: op = "JP_REG"; args = (2,)
        elif w == 0xF9: op, args, cycles = "LD_SP", (2,), 6
        elif w & 0xCF == 0x01: op, args, cycles = "LD16", ((w >> 4) & 3, self.word()), 10
        elif w & 0xCF in (0x03, 0x0B):
            op, args, cycles = "INC16", ((w >> 4) & 3, -1 if w & 8 else 1), 6
        elif w & 0xCF == 0x09: op, args, cycles = "ADD_HL", ((w >> 4) & 3,), 11
        elif w & 0xCF in (0xC1, 0xC5):
            op, args, cycles = ("POP" if w & 0xCF == 0xC1 else "PUSH"), ((w >> 4) & 3,), (10 if w & 0xCF == 0xC1 else 11)
        elif w & 0xC7 == 0x06:
            reg = (w >> 3) & 7
            op, args, cycles = "LD8_IMM", (reg, self.byte()), 10 if reg == 6 else 7
        elif w & 0xC7 in (0x04, 0x05):
            reg = (w >> 3) & 7
            op, args, cycles = "INC8", (reg, -1 if w & 1 else 1), 11 if reg == 6 else 4
        elif 0x40 <= w <= 0x7F:
            dst, src = (w >> 3) & 7, w & 7
            op, args, cycles = "LD8", (dst, src), 7 if 6 in (dst, src) else 4
        elif 0x80 <= w <= 0xBF:
            kind, reg = (w >> 3) & 7, w & 7
            op, args, cycles = "ALU", (kind, reg), 7 if reg == 6 else 4
        elif w & 0xC7 == 0xC6: op, args, cycles = "ALU_IMM", ((w >> 3) & 7, self.byte()), 7
        elif w in (0x02, 0x12, 0x0A, 0x1A):
            op, args, cycles = "LD_A_PAIR", ((w >> 4) & 1, bool(w & 8)), 7
        elif w in (0x32, 0x3A): op, args, cycles = "LD_A_MEM", (self.word(), w == 0x3A), 13
        elif w in (0x22, 0x2A): op, args, cycles = "LD_PAIR_MEM", (2, self.word(), w == 0x2A), 16
        elif w == 0xC3: op, args, cycles = "JP", (self.word(),), 10
        elif w & 0xC7 == 0xC2: op, args, cycles = "JP_CC", ((w >> 3) & 7, self.word()), 10
        elif w in (0x18, 0x20, 0x28, 0x30, 0x38, 0x10):
            disp = self.byte()
            if disp & 0x80: disp -= 256
            target = (self.pc + disp) & 0xFFFF
            op = "DJNZ" if w == 0x10 else "JR"
            args = (target,) if w == 0x10 else ((-1 if w == 0x18 else (w >> 3) & 3), target)
            cycles = 13 if w == 0x10 else 12
        elif w == 0xCD: op, args, cycles = "CALL", (self.word(),), 17
        elif w & 0xC7 == 0xC4: op, args, cycles = "CALL_CC", ((w >> 3) & 7, self.word()), 17
        elif w & 0xC7 == 0xC7: op, args, cycles = "CALL", (w & 0x38,), 11
        elif w == 0xC9: op, cycles = "RET", 10
        elif w & 0xC7 == 0xC0: op, args, cycles = "RET_CC", ((w >> 3) & 7,), 11
        elif w == 0xCB:
            ext = self.byte()
            if ext < 0x40:
                reg = ext & 7
                op, args, cycles = "ROTATE", ((ext >> 3) & 7, reg), 15 if reg == 6 else 8
            elif ext < 0x80:
                op, args, cycles = "BIT", ((ext >> 3) & 7, ext & 7), 12 if ext & 7 == 6 else 8
            elif ext >= 0x80:
                op, args, cycles = "BIT_WRITE", ((ext >> 3) & 7, ext & 7, ext >= 0xc0), 15 if ext & 7 == 6 else 8
            else: raise Z80DecodeError(f"unsupported Z80 CB opcode ${ext:02x}")
        elif w in (0xDD, 0xFD):
            pair, ext = (4 if w == 0xDD else 5), self.byte()
            if ext in (0xE1, 0xE5): op, args, cycles = ("POP_INDEX" if ext == 0xE1 else "PUSH_INDEX"), (pair,), (14 if ext == 0xE1 else 15)
            elif ext == 0x21: op, args, cycles = "LD16", (pair, self.word()), 14
            elif ext == 0xE9: op, args, cycles = "JP_REG", (pair,), 8
            elif ext == 0xF9: op, args, cycles = "LD_SP", (pair,), 10
            elif ext in (0x22, 0x2A): op, args, cycles = "LD_PAIR_MEM", (pair, self.word(), ext == 0x2A), 20
            elif ext in (0x23, 0x2b): op, args, cycles = "INC16", (pair, -1 if ext == 0x2b else 1), 10
            elif ext & 0xcf == 0x09:
                source=(ext >> 4)&3
                op, args, cycles = "ADD_INDEX", (pair, pair if source == 2 else source), 15
            elif 0x40 <= ext < 0x80 and ext != 0x76 and (ext & 7 == 6 or (ext >> 3)&7 == 6):
                disp=self.byte(); disp=disp-256 if disp&128 else disp
                op, args, cycles = "LD_INDEX_MEM", (pair, disp, (ext >> 3)&7, ext&7), 19
            elif ext == 0x36:
                disp=self.byte(); disp=disp-256 if disp&128 else disp
                op, args, cycles = "LD_INDEX_IMM", (pair, disp, self.byte()), 19
            elif ext in (0x34, 0x35):
                disp=self.byte(); disp=disp-256 if disp&128 else disp
                op, args, cycles = "INC_INDEX_MEM", (pair, disp, -1 if ext&1 else 1), 23
            elif 0x80 <= ext <= 0xbf and ext & 7 == 6:
                disp=self.byte(); disp=disp-256 if disp&128 else disp
                op, args, cycles = "ALU_INDEX_MEM", (pair, disp, (ext >> 3)&7), 19
            elif ext == 0xcb:
                disp=self.byte(); disp=disp-256 if disp&128 else disp
                bitop=self.byte()
                if bitop < 0x40: raise Z80DecodeError(f"unsupported Z80 indexed CB opcode ${bitop:02x}")
                if bitop < 0x80:
                    op, args, cycles = "BIT_INDEX", (pair, disp, (bitop >> 3)&7), 20
                else:
                    op, args, cycles = "BIT_INDEX_WRITE", (pair, disp, (bitop >> 3)&7, bitop&7, bitop >= 0xc0), 23
            else: raise Z80DecodeError(f"unsupported Z80 indexed opcode ${w:02x}${ext:02x}")
        elif w == 0xED:
            ext = self.byte()
            if ext in (0xA0, 0xB0, 0xA8, 0xB8):
                op, args, cycles = "LD_BLOCK", (-1 if ext & 8 else 1, bool(ext & 0x10)), 16
            elif ext in (0x47, 0x4F, 0x57, 0x5F): op, args, cycles = "LD_IR", (bool(ext & 8), bool(ext & 0x10)), 9
            elif ext in (0x46, 0x56, 0x5E): op, args, cycles = "IM", ({0x46:0, 0x56:1, 0x5E:2}[ext],), 8
            elif ext & 0xc7 == 0x44: op, cycles = "NEG", 8
            elif ext & 0xc7 == 0x45: op, cycles = "RETN", 14
            elif ext & 0xc7 in (0x42, 0x4a): op, args, cycles = "ALU16", ((ext >> 4)&3, not bool(ext&8)), 15
            elif ext & 0xc7 in (0x43, 0x4b): op, args, cycles = "LD_PAIR_MEM", ((ext >> 4)&3, self.word(), bool(ext&8)), 20
            else: raise Z80DecodeError(f"unsupported Z80 ED opcode ${ext:02x}")
        else: raise Z80DecodeError(f"unsupported Z80 opcode ${w:02x}")
        return ZInstruction(self.start, self.pc & 0xFFFF, op, args, cycles, bytes(self.raw))


@dataclass
class ZProgram:
    instructions: dict[int, list[ZInstruction]] = field(default_factory=dict)
    errors: list[dict] = field(default_factory=list)
    mutable_immediates: tuple[int, ...] = ()
    image_entries: tuple[tuple[int, int], ...] = ()
    mutable_displacements: tuple[int, ...] = ()


def analyze_z80(images: list[bytes], entries=(), overlays=(), mutable_immediates=(), image_entries=(), mutable_displacements=()) -> ZProgram:
    program = ZProgram()
    program.image_entries = tuple(sorted(set(image_entries)))
    if any(not 0 <= index < len(images) or not 0 <= pc < 0x4000 for index, pc in program.image_entries):
        raise ValueError("Z80 image entry must select an existing zero-based image index and a RAM/mirror address")
    variants = []
    for index, image in enumerate(images):
        if not 1 <= len(image) <= 8192: raise ValueError("Z80 RAM image must contain 1 to 8192 bytes")
        full = image.ljust(8192, b"\0")
        variants.append((full, [0, *entries, *(pc for which, pc in program.image_entries if which == index)]))
        for pc, raw in overlays:
            if not raw or pc < 0 or pc + len(raw) > 8192: raise ValueError("Z80 overlay must fit physical RAM")
            patched = bytearray(full)
            patched[pc:pc+len(raw)] = raw
            variants.append((bytes(patched), [pc]))
    for index, (image, roots) in enumerate(variants):
        pending, seen = list(reversed(roots)), set()
        while pending:
            pc = pending.pop()
            if pc in seen: continue
            seen.add(pc)
            try:
                inst = ZDecoder(image, pc).decode()
            except Z80DecodeError as exc:
                program.errors.append({"variant":index, "pc":pc, "message":str(exc)})
                continue
            existing = program.instructions.setdefault(pc, [])
            if inst not in existing: existing.append(inst)
            # Z80 branches can legally enter another instruction's operand.
            # Each entry still has its own static operation and full byte guard.
            pending.extend(reversed(inst.successors()))
    program.mutable_immediates = tuple(sorted(set(mutable_immediates)))
    for pc in program.mutable_immediates:
        templates = program.instructions.get(pc, [])
        if not templates or any(i.op != "LD8_IMM" or len(i.raw) != 2 for i in templates):
            raise ValueError("mutable Z80 immediate must name an analyzed two-byte LD r,n instruction")
        expanded = list(templates)
        for i in templates:
            for value in range(256):
                variant = replace(i, args=(i.args[0], value), raw=bytes((i.raw[0], value)))
                if variant not in expanded:
                    expanded.append(variant)
        program.instructions[pc] = expanded
    program.mutable_displacements = tuple(sorted(set(mutable_displacements)))
    for pc in program.mutable_displacements:
        templates = program.instructions.get(pc, [])
        allowed = {"LD_INDEX_MEM", "LD_INDEX_IMM", "INC_INDEX_MEM", "ALU_INDEX_MEM", "BIT_INDEX", "BIT_INDEX_WRITE"}
        if not templates or any(i.op not in allowed or i.raw[0] not in (0xdd, 0xfd) for i in templates):
            raise ValueError("mutable Z80 displacement must name an analyzed IX/IY memory instruction")
        expanded = list(templates)
        for inst in templates:
            for value in range(256):
                raw = inst.raw[:2] + bytes((value,)) + inst.raw[3:]
                args = (inst.args[0], value-256 if value&128 else value, *inst.args[2:])
                variant = replace(inst, args=args, raw=raw)
                if variant not in expanded:
                    expanded.append(variant)
        program.instructions[pc] = expanded
    return program


def z80_instruction_code(i):
    op, a, pc = i.op, i.args, i.pc
    lines = [f"/* Z80 {pc:04x}: {op} {a} */", f"z80_m1(c, {2 if i.raw[0] in (0xDD,0xFD,0xED,0xCB) else 1});"]
    tail = [f"z->pc = 0x{i.end:04x};", f"return {i.cycles};"]
    if op == "NOP": pass
    elif op == "HALT": lines.append("z->halted = 1;")
    elif op in ("DI", "EI"):
        lines.append(f"z->iff1 = z->iff2 = {int(op=='EI')}; z->ei_delay={2 if op=='EI' else 0};")
    elif op == "IM": lines.append(f"z->im = {a[0]};")
    elif op == "LD16": lines.append(f"z80_set_pair(c, {a[0]}, 0x{a[1]:04x});")
    elif op == "INC16": lines.append(f"z80_set_pair(c, {a[0]}, (uint16_t)(z80_pair(c,{a[0]}) + ({a[1]})));")
    elif op == "ADD_HL": lines.append(f"z80_add_hl(c, z80_pair(c,{a[0]}));")
    elif op == "ADD_INDEX": lines.append(f"z80_add_pair(c,{a[0]},z80_pair(c,{a[1]}));")
    elif op == "ALU16": lines.append(f"z80_alu16(c,z80_pair(c,{a[0]}),{int(a[1])});")
    elif op in ("LD8", "LD8_IMM"):
        source = f"z80_reg(c,{a[1]})" if op == "LD8" else str(a[1])
        lines += [f"uint8_t value = {source};", "if (c->fault) return 0;", f"z80_set_reg(c,{a[0]},value);"]
    elif op == "INC8":
        lines += [f"uint8_t value = z80_reg(c,{a[0]});", "if (c->fault) return 0;", f"z80_set_reg(c,{a[0]},z80_inc(c,value,{a[1]}));"]
    elif op == "ROTATE":
        lines += [f"uint8_t value = z80_reg(c,{a[1]});", "if (c->fault) return 0;", f"z80_set_reg(c,{a[1]},z80_rotate(c,value,{a[0]}));"]
    elif op == "ROTATE_A":
        lines += ["uint8_t preserved=z->f&(Z_S|Z_Z|Z_PV);", f"z->a=z80_rotate(c,z->a,{a[0]});", "z->f=(uint8_t)(preserved|(z->f&Z_C)|(z->a&0x28));"]
    elif op == "NEG":
        lines += ["uint8_t value=z->a; z->a=0; z80_alu(c,2,value);"]
    elif op == "BIT":
        xy = "z->wz>>8" if a[1] == 6 else "value"
        lines += [f"uint8_t value=z80_reg(c,{a[1]});", "if (c->fault) return 0;", f"z80_bit(c,value,{a[0]},(uint8_t)({xy}));"]
    elif op == "BIT_WRITE":
        expr=f"value | (1u<<{a[0]})" if a[2] else f"value & ~(1u<<{a[0]})"
        lines += [f"uint8_t value=z80_reg(c,{a[1]});", "if (c->fault) return 0;", f"z80_set_reg(c,{a[1]},(uint8_t)({expr}));"]
    elif op in ("LD_INDEX_MEM", "LD_INDEX_IMM", "INC_INDEX_MEM", "ALU_INDEX_MEM"):
        lines.append(f"uint16_t address=(uint16_t)(z80_pair(c,{a[0]})+({a[1]}));")
        lines.append("z->wz=address;")
        if op == "LD_INDEX_MEM":
            source="z80_read(c,address)" if a[3] == 6 else f"z80_reg(c,{a[3]})"
            lines += [f"uint8_t value={source};", "if (c->fault) return 0;"]
            lines.append("z80_write(c,address,value);" if a[2] == 6 else f"z80_set_reg(c,{a[2]},value);")
        elif op == "LD_INDEX_IMM": lines.append(f"z80_write(c,address,{a[2]});")
        else:
            lines += ["uint8_t value=z80_read(c,address);", "if (c->fault) return 0;"]
            lines.append(f"z80_write(c,address,z80_inc(c,value,{a[2]}));" if op == "INC_INDEX_MEM" else f"z80_alu(c,{a[2]},value);")
    elif op in ("ALU", "ALU_IMM"):
        source = f"z80_reg(c,{a[1]})" if op == "ALU" else str(a[1])
        lines += [f"uint8_t value = {source};", "if (c->fault) return 0;", f"z80_alu(c,{a[0]},value);"]
    elif op == "LD_A_PAIR":
        lines.append(f"uint16_t address=z80_pair(c,{a[0]});")
        if a[1]: lines.append(f"z->a = z80_read(c,z80_pair(c,{a[0]}));")
        else: lines.append(f"z80_write(c,z80_pair(c,{a[0]}),z->a);")
        lines.append("z->wz=(uint16_t)(address+1);" if a[1] else "z->wz=(uint16_t)((z->a<<8)|((address+1)&255));")
    elif op == "LD_A_MEM":
        lines.append(f"z->a = z80_read(c,0x{a[0]:04x});" if a[1] else f"z80_write(c,0x{a[0]:04x},z->a);")
        lines.append(f"z->wz=0x{(a[0]+1)&65535:04x};" if a[1] else f"z->wz=(uint16_t)((z->a<<8)|0x{(a[0]+1)&255:02x});")
    elif op == "LD_PAIR_MEM":
        lines.append(f"z80_set_pair(c,{a[0]},z80_read16(c,0x{a[1]:04x}));" if a[2] else f"z80_write16(c,0x{a[1]:04x},z80_pair(c,{a[0]}));")
        lines.append(f"z->wz=0x{(a[1]+1)&65535:04x};")
    elif op == "LD_SP": lines.append(f"z->sp = z80_pair(c,{a[0]});")
    elif op in ("POP", "POP_INDEX"):
        pair = a[0] if op == "POP_INDEX" or a[0] != 3 else 6
        lines += ["uint16_t value = z80_pop(c);", "if (c->fault) return 0;", f"z80_set_pair(c,{pair},value);"]
    elif op in ("PUSH", "PUSH_INDEX"):
        pair = a[0] if op == "PUSH_INDEX" or a[0] != 3 else 6
        lines.append(f"z80_push(c,z80_pair(c,{pair}));")
    elif op == "EX_AF": lines.append("uint8_t t=z->a; z->a=z->a_alt; z->a_alt=t; t=z->f; z->f=z->f_alt; z->f_alt=t;")
    elif op == "EXX": lines.append("for (unsigned n=0;n<6;++n) { uint8_t t=z->r8[n]; z->r8[n]=z->alternate[n]; z->alternate[n]=t; }")
    elif op == "EX_DE_HL": lines.append("uint16_t t=z80_pair(c,1); z80_set_pair(c,1,z80_pair(c,2)); z80_set_pair(c,2,t);")
    elif op == "CPL": lines.append("z->a=(uint8_t)~z->a; z->f=(uint8_t)((z->f&(Z_S|Z_Z|Z_PV|Z_C))|(z->a&0x28)|Z_H|Z_N);")
    elif op in ("SCF", "CCF"):
        carry = "Z_C" if op == "SCF" else "(z->f&Z_C ? Z_H:Z_C)"
        lines.append(f"z->f=(uint8_t)((z->f&(Z_S|Z_Z|Z_PV))|(z->a&0x28)|{carry});")
    elif op == "BIT_INDEX":
        lines += [f"z->wz=(uint16_t)(z80_pair(c,{a[0]})+({a[1]}));", "uint8_t value=z80_read(c,z->wz);", "if (c->fault) return 0;", f"z80_bit(c,value,{a[2]},(uint8_t)(z->wz>>8));"]
    elif op == "BIT_INDEX_WRITE":
        expr=f"value | (1u<<{a[2]})" if a[4] else f"value & ~(1u<<{a[2]})"
        lines += [f"uint16_t address=(uint16_t)(z80_pair(c,{a[0]})+({a[1]}));", "z->wz=address;", "uint8_t value=z80_read(c,address);", "if (c->fault) return 0;", f"value=(uint8_t)({expr});", "z80_write(c,address,value);"]
        if a[3] != 6: lines.append(f"z80_set_reg(c,{a[3]},value);")
    elif op == "LD_IR":
        member = "r" if a[0] else "i"
        if a[1]: lines.append(f"z->a = z->{member}; z->f = (uint8_t)((z->f & Z_C) | (z80_szxy(z->a) & ~Z_PV) | (z->iff2 ? Z_PV:0));")
        else: lines.append(f"z->{member} = z->a;")
    elif op == "LD_BLOCK":
        lines += [f"if (z80_block(c,{a[0]},{int(a[1])})) {{ if (c->fault) return 0; z->wz=0x{(pc+1)&65535:04x}; z->pc=0x{pc:04x}; return 21; }}"]
    elif op == "JP_REG": tail = [f"z->pc = z80_pair(c,{a[0]});", f"return {i.cycles};"]
    elif op == "JP": tail = [f"z->pc=z->wz=0x{a[0]:04x};", "return 10;"]
    elif op == "JP_CC": tail = [f"z->wz=0x{a[1]:04x};", f"z->pc=z80_condition(c,{a[0]}) ? 0x{a[1]:04x}:0x{i.end:04x};", "return 10;"]
    elif op == "JR":
        condition = "1" if a[0] == -1 else f"z80_condition(c,{a[0]})"
        tail = [f"if ({condition}) {{ z->pc=z->wz=0x{a[1]:04x}; return 12; }}", f"z->pc=0x{i.end:04x}; return 7;"]
    elif op == "DJNZ": tail = [f"if (--z->r8[0]) {{ z->pc=z->wz=0x{a[0]:04x}; return 13; }}", f"z->pc=0x{i.end:04x}; return 8;"]
    elif op == "CALL": lines += [f"z80_push(c,0x{i.end:04x});"]; tail = [f"z->pc=z->wz=0x{a[0]:04x};", f"return {i.cycles};"]
    elif op == "CALL_CC":
        lines += [f"z->wz=0x{a[1]:04x};", f"if (z80_condition(c,{a[0]})) {{ z80_push(c,0x{i.end:04x}); if (c->fault) return 0; z->pc=0x{a[1]:04x}; return 17; }}"]
        tail = [f"z->pc=0x{i.end:04x};", "return 10;"]
    elif op in ("RET", "RETN"):
        lines.append("uint16_t target=z80_pop(c);")
        if op == "RETN": lines.append("z->iff1=z->iff2;")
        tail = ["z->pc=z->wz=target;", f"return {i.cycles};"]
    elif op == "RET_CC":
        lines += [f"if (z80_condition(c,{a[0]})) {{ uint16_t target=z80_pop(c); if (c->fault) return 0; z->pc=z->wz=target; return 11; }}"]
        tail = [f"z->pc=0x{i.end:04x};", "return 5;"]
    else: raise ValueError(f"missing Z80 emission: {op}")
    return "\n".join([*lines, "if (c->fault) return 0;", *tail])


def emit_z80(program: ZProgram | None):
    lines = ["static unsigned translated_z80_step(CPU *c) {", "    Z80CPU *z=&c->z80_cpu;", "    switch (z->pc) {"]
    if program:
        for pc, variants in sorted(program.instructions.items()):
            lines.append(f"    case 0x{pc:04x}: {{")
            for inst in variants:
                checks = " && ".join(f"c->z80_bus.ram[0x{(pc+n)&0x1FFF:04x}]==0x{b:02x}" for n,b in enumerate(inst.raw))
                lines += [f"        if ({checks}) {{", z80_instruction_code(inst), "        }"]
            lines += ["        fail(c, \"Z80 RAM differs from compiled instruction variants\", 0xa00000+(z->pc&0x1fff)); return 0;", "    }"]
    lines += ["    default: fail(c, \"Z80 PC has no static translation\", 0xa00000+(z->pc&0x1fff)); return 0;", "    }", "}"]
    return "\n".join(lines)
