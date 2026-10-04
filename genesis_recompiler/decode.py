"""Decode the supported original MC68000 instruction subset, big endian."""
from dataclasses import dataclass, field


class DecodeError(ValueError):
    pass


def signed(value: int, bits: int) -> int:
    return value - (1 << bits) if value & (1 << (bits - 1)) else value


@dataclass(frozen=True)
class EA:
    mode: int
    reg: int
    value: int = 0
    index: int = 0

    @property
    def direct_target(self):
        if self.mode == 7 and self.reg in (0, 1, 2):
            return self.value & 0xFFFFFF
        return None

    def __str__(self):
        m, r, v = self.mode, self.reg, self.value
        if m == 0: return f"D{r}"
        if m == 1: return f"A{r}"
        if m == 2: return f"(A{r})"
        if m == 3: return f"(A{r})+"
        if m == 4: return f"-(A{r})"
        if m == 5: return f"{v}(A{r})"
        if m == 6: return f"{v}(A{r},index=${self.index:04x})"
        if r in (0, 1): return f"${v & 0xFFFFFF:06x}"
        if r == 2: return f"${v:06x}(PC)"
        if r == 3: return f"${v:06x}(PC,index=${self.index:04x})"
        return f"#${v:x}"


@dataclass
class Instruction:
    pc: int
    end: int
    op: str
    size: int = 0
    src: EA | None = None
    dst: EA | None = None
    value: int = 0
    target: int | None = None
    condition: int = 0
    raw: bytes = b""

    def __str__(self):
        suffix = {0: "", 1: ".B", 2: ".W", 4: ".L"}[self.size]
        args = [str(x) for x in (self.src, self.dst) if x is not None]
        if self.op in ("MOVEQ", "ADDQ", "SUBQ"):
            args.insert(0, f"#{self.value}")
        if self.target is not None: args.append(f"${self.target:06x}")
        if self.op == "STOP": args.append(f"#${self.value:04x}")
        if self.op == "TRAP": args.append(f"#{self.value}")
        if self.op.startswith("MOVEM_"): args.append(f"mask=${self.value:04x}")
        name = self.op + (str(self.condition) if self.op in ("BCC", "DBCC") else "")
        return f"{name}{suffix} {', '.join(args)}".rstrip()

    def successors(self):
        if self.op in ("RTS", "RTE", "RTR", "ILLEGAL", "LINE_A", "LINE_F"): return []
        if self.op == "STOP": return [self.end] if ((self.value>>8)&7)<6 else []
        if self.op == "JMP": return [] if self.target is None else [self.target]
        if self.op in ("JSR", "BSR"): return [self.end] + ([] if self.target is None else [self.target])
        if self.op == "BCC":
            return [self.target] if self.condition == 0 else [self.target, self.end]
        if self.op == "DBCC": return [self.target, self.end]
        return [self.end]


class Decoder:
    def __init__(self, rom: bytes, pc: int, base: int = 0):
        self.rom, self.start, self.pc, self.base = rom, pc, pc, base

    def word(self):
        offset = self.pc - self.base
        if offset < 0 or offset + 2 > len(self.rom):
            raise DecodeError(f"truncated instruction at ${self.start:06x}")
        v = int.from_bytes(self.rom[offset:offset + 2], "big")
        self.pc += 2
        return v

    def long(self): return (self.word() << 16) | self.word()

    def ea(self, mode, reg, size):
        if mode < 5: return EA(mode, reg)
        if mode == 5: return EA(mode, reg, signed(self.word(), 16))
        if mode == 6 or (mode == 7 and reg == 3):
            base = self.pc
            ext = self.word()
            if ext & 0x0700: raise DecodeError("non-68000 indexed extension")
            disp = signed(ext & 255, 8)
            return EA(mode, reg, base + disp if mode == 7 else disp, ext)
        if mode == 7:
            if reg == 0: return EA(mode, reg, signed(self.word(), 16))
            if reg == 1: return EA(mode, reg, self.long())
            if reg == 2:
                base = self.pc
                return EA(mode, reg, base + signed(self.word(), 16))
            if reg == 4: return EA(mode, reg, self.long() if size == 4 else self.word() & ((1 << (size * 8)) - 1))
        raise DecodeError("invalid effective address")

    @staticmethod
    def data(ea, writable=False):
        if ea.mode == 1 or (ea.mode == 7 and ea.reg >= (2 if writable else 5)):
            raise DecodeError("invalid data effective address")

    @staticmethod
    def control(ea):
        if ea.mode not in (2, 5, 6, 7) or (ea.mode == 7 and ea.reg > 3):
            raise DecodeError("invalid control effective address")

    def decode(self):
        if self.pc & 1: raise DecodeError("odd instruction address")
        w = self.word()
        kw = {}
        op, size, src, dst = "", 0, None, None
        if w == 0x4E71: op = "NOP"
        elif w == 0x4AFC: op = "ILLEGAL"
        elif w & 0xfff0 == 0x4e40:
            op, kw = "TRAP", {"value": w & 15}
        elif w & 0xf000 in (0xa000, 0xf000):
            op = "LINE_A" if w & 0xf000 == 0xa000 else "LINE_F"
            kw["value"] = w
        elif w == 0x4E75: op = "RTS"
        elif w == 0x4E73: op = "RTE"
        elif w == 0x4E77: op = "RTR"
        elif w & 0xFFF8 == 0x4E50:
            op, dst = "LINK", EA(1, w & 7)
            kw["value"] = signed(self.word(), 16)
        elif w & 0xFFF8 == 0x4E58: op, dst = "UNLK", EA(1, w & 7)
        elif w & 0xFFF0 == 0x4E60:
            op, dst = ("FROM_USP" if w & 8 else "TO_USP"), EA(1, w & 7)
        elif w & 0xFFF8 == 0x4840: op, size, dst = "SWAP", 4, EA(0, w & 7)
        elif w & 0xFFC0 == 0x4800:
            op, size = "NBCD", 1
            dst = self.ea((w >> 3) & 7, w & 7, size)
            self.data(dst, True)
        elif w & 0xFFB8 == 0x4880:
            op, size, dst = "EXT", (4 if w & 0x40 else 2), EA(0, w & 7)
        elif w == 0x4E72:
            op, kw = "STOP", {"value": self.word()}
        elif w & 0xFFC0 in (0x40C0, 0x44C0, 0x46C0):
            size = 2
            ea = self.ea((w >> 3) & 7, w & 7, size)
            if w & 0xFFC0 == 0x40C0:
                op, dst = "FROM_SR", ea
                self.data(dst, True)
            else:
                op, src = ("TO_CCR" if w & 0xFFC0 == 0x44C0 else "TO_SR"), ea
                self.data(src)
        elif w in (0x003C, 0x007C, 0x023C, 0x027C, 0x0A3C, 0x0A7C):
            size = 2 if w & 0x40 else 1
            src = self.ea(7, 4, size)
            op = ("SR_" if size == 2 else "CCR_") + {0: "OR", 0x0200: "AND", 0x0A00: "EOR"}[w & 0xFF00]
        elif w & 0xFB80 == 0x4880:
            op, size = ("MOVEM_LOAD" if w & 0x0400 else "MOVEM_STORE"), (4 if w & 0x40 else 2)
            kw["value"] = self.word()
            ea = self.ea((w >> 3) & 7, w & 7, size)
            if op == "MOVEM_LOAD":
                if ea.mode not in (2, 3, 5, 6, 7) or (ea.mode == 7 and ea.reg > 3):
                    raise DecodeError("invalid MOVEM load effective address")
                src = ea
            else:
                if ea.mode not in (2, 4, 5, 6, 7) or (ea.mode == 7 and ea.reg > 1):
                    raise DecodeError("invalid MOVEM store effective address")
                dst = ea
        elif w & 0xFFC0 == 0x4840:
            op, size = "PEA", 4
            src = self.ea((w >> 3) & 7, w & 7, size)
            self.control(src)
        elif w & 0xF100 == 0x7000:
            op, size, dst = "MOVEQ", 4, EA(0, (w >> 9) & 7)
            kw["value"] = signed(w & 255, 8)
        elif w & 0xF000 == 0x6000:
            cond, disp = (w >> 8) & 15, signed(w & 255, 8)
            if w & 255 == 0: disp = signed(self.word(), 16)
            op = "BSR" if cond == 1 else "BCC"
            kw = {"condition": cond, "target": (self.start + 2 + disp) & 0xFFFFFF}
        elif w & 0xF0F8 == 0x50C8:
            op, size, dst = "DBCC", 2, EA(0, w & 7)
            kw = {"condition": (w >> 8) & 15, "target": (self.start + 2 + signed(self.word(), 16)) & 0xFFFFFF}
        elif w & 0xF0C0 == 0x50C0:
            op, size, dst = "SCC", 1, self.ea((w >> 3) & 7, w & 7, 1)
            self.data(dst, True)
            kw["condition"] = (w >> 8) & 15
        elif w & 0xFFC0 in (0x4EC0, 0x4E80):
            op = "JMP" if w & 0xFFC0 == 0x4EC0 else "JSR"
            src = self.ea((w >> 3) & 7, w & 7, 4)
            self.control(src)
            kw["target"] = src.direct_target
        elif w & 0xF1C0 == 0x41C0:
            op, size, dst = "LEA", 4, EA(1, (w >> 9) & 7)
            src = self.ea((w >> 3) & 7, w & 7, 4)
            self.control(src)
        elif (w >> 12) in (1, 2, 3):
            size = {1: 1, 2: 4, 3: 2}[w >> 12]
            src = self.ea((w >> 3) & 7, w & 7, size)
            if size == 1 and src.mode == 1: raise DecodeError("byte MOVE from address register")
            dst = self.ea((w >> 6) & 7, (w >> 9) & 7, size)
            op = "MOVEA" if dst.mode == 1 else "MOVE"
            if op == "MOVEA":
                if size == 1: raise DecodeError("byte MOVEA")
            else: self.data(dst, True)
        elif w & 0xF000 == 0x5000 and (w >> 6) & 3 != 3:
            op = "SUBQ" if w & 0x0100 else "ADDQ"
            size = (1, 2, 4)[(w >> 6) & 3]
            dst = self.ea((w >> 3) & 7, w & 7, size)
            kw["value"] = ((w >> 9) & 7) or 8
            if dst.mode == 1:
                if size == 1: raise DecodeError("byte quick operation on address register")
            else: self.data(dst, True)
        elif w & 0xFF00 in (0x0000, 0x0200, 0x0400, 0x0600, 0x0A00, 0x0C00):
            op = {0x0000: "ORI", 0x0200: "ANDI", 0x0400: "SUBI", 0x0600: "ADDI", 0x0A00: "EORI", 0x0C00: "CMPI"}[w & 0xFF00]
            code = (w >> 6) & 3
            if code == 3: raise DecodeError("invalid immediate size")
            size = (1, 2, 4)[code]
            src = self.ea(7, 4, size)
            dst = self.ea((w >> 3) & 7, w & 7, size)
            self.data(dst, True)
        elif w & 0xFF00 in (0x4000, 0x4200, 0x4400, 0x4600, 0x4A00):
            op = {0x4000: "NEGX", 0x4200: "CLR", 0x4400: "NEG", 0x4600: "NOT", 0x4A00: "TST"}[w & 0xFF00]
            code = (w >> 6) & 3
            if code == 3: raise DecodeError("invalid unary size")
            size = (1, 2, 4)[code]
            dst = self.ea((w >> 3) & 7, w & 7, size)
            self.data(dst, True)
        elif w & 0xF1F0 in (0x8100, 0xC100):
            op, size = ("ABCD" if w & 0x4000 else "SBCD"), 1
            src, dst = EA(4 if w & 8 else 0, w & 7), EA(4 if w & 8 else 0, (w >> 9) & 7)
        elif w & 0xF1F8 in (0xC140, 0xC148, 0xC188):
            op, size = "EXG", 4
            form = w & 0xF1F8
            src, dst = EA(0 if form != 0xC148 else 1, (w >> 9) & 7), EA(0 if form == 0xC140 else 1, w & 7)
        elif w & 0xF130 in (0x9100, 0xD100) and (w >> 6) & 3 != 3:
            op, size = ("SUBX" if w & 0xF000 == 0x9000 else "ADDX"), (1, 2, 4)[(w >> 6) & 3]
            src, dst = EA(4 if w & 8 else 0, w & 7), EA(4 if w & 8 else 0, (w >> 9) & 7)
        elif w & 0xF138 == 0xB108 and (w >> 6) & 3 != 3:
            op, size = "CMP", (1, 2, 4)[(w >> 6) & 3]
            src, dst = EA(3, w & 7), EA(3, (w >> 9) & 7)
        elif w & 0xF000 in (0x8000, 0x9000, 0xB000, 0xC000, 0xD000):
            group, form, reg = w & 0xF000, (w >> 6) & 7, (w >> 9) & 7
            if form in (3, 7):
                size = 2 if form == 3 or group in (0x8000, 0xC000) else 4
                src, dst = self.ea((w >> 3) & 7, w & 7, size), EA(1, reg)
                if group in (0x9000, 0xB000, 0xD000):
                    op = {0x9000:"SUBA", 0xB000:"CMPA", 0xD000:"ADDA"}[group]
                else:
                    op = ("DIV" if group == 0x8000 else "MUL") + ("S" if form == 7 else "U")
                    dst, size = EA(0, reg), 2
                    self.data(src)
            else:
                size = (1, 2, 4)[form & 3]
                ea = self.ea((w >> 3) & 7, w & 7, size)
                op = {0x8000:"OR", 0x9000:"SUB", 0xB000:"CMP" if form < 4 else "EOR", 0xC000:"AND", 0xD000:"ADD"}[group]
                if form < 4:
                    src, dst = ea, EA(0, reg)
                    if ea.mode == 1 and (size == 1 or op not in ("ADD", "SUB", "CMP")):
                        raise DecodeError("invalid address-register arithmetic source")
                else:
                    src, dst = EA(0, reg), ea
                    self.data(dst, True)
                    if op != "EOR" and dst.mode == 0:
                        raise DecodeError("register encoding belongs to a different instruction family")
        elif w & 0xF100 == 0x0100 or w & 0xFF00 == 0x0800:
            op = ("BTST", "BCHG", "BCLR", "BSET")[(w >> 6) & 3]
            src = EA(0, (w >> 9) & 7) if w & 0x0100 else EA(7, 4, self.word())
            size = 4 if (w >> 3) & 7 == 0 else 1
            dst = self.ea((w >> 3) & 7, w & 7, size)
            self.data(dst, op != "BTST")
            if dst.mode == 7 and dst.reg == 4: raise DecodeError("immediate bit destination")
        elif w & 0xF000 == 0xE000:
            direction = "L" if w & 0x0100 else "R"
            if (w >> 6) & 3 == 3:
                if w & 0x0800: raise DecodeError("non-68000 memory shift encoding")
                op, size = ("AS", "LS", "ROX", "RO")[(w >> 9) & 3] + direction, 2
                dst = self.ea((w >> 3) & 7, w & 7, size)
                self.data(dst, True)
                if dst.mode < 2: raise DecodeError("memory shift requires memory")
                src = EA(7, 4, 1)
            else:
                op, size = ("AS", "LS", "ROX", "RO")[(w >> 3) & 3] + direction, (1, 2, 4)[(w >> 6) & 3]
                dst = EA(0, w & 7)
                src = EA(0, (w >> 9) & 7) if w & 0x20 else EA(7, 4, ((w >> 9) & 7) or 8)
        else: raise DecodeError(f"unsupported opcode ${w:04x} at ${self.start:06x}")
        return Instruction(self.start, self.pc, op, size, src, dst, raw=self.rom[self.start-self.base:self.pc-self.base], **kw)


@dataclass(frozen=True)
class RamCodeCopy:
    rom_offset: int
    address: int
    size: int


@dataclass
class RamVariant:
    instruction: Instruction
    image: RamCodeCopy
    mutable_address: bool = False


@dataclass
class Program:
    rom: bytes
    instructions: dict[int, Instruction] = field(default_factory=dict)
    errors: dict[int, str] = field(default_factory=dict)
    indirect: list[int] = field(default_factory=list)
    jump_tables: dict[int, dict] = field(default_factory=dict)
    return_tables: dict[int, dict] = field(default_factory=dict)
    ram_callbacks: dict[int, dict] = field(default_factory=dict)
    pointer_tables: dict[int, dict] = field(default_factory=dict)
    value_transfers: dict[int, dict] = field(default_factory=dict)
    inline_pointer_tables: dict[int, dict] = field(default_factory=dict)
    inline_relative_tables: dict[int, dict] = field(default_factory=dict)
    ram_copies: tuple[RamCodeCopy, ...] = ()
    unrolled_blocks: dict[int, dict] = field(default_factory=dict)
    noreturn: tuple[int, ...] = ()
    mutable_addresses: tuple[int, ...] = ()
    trap_data: tuple[tuple[int, int], ...] = ()
    trap_targets: dict[int, int] = field(default_factory=dict)
    entries: tuple[int, ...] = ()
    ram_uploads: list[dict] = field(default_factory=list)
    auto_mutable_addresses: tuple[int, ...] = ()
    ram_variants: dict[int, list[RamVariant]] = field(default_factory=dict)
    ram_variant_errors: list[dict] = field(default_factory=list)
    ram_image_instructions: dict[RamCodeCopy, dict[int, Instruction]] = field(default_factory=dict)
    memory_callbacks: dict[int, dict] = field(default_factory=dict)

    @property
    def instruction_count(self):
        return len(self.instructions) + sum(len(v)-1 for v in self.ram_variants.values())

    def all_instructions(self):
        for pc, inst in self.instructions.items():
            if pc not in self.ram_variants:
                yield inst
        for variants in self.ram_variants.values():
            yield from (v.instruction for v in variants)


def bounded_switches(program: Program):
    """Recognize CMP/unsigned-bound/ASL/MOVE.W/JMP ROM switch tables.

    This is a deliberately narrow compiler pattern, not inference of arbitrary
    register values. Emitted instructions still perform the original table read.
    """
    found = {}
    for cmp in program.instructions.values():
        if cmp.op not in ("CMP", "CMPI") or cmp.size != 4 or not cmp.src or not cmp.dst:
            continue
        if (cmp.src.mode, cmp.src.reg, cmp.dst.mode) != (7, 4, 0): continue
        count, reg = cmp.src.value, cmp.dst.reg
        if not 1 <= count <= 512: continue
        sequence = [cmp]
        for _ in range(4):
            next_inst = program.instructions.get(sequence[-1].end)
            if next_inst is None: break
            sequence.append(next_inst)
        if len(sequence) != 5: continue
        _, branch, shift, move, jump = sequence
        if branch.op != "BCC" or branch.condition != 4: continue
        if branch.target is None or cmp.pc < branch.target < jump.end: continue
        if shift.op != "ASL" or shift.size != 4 or shift.src != EA(7,4,1) or shift.dst != EA(0,reg): continue
        if move.op != "MOVE" or move.size != 2 or move.dst != EA(0,reg): continue
        if jump.op != "JMP": continue
        if any(ea is None or ea.mode != 7 or ea.reg != 3 or (ea.index & 0xf800) != reg << 12 for ea in (move.src,jump.src)): continue
        table, base = move.src.value, jump.src.value
        if table & 1 or table < 0 or table + count*2 > len(program.rom): continue
        targets = [(base + signed(int.from_bytes(program.rom[table+n*2:table+n*2+2],"big"),16)) & 0xffffff for n in range(count)]
        if any(pc & 1 or not 0 <= pc < len(program.rom) for pc in targets): continue
        found[jump.pc] = {"table":table, "base":base, "count":count, "targets":targets}
    return found


def bounded_return_tables(program: Program):
    """Recognize masked absolute-pointer dispatch through a pushed PC and RTS.

    AND.W/OR.B bound the word index; ASL.W #2 selects four-byte entries.
    A local LEA fixes the ROM table base. Instructions still execute the
    original table read/push/return; this only adds static translation roots.
    """
    found = {}
    for mask in program.instructions.values():
        if mask.op not in ("AND", "ANDI") or mask.size != 2:
            continue
        if not mask.src or mask.src.mode != 7 or mask.src.reg != 4 or not mask.dst or mask.dst.mode != 0:
            continue
        count = (mask.src.value | 0xff) + 1
        if count > 512: continue
        reg = mask.dst.reg
        sequence = [mask]
        for _ in range(4):
            next_inst = program.instructions.get(sequence[-1].end)
            if next_inst is None: break
            sequence.append(next_inst)
        if len(sequence) != 5: continue
        _, merge, shift, base, push = sequence
        if merge.op != "OR" or merge.size != 1 or not merge.src or merge.src.mode != 0 or merge.dst != EA(0,reg): continue
        if shift.op != "ASL" or shift.size != 2 or shift.src != EA(7,4,2) or shift.dst != EA(0,reg): continue
        if base.op != "LEA" or not base.src or base.src.direct_target is None or not base.dst or base.dst.mode != 1 or base.dst.reg == 7: continue
        if push.op != "MOVE" or push.size != 4 or push.dst != EA(4,7) or not push.src:
            continue
        ea = push.src
        if ea.mode != 6 or ea.reg != base.dst.reg or (ea.index & 0xf800) != reg << 12: continue
        # Palette/address setup after the push may replace the table register,
        # but must leave the stack and its newly pushed PC intact.
        ret = program.instructions.get(push.end)
        for _ in range(2):
            if ret is None or ret.op != "LEA" or not ret.dst or ret.dst.reg == 7: break
            ret = program.instructions.get(ret.end)
        if ret is None or ret.op != "RTS": continue
        table = (base.src.direct_target + ea.value) & 0xffffff
        if table & 1 or table + count*4 > len(program.rom): continue
        targets = [int.from_bytes(program.rom[table+n*4:table+n*4+4],"big") & 0xffffff for n in range(count)]
        if any(pc & 1 or not 8 <= pc < len(program.rom) for pc in targets): continue
        found[ret.pc] = {"table":table, "count":count, "push_pc":push.pc, "targets":targets}
    return found


def bounded_pointer_tables(program: Program):
    """Recognize unsigned bounds and four-byte indexed ROM function tables.

    The dispatch block may be the taken BCS path or the fall-through BCC path.
    Up to two constant-to-memory stores may precede scaling. The pointer load
    is followed by a register-indirect jump/call with optional argument setup.
    """
    found = {}
    for cmp in program.instructions.values():
        if cmp.op not in ("CMP", "CMPI") or cmp.size not in (2, 4): continue
        if not cmp.src or cmp.src.mode != 7 or cmp.src.reg != 4 or not cmp.dst or cmp.dst.mode != 0: continue
        count, reg = cmp.src.value, cmp.dst.reg
        if not 1 <= count <= 512: continue
        branch = program.instructions.get(cmp.end)
        if not branch or branch.op != "BCC" or branch.condition not in (4, 5): continue
        pc = branch.target if branch.condition == 5 else branch.end
        inst = program.instructions.get(pc)
        for _ in range(2):
            if not inst or inst.op != "MOVE" or inst.size != 4 or not inst.src or inst.src.mode != 7 or inst.src.reg != 4 or not inst.dst or inst.dst.mode < 2: break
            inst = program.instructions.get(inst.end)
        if inst and inst.op in ("ASL", "LSL") and inst.size == cmp.size and inst.src == EA(7,4,2) and inst.dst == EA(0,reg):
            inst = program.instructions.get(inst.end)
        else:
            for _ in range(2):
                if not inst or inst.op != "ADD" or inst.size != cmp.size or inst.src != EA(0,reg) or inst.dst != EA(0,reg):
                    inst = None
                    break
                inst = program.instructions.get(inst.end)
        if not inst or inst.op != "MOVEA" or inst.size != 4 or not inst.src or not inst.dst: continue
        ea = inst.src
        if ea.mode != 7 or ea.reg != 3 or (ea.index & 0xf800) != reg << 12: continue
        # A word bound cannot constrain a long index's unknown upper half.
        table, pointer = ea.value, inst.dst
        if table & 1 or table < 0 or table + count*4 > len(program.rom): continue
        jump = program.instructions.get(inst.end)
        for _ in range(2):
            if not jump or jump.op not in ("LEA", "MOVE", "MOVEA") or jump.dst == pointer: break
            if any(operand and operand.mode in (3, 4) and operand.reg == pointer.reg for operand in (jump.src, jump.dst)): break
            jump = program.instructions.get(jump.end)
        if not jump or jump.op not in ("JMP", "JSR") or jump.src != EA(2, pointer.reg): continue
        if branch.condition == 4 and branch.end <= branch.target < jump.end: continue
        targets = [int.from_bytes(program.rom[table+n*4:table+n*4+4], "big") & 0xffffff for n in range(count)]
        if any(pc & 1 or not 8 <= pc < len(program.rom) for pc in targets): continue
        found[jump.pc] = {"table": table, "count": count, "targets": targets}
    return found


def inline_unrolled_blocks(program: Program):
    """Recognize inline MOVE.L/ADDA.W rows entered by a negative word index.

    Two ADD.W Dn,Dn and NEG.W precede JMP end(PC,Dn.W). The bytes between
    that jump and its base must be identical four-byte MOVE/ADDA units.
    This discovers possible ROM code roots, without assuming runtime bounds.
    """
    preceding = {inst.end: inst for inst in program.instructions.values()}
    found = {}
    for pc in program.indirect:
        jump = program.instructions[pc]
        ea = jump.src
        if jump.op != "JMP" or not ea or ea.mode != 7 or ea.reg != 3 or ea.index & 0x8800: continue
        reg, base = (ea.index >> 12) & 7, ea.value
        inst = preceding.get(pc)
        if not inst or inst.op != "NEG" or inst.size != 2 or inst.dst != EA(0,reg): continue
        for _ in range(2):
            inst = preceding.get(inst.pc)
            if not inst or inst.op != "ADD" or inst.size != 2 or inst.src != EA(0,reg) or inst.dst != EA(0,reg):
                inst = None
                break
        if not inst: continue
        start, span = jump.end, base-jump.end
        if span <= 0 or span > 1024 or span%4 or base >= len(program.rom): continue
        try:
            move = Decoder(program.rom,start).decode()
            add = Decoder(program.rom,move.end).decode()
        except DecodeError: continue
        if move.op != "MOVE" or move.size != 4 or not move.src or move.src.mode != 0 or not move.dst or move.dst.mode != 3: continue
        if add.op != "ADDA" or add.size != 2 or not add.src or add.src.mode != 0 or add.dst != EA(1,move.dst.reg): continue
        if move.end != start+2 or add.end != start+4: continue
        unit = program.rom[start:start+4]
        if program.rom[start:base] != unit*(span//4): continue
        found[pc] = {"start": start, "end": base, "stride": 4,
                     "count": span//4, "targets": list(range(start,base+1,4))}
    return found


def constant_ram_callbacks(program: Program):
    """Find ROM function constants stored in absolute work-RAM callback slots.

    A short backwards slice links a register-indirect call to a longword RAM
    load, including register copies. Only reachable stores are considered.
    This adds possible translation roots, not a proof that a slot can contain
    no other values: the indirect call remains unresolved in the report.
    """
    preceding = {inst.end: inst for inst in program.instructions.values()}

    def slot(ea):
        if ea and ea.mode == 7 and ea.reg in (0, 1):
            address = ea.direct_target
            if address >= 0xe00000 and not address & 1:
                return 0xff0000 | (address & 0xffff)
        return None

    def origin(ea, before, kind):
        for _ in range(8):
            if kind == "slot" and slot(ea) is not None:
                return slot(ea)
            if kind == "constant" and ea and ea.mode == 7 and ea.reg == 4:
                return ea.value & 0xffffff
            if not ea or ea.mode not in (0, 1): return None
            inst = preceding.get(before)
            if inst is None: return None
            before = inst.pc
            if inst.op == "BCC" and inst.condition != 0:
                continue  # Slice the fall-through path only; add possible roots.
            if inst.op not in ("MOVE", "MOVEA", "MOVEQ", "LEA", "CLR", "TST", "NOP"):
                return None
            if inst.dst == ea and inst.op != "TST":
                if inst.op in ("MOVE", "MOVEA") and inst.size == 4:
                    ea = inst.src
                    continue
                if kind == "constant" and inst.op == "LEA" and inst.src:
                    return inst.src.direct_target
                return None
            # Pre/postincrement also changes an address register used by the slice.
            if ea.mode == 1 and any(operand and operand.mode in (3, 4) and operand.reg == ea.reg
                                    for operand in (inst.src, inst.dst)):
                return None
        return None

    stores = {}
    from .discovery import parameter_constants, parameter_context
    context = parameter_context(program)
    for inst in program.instructions.values():
        if inst.op != "MOVE" or inst.size != 4: continue
        address = slot(inst.dst)
        if address is None: continue
        target = origin(inst.src, inst.pc, "constant")
        targets = parameter_constants(program, inst.src, inst.pc, preceding, context)
        if target is not None and not target & 1 and 8 <= target < len(program.rom):
            targets = [*targets, target]
        for target in set(targets):
            stores.setdefault(address, []).append((inst.pc, target))
    found = {}
    for pc in program.indirect:
        inst = program.instructions[pc]
        if not inst.src or inst.src.mode != 2: continue
        address = origin(EA(1, inst.src.reg), pc, "slot")
        if address not in stores: continue
        found[pc] = {"slot": address,
                     "stores": sorted({store for store, _ in stores[address]}),
                     "targets": sorted({target for _, target in stores[address]})}
    return found


def analyze(rom: bytes, entries: list[int], ram_copies=(), noreturn=(), mutable_addresses=(), trap_data=()) -> Program:
    copies = tuple(ram_copies)
    explicit_copies = copies
    for copy in copies:
        if (copy.rom_offset < 0 or copy.size < 2 or copy.rom_offset+copy.size > len(rom)
                or not 0xe00000 <= copy.address <= 0xffffff or copy.address & 1
                or (copy.address & 0xffff)+copy.size > 0x10000):
            raise ValueError("68000 RAM copy must fit the ROM source and one aligned 64 KiB work-RAM window")
    if len(copies) > 256:
        raise ValueError("at most 256 68000 RAM images are supported")
    noreturn = tuple(sorted(set(noreturn)))
    if any(pc & 1 or not (8 <= pc < len(rom) or any(
            copy.address <= pc < copy.address+copy.size for copy in copies)) for pc in noreturn):
        raise ValueError("nonreturning targets must be aligned addresses in ROM or a declared RAM code copy")
    trap_data = tuple(sorted(set(trap_data)))
    if (any(not 0 <= vector <= 15 or not 0 <= count <= 256 or count & 1 for vector, count in trap_data)
            or len({vector for vector, _ in trap_data}) != len(trap_data)):
        raise ValueError("TRAP data annotations require distinct trap numbers 0..15 and even byte counts 0..256")
    program = Program(rom, ram_copies=copies, noreturn=noreturn, trap_data=trap_data,
                      entries=tuple(sorted({*entries, *(copy.address for copy in copies)})))
    pending, occupied = list(reversed([*entries, *(copy.address for copy in copies)])), {}
    ram_pending, ram_seen, ram_occupied = [], set(), {}

    def successors(inst):
        result = inst.successors()
        if inst.op == 'TRAP':
            result = [inst.end + dict(trap_data).get(inst.value, 0)]
            vector = (32 + inst.value) * 4
            if vector + 4 <= len(rom):
                target = int.from_bytes(rom[vector:vector+4], 'big') & 0xffffff
                program.trap_targets[inst.value] = target
                if not target & 1 and (8 <= target < len(rom) or any(
                        copy.address <= target < copy.address+copy.size for copy in copies)):
                    result.append(target)
        if inst.op in ('JSR', 'BSR') and inst.target in noreturn:
            result = [inst.target]
        return result

    while True:
        while pending or ram_pending:
            if ram_pending:
                image, pc = ram_pending.pop()
                if (image, pc) in ram_seen:
                    continue
                ram_seen.add((image, pc))
                owned = ram_occupied.setdefault(image, {})
                try:
                    inst = Decoder(rom[image.rom_offset:image.rom_offset+image.size], pc, image.address).decode()
                    if any(a in owned and owned[a] != pc for a in range(pc, inst.end)):
                        raise DecodeError('instruction overlaps previously decoded RAM image code')
                except DecodeError as exc:
                    program.ram_variant_errors.append({'rom_offset': image.rom_offset,
                        'address': image.address, 'size': image.size, 'pc': pc, 'message': str(exc)})
                    if pc not in program.instructions:
                        program.errors[pc] = str(exc)
                    continue
                variants = program.ram_variants.setdefault(pc, [])
                program.ram_image_instructions.setdefault(image, {})[pc] = inst
                if not any(v.instruction.raw == inst.raw for v in variants):
                    variants.append(RamVariant(inst, image))
                first = pc not in program.instructions
                program.instructions.setdefault(pc, inst)
                program.errors.pop(pc, None)
                owned.update((a, pc) for a in range(pc, inst.end))
                if first and inst.op in ('JSR', 'JMP') and inst.target is None:
                    program.indirect.append(pc)
                for target in reversed(successors(inst)):
                    if image.address <= target < image.address+image.size:
                        ram_pending.append((image, target))
                    else:
                        pending.append(target)
                continue
            pc = pending.pop()
            if pc >= 0xe00000:
                images = [copy for copy in copies if copy.address <= pc < copy.address+copy.size]
                if images:
                    ram_pending.extend((copy, pc) for copy in reversed(images))
                    continue
            if pc in program.instructions or pc in program.errors: continue
            if pc in occupied:
                program.errors[pc] = f"entry overlaps instruction at ${occupied[pc]:06x}"
                continue
            try:
                inst = Decoder(rom, pc).decode()
                if any(a in occupied for a in range(pc, inst.end)):
                    raise DecodeError("instruction overlaps previously decoded code")
            except DecodeError as exc:
                program.errors[pc] = str(exc)
                continue
            program.instructions[pc] = inst
            for addr in range(pc, inst.end): occupied[addr] = pc
            if inst.op in ("JSR", "JMP") and inst.target is None: program.indirect.append(pc)
            pending.extend(reversed(successors(inst)))
        for pc, table in bounded_switches(program).items():
            if pc in program.jump_tables: continue
            program.jump_tables[pc] = table
            program.indirect.remove(pc)
            pending.extend(reversed(table["targets"]))
        for pc, table in bounded_return_tables(program).items():
            if pc in program.return_tables: continue
            program.return_tables[pc] = table
            pending.extend(reversed(table["targets"]))
        for pc, table in bounded_pointer_tables(program).items():
            if pc in program.pointer_tables: continue
            program.pointer_tables[pc] = table
            pending.extend(reversed(table["targets"]))
        for pc, callback in constant_ram_callbacks(program).items():
            previous = program.ram_callbacks.get(pc, {}).get("targets", [])
            program.ram_callbacks[pc] = callback
            pending.extend(reversed([target for target in callback["targets"] if target not in previous]))
        from .callback_discovery import memory_callbacks
        for pc, callback in memory_callbacks(program).items():
            previous = program.memory_callbacks.get(pc, {}).get('targets', [])
            program.memory_callbacks[pc] = callback
            pending.extend(reversed([target for target in callback['targets'] if target not in previous]))
        for pc, block in inline_unrolled_blocks(program).items():
            if pc in program.unrolled_blocks: continue
            program.unrolled_blocks[pc] = block
            pending.extend(reversed(block["targets"]))
        from .discovery import inline_pointer_tables, inline_relative_tables, value_transfers
        for pc, transfer in value_transfers(program).items():
            previous = program.value_transfers.get(pc, {}).get("targets", [])
            program.value_transfers[pc] = transfer
            pending.extend(reversed([target for target in transfer["targets"] if target not in previous]))
        for pc, table in inline_pointer_tables(program).items():
            if pc in program.inline_pointer_tables: continue
            program.inline_pointer_tables[pc] = table
            pending.extend(reversed(table["targets"]))
        for pc, table in inline_relative_tables(program).items():
            if pc in program.inline_relative_tables: continue
            program.inline_relative_tables[pc] = table
            pending.extend(reversed(table["targets"]))
        from .ram_discovery import ram_uploads, valid_upload_entries
        uploads = ram_uploads(program)
        program.ram_uploads = []
        for upload in uploads:
            copy = upload['copy']
            start, end = copy.address & 0xffff, (copy.address & 0xffff)+copy.size

            def overlaps(other):
                return start < (other.address & 0xffff)+other.size and (other.address & 0xffff) < end

            def same_image(other):
                return (start == other.address & 0xffff and copy.size == other.size and
                        rom[copy.rom_offset:copy.rom_offset+copy.size] ==
                        rom[other.rom_offset:other.rom_offset+other.size])

            conflict = any(overlaps(other['copy']) and not same_image(other['copy']) for other in uploads)
            existing = next((other for other in copies if overlaps(other) and other.address == copy.address
                             and same_image(other)), None)
            declared = existing in explicit_copies if existing is not None else False
            valid = valid_upload_entries(program, upload)
            conflict |= any(overlaps(other) and not same_image(other) for other in copies)
            status = 'declared' if declared else 'invalid' if not valid else 'variant' if conflict else 'translated'
            if existing is None and valid:
                if len(copies) >= 256:
                    status = 'limit'
                else:
                    copies = (*copies, copy)
                    program.ram_copies = copies
                    existing = copy
            record = {key: value for key, value in upload.items() if key != 'copy'}
            record.update(rom_offset=copy.rom_offset, address=copy.address, size=copy.size, status=status)
            program.ram_uploads.append(record)
            if existing is not None:
                for target in upload['entries']:
                    if (existing, target) not in ram_seen:
                        ram_pending.append((existing, target))
        if not pending and not ram_pending: break
    declared_mutable = tuple(sorted(set(mutable_addresses)))
    for pc in declared_mutable:
        if not any(v.instruction.op in ('MOVE', 'LEA') and v.instruction.src
                   and (v.instruction.src.mode, v.instruction.src.reg) == (7, 1)
                   for v in program.ram_variants.get(pc, [])):
            raise ValueError("mutable 68000 address must name a translated RAM MOVE or LEA with an absolute-long source")
    from .ram_discovery import mutable_fields
    fields = mutable_fields(program)
    auto = set()
    for pc, variants in program.ram_variants.items():
        for variant in variants:
            inst = variant.instruction
            eligible = inst.op in ('MOVE', 'LEA') and inst.src and (inst.src.mode, inst.src.reg) == (7, 1)
            inferred = eligible and (pc+2) & 0xffff in fields and variant.image not in explicit_copies
            variant.mutable_address = bool(eligible and (pc in declared_mutable or inferred))
            if inferred: auto.add(pc)
    program.auto_mutable_addresses = tuple(sorted(auto))
    program.mutable_addresses = tuple(sorted({*declared_mutable, *program.auto_mutable_addresses}))
    return program
