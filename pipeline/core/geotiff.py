"""Lecteur minimal de GeoTIFF tuilé (bibliothèque standard) : TIFF ou BigTIFF, 8 bits, une bande, tuiles
compressées en LZW (5), Deflate (8, 32946) ou non compressées (1), avec leurs aperçus (overviews) dans le même
fichier. C'est ce qu'il faut pour la couverture du sol du Canada de RNCan ; le reste du format n'est pas géré.

    tif = TiledTiff(path)
    lvl = tif.levels[3]              # aperçu au 1/8 (240 m pour une image à 30 m)
    tile = tif.read_tile(lvl, tx, ty)  # bytes, tile_w × tile_h valeurs
"""

from __future__ import annotations

import struct
import zlib
from dataclasses import dataclass

_TYPES = {1: "B", 2: "s", 3: "H", 4: "I", 5: "II", 6: "b", 7: "B", 8: "h", 9: "i", 11: "f", 12: "d", 16: "Q", 17: "q", 18: "Q"}
_SIZES = {1: 1, 2: 1, 3: 2, 4: 4, 5: 8, 6: 1, 7: 1, 8: 2, 9: 4, 10: 8, 11: 4, 12: 8, 16: 8, 17: 8, 18: 8}


@dataclass
class Level:
    width: int
    height: int
    tile_w: int
    tile_h: int
    offsets: tuple
    counts: tuple
    compression: int
    predictor: int
    bits: int
    samples: int

    @property
    def tiles_across(self) -> int:
        return (self.width + self.tile_w - 1) // self.tile_w

    @property
    def tiles_down(self) -> int:
        return (self.height + self.tile_h - 1) // self.tile_h


def lzw_decode(data: bytes) -> bytes:
    """TIFF LZW (MSB first, codes 9–12 bits, « early change »)."""
    out = bytearray()
    table = [bytes([i]) for i in range(256)] + [b"", b""]
    width, bitbuf, nbits, prev = 9, 0, 0, None
    append = table.append
    for byte in data:
        bitbuf = (bitbuf << 8) | byte
        nbits += 8
        while nbits >= width:
            nbits -= width
            code = (bitbuf >> nbits) & ((1 << width) - 1)
            if code == 256:  # clear
                del table[258:]
                width, prev = 9, None
                continue
            if code == 257:  # end of information
                return bytes(out)
            if prev is None:
                entry = table[code]
            elif code < len(table):
                entry = table[code]
                append(prev + entry[:1])
            else:
                entry = prev + prev[:1]
                append(entry)
            out += entry
            prev = entry
            n = len(table)
            if n >= 511 and width == 9 or n >= 1023 and width == 10 or n >= 2047 and width == 11:
                width += 1
        bitbuf &= (1 << nbits) - 1
    return bytes(out)


class TiledTiff:
    def __init__(self, path):
        self.path = path
        self.f = open(path, "rb")
        head = self.f.read(16)
        self.e = e = "<" if head[:2] == b"II" else ">"
        magic = struct.unpack(e + "H", head[2:4])[0]
        self.big = magic == 43
        if magic not in (42, 43):
            raise ValueError(f"{path} n'est pas un TIFF")
        off = struct.unpack(e + "Q", head[8:16])[0] if self.big else struct.unpack(e + "I", head[4:8])[0]
        self.ifds = []
        while off:
            tags, off = self._ifd(off)
            self.ifds.append(tags)
        self.levels = [self._level(t) for t in self.ifds if 324 in t or 273 in t]
        t0 = self.ifds[0]
        self.pixel_scale = t0.get(33550)  # (sx, sy, sz)
        self.tiepoint = t0.get(33922)  # (i, j, k, x, y, z)
        self.palette = t0.get(320)

    def _read(self, off, n):
        self.f.seek(off)
        return self.f.read(n)

    def _ifd(self, off):
        e = self.e
        if self.big:
            n = struct.unpack(e + "Q", self._read(off, 8))[0]
            raw = self._read(off + 8, n * 20 + 8)
            esz, cnt_fmt, ptr_fmt = 20, "Q", "Q"
        else:
            n = struct.unpack(e + "H", self._read(off, 2))[0]
            raw = self._read(off + 2, n * 12 + 4)
            esz, cnt_fmt, ptr_fmt = 12, "I", "I"
        inline = 8 if self.big else 4
        tags = {}
        for k in range(n):
            p = k * esz
            tag, typ = struct.unpack(e + "HH", raw[p:p + 4])
            cnt = struct.unpack(e + cnt_fmt, raw[p + 4:p + 4 + struct.calcsize(cnt_fmt)])[0]
            vo = raw[p + 4 + struct.calcsize(cnt_fmt):p + esz]
            size = _SIZES.get(typ, 1) * cnt
            data = vo[:size] if size <= inline else self._read(struct.unpack(e + ptr_fmt, vo)[0], size)
            fmt = _TYPES.get(typ)
            if fmt is None:
                continue
            if typ == 2:
                tags[tag] = data.rstrip(b"\0").decode("latin-1")
            else:
                tags[tag] = struct.unpack(f"{e}{cnt * len(fmt)}{fmt[0]}", data)
        nxt = struct.unpack(e + ptr_fmt, raw[n * esz:n * esz + struct.calcsize(ptr_fmt)])[0]
        return tags, nxt

    def _level(self, t) -> Level:
        if 324 not in t:
            raise ValueError("TIFF en bandes (strips) non géré : il faut des tuiles")
        lvl = Level(width=t[256][0], height=t[257][0], tile_w=t[322][0], tile_h=t[323][0], offsets=t[324],
                    counts=t[325], compression=t.get(259, (1,))[0], predictor=t.get(317, (1,))[0],
                    bits=t.get(258, (8,))[0], samples=t.get(277, (1,))[0])
        if lvl.bits != 8 or lvl.samples != 1 or lvl.predictor != 1:
            raise ValueError("seulement une bande de 8 bits sans prédicteur")
        if lvl.compression not in (1, 5, 8, 32946):
            raise ValueError(f"compression {lvl.compression} non gérée")
        return lvl

    def read_tile(self, lvl: Level, tx: int, ty: int) -> bytes:
        k = ty * lvl.tiles_across + tx
        n = lvl.tile_w * lvl.tile_h
        if not lvl.counts[k]:
            return bytes(n)
        raw = self._read(lvl.offsets[k], lvl.counts[k])
        if lvl.compression == 5:
            data = lzw_decode(raw)
        elif lvl.compression in (8, 32946):
            data = zlib.decompress(raw)
        else:
            data = raw
        return data[:n].ljust(n, b"\0")

    def close(self):
        self.f.close()
