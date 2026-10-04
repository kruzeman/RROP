"""Bounded, backwards value analysis for indirect MC68000 control transfers.

Only decoded instructions and immutable ROM reads participate. Unknown values,
calls, joins and oversized sets stop a slice; this never scans data for code.
The result supplies possible roots, not an exhaustive control-flow proof.
"""
from .decode import DecodeError, Decoder, EA, signed


LIMIT = 256
DEPTH = 32


def finite(values):
    result = frozenset(values)
    return result if len(result) <= LIMIT else None


def combine(left, right, operation):
    if left is None or right is None or len(left) * len(right) > LIMIT:
        return None
    return finite(operation(a, b) for a in left for b in right)


def valid_roots(program, targets, occupied):
    """Reject ambiguous candidate sets before they can poison known decoding."""
    for pc in targets:
        if pc in occupied and occupied[pc] != pc:
            return False
        try:
            inst = program.instructions.get(pc) or Decoder(program.rom, pc).decode()
        except DecodeError:
            return False
        if any(a in targets or a in occupied and occupied[a] != pc for a in range(pc+1, inst.end)):
            return False
    return True


class ValueSlice:
    def __init__(self, program, preceding, joins, allow_ram=False):
        self.program, self.preceding, self.joins = program, preceding, joins
        self.allow_ram = allow_ram
        self.cache = {}
        self.reads = set()

    def address(self, ea, before, depth=0):
        if ea is None or depth > DEPTH:
            return None
        if ea.mode == 7 and ea.reg in (0, 1, 2):
            return frozenset((ea.value & 0xffffff,))
        if ea.mode == 7 and ea.reg == 3:
            base = frozenset((ea.value,))
        elif ea.mode in (2, 3, 5, 6):
            base = self.register(EA(1, ea.reg), before, 4, depth+1)
            if ea.mode in (5, 6) and base is not None:
                base = finite(a + ea.value for a in base)
        else:
            return None
        if ea.mode == 6 or (ea.mode == 7 and ea.reg == 3):
            index = EA(1 if ea.index & 0x8000 else 0, (ea.index >> 12) & 7)
            size = 4 if ea.index & 0x800 else 2
            values = self.register(index, before, size, depth+1)
            if values is not None:
                values = finite(signed(v, size*8) for v in values)
            base = combine(base, values, lambda a, b: a+b)
        return None if base is None else finite(a & 0xffffff for a in base)

    def operand(self, ea, before, size, depth):
        if ea is None or depth > DEPTH:
            return None
        mask = (1 << (size*8))-1
        if ea.mode in (0, 1):
            values = self.register(ea, before, size, depth+1)
            return frozenset(range(256)) if values is None and size == 1 else values
        if ea.mode == 7 and ea.reg == 4:
            return frozenset((ea.value & mask,))
        addresses = self.address(ea, before, depth+1)
        # The cartridge is immutable; work RAM, devices and bus aliases are not.
        if addresses is None or any(a & 1 and size > 1 or a+size > len(self.program.rom)
                                    for a in addresses):
            return frozenset(range(256)) if size == 1 else None
        self.reads.update((a, size) for a in addresses)
        return finite(int.from_bytes(self.program.rom[a:a+size], 'big') for a in addresses)

    def register(self, reg, before, size, depth=0):
        if depth > DEPTH or before in self.joins or before >= len(self.program.rom) and not self.allow_ram:
            return None
        key = (reg, before, size)
        if key in self.cache:
            return self.cache[key]
        inst = self.preceding.get(before)
        if inst is None or inst.op in ('JSR', 'BSR', 'JMP', 'RTS', 'RTE', 'RTR',
                                       'TRAP', 'STOP', 'DBCC', 'ILLEGAL', 'LINE_A', 'LINE_F'):
            return None
        if inst.op == 'BCC' and inst.condition == 0:
            return None
        if inst.op == 'BCC' and inst.condition in (2, 3, 4, 5):
            cmp = self.preceding.get(inst.pc)
            if cmp and cmp.op in ('CMP', 'CMPI') and cmp.dst == reg and cmp.src and (
                    cmp.src.mode, cmp.src.reg) == (7, 4):
                # The physical successor is the fall-through path. Bounds on
                # a word/byte do not constrain an unknown register upper half.
                values = self.register(reg, inst.pc, size, depth+1)
                width_mask = (1 << (cmp.size*8))-1
                bound = cmp.src.value & width_mask
                if values is None and size == cmp.size:
                    high = bound if inst.condition == 2 else bound-1
                    if inst.condition in (2, 4) and 0 <= high < LIMIT:
                        values = frozenset(range(high+1))
                if values is not None:
                    tests = {2: lambda v: v <= bound, 3: lambda v: v > bound,
                             4: lambda v: v < bound, 5: lambda v: v >= bound}
                    return finite(v for v in values if tests[inst.condition](v & width_mask))
        # Updating addressing modes changes an address register even without a
        # register destination. MOVEM restores only registers in its mask.
        if reg.mode == 1 and any(ea and ea.mode in (3, 4) and ea.reg == reg.reg
                                for ea in (inst.src, inst.dst)):
            return None
        if inst.op == 'MOVEM_LOAD' and inst.value & (1 << (reg.reg + 8*reg.mode)):
            return None
        if inst.op == 'EXG':
            other = inst.dst if inst.src == reg else inst.src if inst.dst == reg else None
            result = self.register(other or reg, inst.pc, size, depth+1)
        elif inst.dst != reg or inst.op in ('CMP', 'CMPI', 'CMPA', 'TST', 'BTST', 'MOVEM_STORE'):
            result = self.register(reg, inst.pc, size, depth+1)
        else:
            result = self.written(inst, reg, size, depth+1)
        self.cache[key] = result
        return result

    def written(self, inst, reg, size, depth):
        full_address = reg.mode == 1
        width = 4 if full_address or inst.op in ('MOVEQ', 'LEA', 'SWAP') else inst.size
        mask = (1 << (8*min(width, size)))-1
        op = inst.op
        if op == 'MOVEQ':
            result = frozenset((inst.value & mask,))
        elif op == 'LEA':
            result = self.address(inst.src, inst.pc, depth+1)
        elif op in ('MOVE', 'MOVEA'):
            result = self.operand(inst.src, inst.pc, min(inst.size, size), depth+1)
            if op == 'MOVEA' and inst.size == 2 and size > 2 and result is not None:
                result = finite(signed(v, 16) & mask for v in result)
        elif op == 'CLR':
            result = frozenset((0,))
        elif op in ('AND', 'ANDI'):
            source = self.operand(inst.src, inst.pc, min(inst.size, size), depth+1)
            old = self.register(reg, inst.pc, min(width, size), depth+1)
            if source is not None and old is None:
                # A small mask yields a finite set even when all source bits
                # are unknown. Enumerate submasks, not a guessed table length.
                values = set()
                for value in source:
                    if value.bit_count() > 8:
                        return None
                    sub = value
                    while True:
                        values.add(sub)
                        if len(values) > LIMIT:
                            return None
                        if sub == 0:
                            break
                        sub = (sub-1) & value
                result = frozenset(values)
            else:
                result = combine(old, source, lambda a, b: a & b)
        elif op in ('ADD', 'ADDI', 'SUB', 'SUBI', 'OR', 'ORI', 'EOR', 'EORI',
                    'ADDA', 'SUBA', 'ADDQ', 'SUBQ'):
            old = self.register(reg, inst.pc, min(width, size), depth+1)
            source = (frozenset((inst.value,)) if op in ('ADDQ', 'SUBQ') else
                      self.operand(inst.src, inst.pc, min(inst.size, size), depth+1))
            if op in ('ADDA', 'SUBA') and inst.size == 2 and source is not None:
                source = finite(signed(v, 16) for v in source)
            if op.startswith('ADD'):
                fn = lambda a, b: a+b
            elif op.startswith('SUB'):
                fn = lambda a, b: a-b
            elif op.startswith('OR'):
                fn = lambda a, b: a | b
            else:
                fn = lambda a, b: a ^ b
            # ADD Dn,Dn uses the same value twice, not independent choices.
            if inst.src == reg and old is not None:
                result = finite(fn(v, v) for v in old)
            else:
                result = combine(old, source, fn)
        elif op in ('ASL', 'LSL', 'LSR', 'ASR'):
            source = self.operand(inst.src, inst.pc, 4, depth+1)
            # Right shifts can move unknown upper bits into the requested low
            # word/byte. Read the complete instruction width before shifting.
            old = self.register(reg, inst.pc, width, depth+1)
            if source is None or any(v > 63 for v in source):
                return None
            if op in ('ASL', 'LSL'):
                result = combine(old, source, lambda a, b: a << b)
            elif op == 'LSR':
                result = combine(old, source, lambda a, b: a >> b)
            else:
                result = combine(old, source, lambda a, b: signed(a, width*8) >> b)
        elif op in ('NEG', 'NOT'):
            old = self.register(reg, inst.pc, min(width, size), depth+1)
            result = None if old is None else finite(-v if op == 'NEG' else ~v for v in old)
        elif op == 'EXT':
            source_size = 1 if inst.size == 2 else 2
            old = self.register(reg, inst.pc, source_size, depth+1)
            result = None if old is None else finite(signed(v, source_size*8) for v in old)
        elif op == 'SWAP':
            old = self.register(reg, inst.pc, 4, depth+1)
            result = None if old is None else finite((v >> 16) | ((v & 0xffff) << 16) for v in old)
        else:
            return None
        if result is None:
            return None
        result = finite(v & mask for v in result)
        if width < size:
            upper = self.register(reg, inst.pc, size, depth+1)
            result = combine(upper, result, lambda a, b: (a & ~mask) | b)
        return result


def value_transfers(program):
    """Return finite ROM destinations of decoded indirect jumps and calls."""
    preceding = {inst.end: inst for inst in program.instructions.values()}
    # Do not borrow a definition from a physically adjacent block when another
    # decoded edge can enter here. Call targets also have unknown input state.
    joins = {*program.entries, *(inst.target for inst in program.instructions.values() if inst.target is not None)}
    found = {}
    occupied = None
    for pc in program.indirect:
        if pc in program.pointer_tables or pc in program.ram_callbacks:
            continue
        inst = program.instructions[pc]
        sliced = ValueSlice(program, preceding, joins)
        targets = sliced.address(inst.src, pc)
        if not targets or any(target & 1 or not 8 <= target < len(program.rom) for target in targets):
            continue
        if occupied is None:
            occupied = {a: i.pc for i in program.instructions.values() for a in range(i.pc, i.end)}
        if not valid_roots(program, targets, occupied):
            continue
        found[pc] = {'targets': sorted(targets),
                     'rom_reads': [{'address': a, 'bytes': size} for a, size in sorted(sliced.reads)]}
    return found


def parameter_context(program):
    calls = {}
    for inst in program.instructions.values():
        if inst.op in ('JSR', 'BSR') and inst.target is not None:
            calls.setdefault(inst.target, []).append(inst.pc)
    joins = {*program.entries, *(inst.target for inst in program.instructions.values() if inst.target is not None)}
    return calls, joins, {}


def parameter_constants(program, operand, before, preceding, context):
    """Resolve register parameters stored by a directly called routine.

    The caller's value is used only at that routine's entry, after tracing
    plain register copies. Unknown callers do not exclude known candidates.
    Used for absolute RAM callback slots, never arbitrary address constants.
    """
    calls, joins, slices = context
    for _ in range(8):
        if operand is None or operand.mode not in (0, 1):
            return ()
        if before in calls:
            targets = set()
            for call in calls[before]:
                if call not in slices:
                    slices[call] = ValueSlice(program, preceding, joins)
                values = slices[call].register(operand, call, 4)
                if values is None:
                    continue
                values = {v & 0xffffff for v in values}
                if any(v & 1 or not 8 <= v < len(program.rom) for v in values):
                    continue
                targets.update(values)
            return sorted(targets)
        if before in joins:
            return ()
        inst = preceding.get(before)
        if inst is None or inst.op not in ('MOVE', 'MOVEA', 'LEA', 'CLR', 'TST', 'NOP'):
            return ()
        before = inst.pc
        if operand.mode == 1 and any(ea and ea.mode in (3, 4) and ea.reg == operand.reg
                                    for ea in (inst.src, inst.dst)):
            return ()
        if inst.dst == operand and inst.op != 'TST':
            if inst.op in ('MOVE', 'MOVEA') and inst.size == 4:
                operand = inst.src
            else:
                return ()
    return ()


def inline_pointer_tables(program):
    """Recognize code-delimited longword tables beside an indirect dispatch.

    Some assemblers put the first table word inside the jump's encoding as an
    unused state-zero entry. Only complete pointers after the jump participate.
    The table must end at its earliest handler, or at one terminal instruction
    immediately before that handler. This structural evidence adds possible
    roots; it does not assert that the runtime index is bounded by the table.
    """
    preceding = {inst.end: inst for inst in program.instructions.values()}
    joins = {*program.entries, *(inst.target for inst in program.instructions.values() if inst.target is not None)}
    found = {}
    for pc in program.indirect:
        jump = program.instructions[pc]
        if not jump.src or jump.src.mode != 2:
            continue
        reg, before, load = EA(1, jump.src.reg), pc, None
        for _ in range(8):
            inst = preceding.get(before)
            if inst is None or before in joins or inst.op in ('JSR', 'BSR', 'JMP', 'RTS', 'RTE', 'RTR', 'DBCC', 'TRAP', 'MOVEM_LOAD', 'EXG'):
                break
            before = inst.pc
            if inst.op == 'BCC' and inst.condition == 0:
                break
            if any(ea and ea.mode in (3, 4) and ea.reg == reg.reg for ea in (inst.src, inst.dst)):
                break
            if inst.dst == reg:
                if inst.op == 'MOVEA' and inst.size == 4 and inst.src:
                    if inst.src.mode in (0, 1):
                        reg = inst.src
                        continue
                    load = inst
                break
        if load is None:
            continue
        ea = load.src
        if ea.mode == 7 and ea.reg == 3:
            base = ea.value
        elif ea.mode == 6:
            values = ValueSlice(program, preceding, joins).address(EA(5, ea.reg, ea.value), load.pc)
            if values is None or len(values) != 1:
                continue
            base = next(iter(values))
        else:
            continue
        # No global pointer search: the array must sit beside this dispatch.
        if base & 1 or not pc-2 <= base <= jump.end+8:
            continue
        start = base
        while start < jump.end:
            start += 4
        if base > jump.end:
            gap = base-jump.end
            if gap % 4 == 0:
                # The labelled table base can skip a negative-index fallback
                # pointer placed immediately after the dispatch instruction.
                start = jump.end
            elif any(program.rom[jump.end:base]):
                separator = program.instructions.get(jump.end)
                if separator is None or separator.end != base or not (
                        separator.op == 'RTS' or separator.op in ('JMP', 'BCC') and
                        separator.target is not None and
                        (separator.op == 'JMP' or separator.condition == 0)):
                    continue
        at, boundary, targets = start, len(program.rom), []
        for _ in range(LIMIT):
            if at+4 > len(program.rom) or at >= boundary:
                break
            target = int.from_bytes(program.rom[at:at+4], 'big')
            # Flags in pointer high bytes are intentionally not guessed here.
            if target & 1 or not start <= target < len(program.rom):
                break
            targets.append(target)
            boundary = min(boundary, target)
            at += 4
        if not targets or at > boundary:
            continue
        end = at
        if at != boundary:
            try:
                terminal = Decoder(program.rom, at).decode()
            except DecodeError:
                continue
            if terminal.end != boundary or not (terminal.op == 'RTS' or
                    terminal.op in ('JMP', 'BCC') and terminal.target is not None and
                    (terminal.op == 'JMP' or terminal.condition == 0)):
                continue
            # Include the fallback entry located immediately after the array.
            targets.append(at)
        found[pc] = {'table': base, 'start': start, 'end': end,
                     'count': (end-start)//4, 'targets': sorted(set(targets))}
    return found


def inline_relative_tables(program):
    """Find adjacent signed-word tables feeding PC-relative JMP/JSR."""
    preceding = {inst.end: inst for inst in program.instructions.values()}
    found = {}
    for pc in program.indirect:
        jump = program.instructions[pc]
        ea = jump.src
        if not ea or (ea.mode, ea.reg) != (7, 3) or ea.index & 0x8800:
            continue
        reg = EA(0, (ea.index >> 12) & 7)
        load = preceding.get(pc)
        if not load or load.op != 'MOVE' or load.size != 2 or load.dst != reg or not load.src:
            continue
        source = load.src
        if (source.mode, source.reg) != (7, 3) or source.index & 0x8800:
            continue
        table, base = source.value, ea.value
        # The offset loaded into the dispatch register can come from another
        # index register; both indices still have to be signed words.
        if table & 1 or not pc-2 <= table <= jump.end+8:
            continue
        start = table
        while start < jump.end:
            start += 2
        if table > jump.end and any(program.rom[jump.end:table]):
            continue
        at, boundary, targets = start, len(program.rom), []
        for _ in range(LIMIT):
            if at+2 > len(program.rom) or at >= boundary:
                break
            target = (base + int.from_bytes(program.rom[at:at+2], 'big', signed=True)) & 0xffffff
            if target & 1 or not start <= target < len(program.rom):
                break
            targets.append(target)
            boundary = min(boundary, target)
            at += 2
        if not targets or at != boundary:
            continue
        found[pc] = {'table': table, 'base': base, 'start': start, 'end': at,
                     'count': (at-start)//2, 'targets': sorted(set(targets))}
    return found
