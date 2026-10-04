"""Generate an original synthetic ROM; no game assets or SDK needed."""
from pathlib import Path
import argparse


def make_demo():
    rom = bytearray(0x400)
    rom[:4] = (0x00FFFF00).to_bytes(4, "big")
    rom[4:8] = (0x200).to_bytes(4, "big")
    rom[0x100:0x110] = b"SEGA GENESIS    "
    rom[0x120:0x150] = b"STATIC RECOMPILER SYNTHETIC DEMO".ljust(48)
    rom[0x1A0:0x1A4] = (0).to_bytes(4, "big")
    rom[0x1A4:0x1A8] = (len(rom)-1).to_bytes(4, "big")
    rom[0x1A8:0x1AC] = (0xFF0000).to_bytes(4, "big")
    rom[0x1AC:0x1B0] = (0xFFFFFF).to_bytes(4, "big")
    words = [
        0x7000,                 # 200: MOVEQ #0,D0
        0x7204,                 # 202: MOVEQ #4,D1
        0x5280,                 # 204: ADDQ.L #1,D0
        0x51C9, 0xFFFC,         # 206: DBF D1,$204 => five additions
        0x6100, 0x0014,         # 20a: BSR.W $220
        0x23C0, 0x00FF, 0x0000, # 20e: MOVE.L D0,$ff0000
        0x0C80, 0x0000, 0x0008, # 214: CMPI.L #8,D0
        0x4E72, 0x2700,         # 21a: STOP #$2700
        0x4E71,                 # 21e: padding
        0x5680,                 # 220: ADDQ.L #3,D0
        0x4E75,                 # 222: RTS
    ]
    code = b"".join(word.to_bytes(2, "big") for word in words)
    rom[0x200:0x200+len(code)] = code
    checksum = sum(int.from_bytes(rom[i:i+2], "big") for i in range(0x200,len(rom),2)) & 0xFFFF
    rom[0x18E:0x190] = checksum.to_bytes(2, "big")
    return bytes(rom)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    args.output.write_bytes(make_demo())
    print(f"wrote synthetic demo to {args.output}")
