"""MC68000 instruction-cycle estimates emitted as constants/C expressions.

EA, branch and shift costs follow the original 68000 timing tables. Multiply
and divide use upper-bound estimates; prefetch, wait states and DMA stalls are
not modeled. This is an instruction-boundary scheduler, not bus-cycle accuracy.
"""
from .decode import EA, Instruction


def ea_cycles(ea: EA | None, size: int, *, destination=False):
    if ea is None or ea.mode in (0,1): return 0
    long = 4 if size==4 else 0
    if ea.mode in (2,3): return 4+long
    if ea.mode==4: return (4 if destination else 6)+long
    if ea.mode==5: return 8+long
    if ea.mode==6: return 10+long
    return {0:8+long,1:12+long,2:8+long,3:10+long,4:4+long}[ea.reg]


def control_cycles(ea, base):
    extra={2:0,5:2,6:6}.get(ea.mode)
    if extra is None: extra={0:2,1:4,2:2,3:6}[ea.reg]
    return base+extra


def instruction_cycles(i: Instruction) -> str:
    op, size, src, dst = i.op,i.size,i.src,i.dst
    se=ea_cycles(src,size); de=ea_cycles(dst,size)
    fixed={'NOP':4,'STOP':4,'TRAP':34,'ILLEGAL':34,'LINE_A':34,'LINE_F':34,'MOVEQ':4,'SWAP':4,'EXT':4,'EXG':6,
           'TO_USP':4,'FROM_USP':4,'LINK':16,'UNLK':12,'RTE':20,'RTR':20,'RTS':16,'BSR':18}
    if op in fixed: return str(fixed[op])
    if op=='BCC':
        if i.condition==0: return '10'
        return f'(condition(c,{i.condition}) ? 10 : {12 if len(i.raw)==4 else 8})'
    if op=='DBCC':
        return f'(condition(c,{i.condition}) ? 12 : ((c->d[{dst.reg}] & 0xffff)==0 ? 14:10))'
    if op in ('JMP','JSR'): return str(control_cycles(src,8 if op=='JMP' else 16))
    if op in ('LEA','PEA'):
        extra={2:0,5:4,6:8}.get(src.mode)
        if extra is None: extra={0:4,1:8,2:4,3:8}[src.reg]
        return str((4 if op=='LEA' else 12)+extra)
    if op in ('MOVE','MOVEA'): return str(4+se+ea_cycles(dst,size,destination=True))
    if op in ('MOVEM_LOAD','MOVEM_STORE'):
        ea=src or dst
        base=12 if op=='MOVEM_LOAD' else 8
        extension={2:0,3:0,4:0,5:4,6:6}.get(ea.mode)
        if extension is None: extension={0:4,1:8,2:4,3:6}[ea.reg]
        return str(base+extension+i.value.bit_count()*(8 if size==4 else 4))
    if op in ('TO_SR','TO_CCR'): return str(12+se)
    if op=='FROM_SR': return str(6 if dst.mode==0 else 8+de)
    if op.startswith(('SR_','CCR_')): return '20'
    if op in ('ASL','ASR','LSL','LSR','ROXL','ROXR','ROL','ROR'):
        if dst.mode!=0: return str(8+de)
        count=str(src.value) if src.mode==7 else f'(c->d[{src.reg}] & 63)'
        return f'({8 if size==4 else 6} + 2*{count})'
    if op in ('MULU','MULS'): return str(70+se)
    if op in ('DIVU','DIVS'): return str((140 if op=='DIVU' else 158)+se)
    if op in ('BTST','BCHG','BCLR','BSET'):
        immediate=src.mode==7
        base={'BTST':6,'BCHG':8,'BCLR':10,'BSET':8}[op] if dst.mode==0 else (4 if op=='BTST' else 8)
        return str(base+(4 if immediate else 0)+de)
    if op=='SCC':
        return f'(condition(c,{i.condition}) ? 6:4)' if dst.mode==0 else str(8+de)
    if op in ('ADDA','SUBA','CMPA'):
        base=6 if op=='CMPA' or size==4 else 8
        if op!='CMPA' and size==4 and (src.mode in (0,1) or (src.mode==7 and src.reg==4)): base=8
        return str(base+se)
    if op in ('ADDQ','SUBQ'):
        if dst.mode==1: return '8'
        return str((8 if size==4 else 4) if dst.mode==0 else 8+de+(4 if size==4 else 0))
    if op in ('ADDX','SUBX'):
        return str((8 if size==4 else 4) if dst.mode==0 else (30 if size==4 else 18))
    if op in ('ABCD','SBCD'): return '6' if dst.mode==0 else '18'
    if op=='NBCD': return '6' if dst.mode==0 else str(8+de)
    if op in ('CMPI','ADDI','SUBI','ORI','ANDI','EORI'):
        if op=='CMPI': return str((14 if size==4 else 8) if dst.mode==0 else (12 if size==4 else 8)+de)
        return str((16 if size==4 else 8) if dst.mode==0 else (20 if size==4 else 12)+de)
    if op in ('CLR','NEG','NEGX','NOT','TST'):
        if op=='TST': return str(4+de)
        return str((6 if size==4 else 4) if dst.mode==0 else (12 if size==4 else 8)+de)
    if op in ('ADD','SUB','CMP','AND','OR','EOR'):
        if dst.mode==0:
            base=6 if size==4 else 4
            if size==4 and op!='CMP' and (src.mode in (0,1) or (src.mode==7 and src.reg==4)): base=8
            return str(base+se)
        if op=='CMP': return str((20 if size==4 else 12)) # CMPM
        return str((12 if size==4 else 8)+de)
    raise ValueError(f'no cycle estimate for {op}')
