"""Connect ROM function stores and indirect calls through resolved RAM slots.

Object-relative fields participate only when their actual physical addresses can
be resolved; a shared field displacement is never sufficient evidence.
"""
from .decode import EA
from .discovery import LIMIT, ValueSlice, finite, valid_roots


def ram_slots(values):
    if not values or any(a & 1 or a < 0xe00000 or (a & 0xffff) > 0xfffc for a in values):
        return ()
    return sorted({0xff0000 | (a & 0xffff) for a in values})


class RamSlice(ValueSlice):
    def __init__(self, program, instructions, preceding, joins, patches):
        super().__init__(program, preceding, joins, allow_ram=True)
        self.instructions, self.patches = instructions, patches

    def address(self, ea, before, depth=0):
        inst = self.instructions.get(before)
        if (inst and inst.op in ('LEA', 'MOVE') and inst.src == ea
                and ea and (ea.mode, ea.reg) == (7, 1)):
            values = self.patches.get((before+2) & 0xffff)
            if values:
                # A live source can retain its original template value or one
                # of the known constants written by reachable native code.
                return finite({ea.value & 0xffffff, *(v & 0xffffff for v in values)})
        return super().address(ea, before, depth)


def memory_callbacks(program):
    rom_instructions = {pc: i for pc, i in program.instructions.items() if pc < len(program.rom)}
    preceding = {i.end: i for i in rom_instructions.values()}
    joins = {*program.entries, *(i.target for i in rom_instructions.values() if i.target is not None)}
    stores, patches = {}, {}
    occupied = {a: i.pc for i in rom_instructions.values() for a in range(i.pc, i.end)}
    for inst in rom_instructions.values():
        if inst.op != 'MOVE' or inst.size != 4 or inst.dst.mode in (0, 1):
            continue
        sliced = ValueSlice(program, preceding, joins)
        slots = ram_slots(sliced.address(inst.dst, inst.pc))
        if not slots:
            continue
        values = sliced.operand(inst.src, inst.pc, 4, 0)
        if values:
            for slot in slots:
                patches.setdefault(slot & 0xffff, set()).update(values)
        targets = {v & 0xffffff for v in values} if values else set()
        if (not targets or len(targets)*len(slots) > LIMIT
                or any(t & 1 or not 8 <= t < len(program.rom) for t in targets)
                or not valid_roots(program, targets, occupied)):
            continue
        for slot in slots:
            stores.setdefault(slot, set()).update((inst.pc, target) for target in targets)
    for inst in program.all_instructions():
        if (inst.pc >= 0xe00000 and inst.op == 'MOVE' and inst.size == 4 and inst.src
                and (inst.src.mode, inst.src.reg) == (7, 4)):
            for slot in ram_slots({inst.dst.direct_target} if inst.dst.direct_target is not None else None):
                patches.setdefault(slot & 0xffff, set()).add(inst.src.value)

    found = {}
    # Each image has its own register slice and instruction boundaries. Shared
    # instructions still occur in each image's view, even when emission dedupes.
    views = [(rom_instructions, preceding, joins, False)]
    for image, instructions in program.ram_image_instructions.items():
        pre = {i.end: i for i in instructions.values()}
        boundaries = {image.address, *(i.target for i in instructions.values() if i.target is not None)}
        views.append((instructions, pre, boundaries, True))
    for instructions, pre, boundaries, ram in views:
        for jump in instructions.values():
            if jump.op not in ('JSR', 'JMP') or jump.target is not None or jump.src.mode != 2:
                continue
            reg, before, slots = EA(1, jump.src.reg), jump.pc, ()
            for _ in range(8):
                if before in boundaries:
                    break
                inst = pre.get(before)
                if inst is None or inst.op in ('JSR', 'BSR', 'JMP', 'RTS', 'RTE', 'RTR', 'TRAP', 'STOP', 'DBCC'):
                    break
                if inst.op == 'BCC' and inst.condition == 0:
                    break
                before = inst.pc
                if inst.dst == reg and inst.op not in ('CMPA', 'TST'):
                    if inst.op not in ('MOVE', 'MOVEA') or inst.size != 4:
                        break
                    if inst.src.mode in (0, 1):
                        reg = inst.src
                        continue
                    sliced = RamSlice(program, instructions, pre, boundaries, patches) if ram else ValueSlice(program, pre, boundaries)
                    slots = ram_slots(sliced.address(inst.src, inst.pc))
                    break
                if reg.mode == 1 and any(ea and ea.mode in (3, 4) and ea.reg == reg.reg for ea in (inst.src, inst.dst)):
                    break
                if inst.op == 'MOVEM_LOAD' and inst.value & (1 << (reg.reg + 8*reg.mode)):
                    break
                if inst.op == 'EXG' and reg in (inst.src, inst.dst):
                    break
            matches = {s: stores[s] for s in slots if s in stores}
            if not matches:
                continue
            record = found.setdefault(jump.pc, {'slots': [], 'stores': [], 'targets': []})
            record['slots'] = sorted({*record['slots'], *matches})
            record['stores'] = sorted({*record['stores'], *(pc for pairs in matches.values() for pc, _ in pairs)})
            record['targets'] = sorted({*record['targets'], *(t for pairs in matches.values() for _, t in pairs)})
    return found
