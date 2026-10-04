"""Discover bounded ROM-to-work-RAM uploads referenced as executable code.

The original program still copies and patches RAM. Static images only provide
translation bytes; every emitted RAM instruction retains its byte guard.
"""
from .decode import DecodeError, Decoder, EA, RamCodeCopy
from .discovery import DEPTH, ValueSlice, parameter_context, valid_roots


class CallerSlice(ValueSlice):
    def __init__(self, program, preceding, joins, binding=None):
        super().__init__(program, preceding, joins)
        self.binding = binding

    def register(self, reg, before, size, depth=0):
        if depth > DEPTH:
            return None
        if self.binding and before == self.binding[0]:
            _, call, caller = self.binding
            return caller.register(reg, call, size, depth+1)
        return super().register(reg, before, size, depth)


def copy_loops(program):
    """Find straight MOVE (An)+,(Am)+ bodies bounded by a backwards DBF."""
    result = []
    for branch in program.instructions.values():
        if branch.op != 'DBCC' or branch.condition != 1 or branch.target >= branch.pc:
            continue
        pc, body = branch.target, []
        while pc < branch.pc and len(body) < 32:
            inst = program.instructions.get(pc)
            if (inst is None or inst.op != 'MOVE' or inst.size not in (1, 2, 4)
                    or not inst.src or not inst.dst or inst.src.mode != 3 or inst.dst.mode != 3
                    or inst.src.reg == inst.dst.reg or inst.size == 1 and 7 in (inst.src.reg, inst.dst.reg)):
                break
            body.append(inst)
            pc = inst.end
        if not body or pc != branch.pc:
            continue
        first = body[0]
        if any(i.src != first.src or i.dst != first.dst or i.size != first.size for i in body):
            continue
        # Entry edges to the first MOVE are handled by the value slice/call
        # context. Edges into the middle defeat first-iteration initialization.
        if any(i.target is not None and branch.target < i.target <= branch.pc and i.pc != branch.pc
               for i in program.instructions.values()):
            continue
        result.append((branch, first, len(body)*first.size))
    return result


def unrolled_copies(program):
    """Recognize contiguous postincrement moves with no loop backedge."""
    preceding = {i.end:i for i in program.instructions.values()}
    result = []
    for first in program.instructions.values():
        if (first.op != 'MOVE' or first.size not in (1, 2, 4) or not first.src or not first.dst
                or first.src.mode != 3 or first.dst.mode != 3 or first.src.reg == first.dst.reg
                or first.size == 1 and 7 in (first.src.reg, first.dst.reg)):
            continue
        previous = preceding.get(first.pc)
        if previous and previous.op == 'MOVE' and previous.size == first.size and (
                previous.src, previous.dst) == (first.src, first.dst):
            continue
        pc, body = first.pc, []
        while len(body) < 32:
            inst = program.instructions.get(pc)
            if not inst or inst.op != 'MOVE' or (inst.src, inst.dst, inst.size) != (first.src, first.dst, first.size):
                break
            body.append(inst)
            pc = inst.end
        following = program.instructions.get(pc)
        if following and following.op == 'DBCC':
            continue
        if len(body) == 32 or any(i.target is not None and first.pc < i.target < pc
                                 for i in program.instructions.values()):
            continue
        if any(i.target == first.pc and i.pc >= first.pc for i in program.instructions.values()):
            continue
        result.append((None, first, len(body)*first.size))
    return result


def upload_states(program, branch, first, stride, preceding, calls):
    """Evaluate each call context separately, preserving argument correlation."""
    joins = {*program.entries, *(i.target for i in program.instructions.values()
                                 if i.target is not None and (branch is None or i.pc != branch.pc))}

    def function_entry(before):
        for _ in range(48):
            if before in calls:
                return before
            inst = preceding.get(before)
            if inst is None or inst.op in ('RTS', 'RTE', 'RTR', 'JMP', 'ILLEGAL', 'LINE_A', 'LINE_F'):
                break
            if inst.op == 'BCC' and inst.condition == 0:
                break
            before = inst.pc
        return None

    def contexts(before, depth=0, active=()):
        entry = function_entry(before)
        if entry is None or depth >= 3 or entry in active:
            return [CallerSlice(program, preceding, joins)]
        result = []
        for call in calls[entry]:
            for parent in contexts(call, depth+1, (*active, entry)):
                result.append(CallerSlice(program, preceding, joins, (entry, call, parent)))
                if len(result) >= 32:
                    return result
        return result

    found = set()
    for sliced in [CallerSlice(program, preceding, joins), *contexts(first.pc)]:
        source = sliced.address(EA(2, first.src.reg), first.pc)
        destination = sliced.address(EA(2, first.dst.reg), first.pc)
        count = sliced.register(branch.dst, first.pc, 2) if branch else frozenset((0,))
        if any(v is None or len(v) != 1 for v in (source, destination, count)):
            continue
        source, destination, count = next(iter(source)), next(iter(destination)), next(iter(count))
        size = stride*(count+1)  # DBF repeats even for an initial zero count.
        if (source & 1 or destination & 1 or not 8 <= source < len(program.rom)
                or size < 2 or size > 65536 or source+size > len(program.rom)
                or not 0xe00000 <= destination <= 0xffffff
                or (destination & 0xffff)+size > 65536):
            continue
        found.add((source, destination, size))
    return sorted(found)


def execution_references(program):
    """Known transfers plus finite register transfers and RAM IRQ vectors."""
    references = {pc for pc in program.entries if pc >= 0xe00000 and not pc & 1}
    references.update(i.target for i in program.all_instructions()
                      if i.target is not None and i.target >= 0xe00000 and not i.target & 1
                      and (i.pc < len(program.rom) or i.op in ('JSR', 'JMP')))
    references.update(pc for pc in program.trap_targets.values() if pc >= 0xe00000 and not pc & 1)
    for offset in (0x70, 0x78):
        if offset+4 <= len(program.rom):
            pc = int.from_bytes(program.rom[offset:offset+4], 'big') & 0xffffff
            if pc >= 0xe00000 and not pc & 1:
                references.add(pc)
    preceding = {i.end:i for i in program.instructions.values()}
    _, joins, _ = parameter_context(program)
    occupied = None
    for pc in program.indirect:
        targets = ValueSlice(program, preceding, joins).address(program.instructions[pc].src, pc)
        # Reject an ambiguous set as a whole; filtering its plausible RAM
        # members can turn unrelated table bytes into fake executable uploads.
        if not targets or any(t & 1 or not (8 <= t < len(program.rom) or t >= 0xe00000) for t in targets):
            continue
        rom_targets = {t for t in targets if t < len(program.rom)}
        if rom_targets:
            if occupied is None:
                occupied = {a: i.pc for i in program.instructions.values() for a in range(i.pc, i.end)}
            if not valid_roots(program, rom_targets, occupied):
                continue
        references.update(t for t in targets if t >= 0xe00000)
    return references


def ram_uploads(program):
    """Return candidate copies with their loop and execution-entry evidence."""
    preceding = {i.end:i for i in program.instructions.values()}
    calls, _, _ = parameter_context(program)
    references = execution_references(program)
    found = []
    for branch, first, stride in [*copy_loops(program), *unrolled_copies(program)]:
        for source, destination, size in upload_states(program, branch, first, stride, preceding, calls):
            entries = sorted(pc for pc in references
                             if (destination & 0xffff) <= (pc & 0xffff) < (destination & 0xffff)+size)
            if not entries:
                continue
            for window in sorted({pc & 0xff0000 for pc in entries}):
                address = window | (destination & 0xffff)
                found.append({'copy': RamCodeCopy(source, address, size),
                              'loop_pc': first.pc, 'dbf_pc': branch.pc if branch else None,
                              'write_address': destination,
                              'entries': [pc for pc in entries if pc & 0xff0000 == window]})
    return found


def valid_upload_entries(program, upload):
    """Reject the whole candidate when an execution root cannot be decoded.

    Address constants can alias a data upload. They are not sufficient evidence
    when a root is invalid, crosses the image boundary, or overlaps another
    candidate instruction. Remaining control flow is decoded normally later.
    """
    copy = upload['copy']
    image = program.rom[copy.rom_offset:copy.rom_offset+copy.size]
    occupied = {}
    try:
        for pc in upload['entries']:
            inst = Decoder(image, pc, copy.address).decode()
            if any(a in occupied for a in range(pc, inst.end)):
                return False
            occupied.update((a, pc) for a in range(pc, inst.end))
    except DecodeError:
        return False
    return True


def mutable_fields(program):
    """Find reachable longword stores to aligned physical work-RAM fields."""
    fields = set()
    for inst in program.all_instructions():
        if inst.op == 'MOVE' and inst.size == 4 and inst.dst and inst.dst.mode == 7 and inst.dst.reg in (0, 1):
            address = inst.dst.direct_target
            if address >= 0xe00000 and not address & 1:
                fields.add(address & 0xffff)
    return fields
