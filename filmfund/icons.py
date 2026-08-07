"""
Generate the PWA app icons with the standard library only (no Pillow).
Dark tile + red radar disc + white play triangle. Writes static/icon-192.png
and static/icon-512.png.
"""

import struct
import zlib
from pathlib import Path

BG = (15, 17, 21)       # #0f1115
RED = (225, 29, 42)     # #e11d2a
WHITE = (245, 245, 250)

STATIC = Path(__file__).parent / "static"


def _png(size: int) -> bytes:
    cx = cy = size / 2
    disc = size * 0.42
    ring = size * 0.34
    # play triangle geometry
    tw = size * 0.20
    th = size * 0.24
    tx0 = cx - tw * 0.4
    row_bytes = bytearray()
    for y in range(size):
        row_bytes.append(0)  # filter type 0
        for x in range(size):
            dx, dy = x - cx, y - cy
            d2 = dx * dx + dy * dy
            r, g, b = BG
            if d2 <= disc * disc:
                r, g, b = RED
            if ring * ring * 0.90 <= d2 <= ring * ring:   # thin white ring
                r, g, b = WHITE
            # play triangle (points right), white
            if -th / 2 <= dy <= th / 2 and tx0 <= x <= tx0 + tw:
                frac = (x - tx0) / tw
                if abs(dy) <= (th / 2) * (1 - frac):
                    r, g, b = WHITE
            row_bytes += bytes((r, g, b))

    def chunk(typ, data):
        c = typ + data
        return struct.pack(">I", len(data)) + c + struct.pack(">I", zlib.crc32(c) & 0xffffffff)

    ihdr = struct.pack(">IIBBBBB", size, size, 8, 2, 0, 0, 0)  # 8-bit RGB
    idat = zlib.compress(bytes(row_bytes), 9)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr)
            + chunk(b"IDAT", idat) + chunk(b"IEND", b""))


def generate():
    STATIC.mkdir(exist_ok=True)
    for s in (192, 512):
        (STATIC / f"icon-{s}.png").write_bytes(_png(s))
        print(f"  wrote static/icon-{s}.png")


if __name__ == "__main__":
    generate()
