#!/usr/bin/env python3
"""Deterministic, read-only STFS (LIVE/PIRS/CON) extractor.

Block mapping follows xenia-project/xenia src/xenia/vfs/devices/stfs_container_device.cc
(BlockToOffsetSTFS / BlockToHashBlockNumberSTFS). Every data block is verified
against its level-0 SHA-1 hash entry; the run fails loudly on any mismatch.

Usage:
  stfs_extract.py <package> --info
  stfs_extract.py <package> --list
  stfs_extract.py <package> --extract <outdir>
"""
import argparse, hashlib, json, os, struct, sys

BLOCK = 0x1000
PER_L0 = 0xAA
PER_L1 = 0xAA * 0xAA


class Stfs:
    def __init__(self, path):
        self.f = open(path, "rb")
        h = self.f.read(0x971A)
        self.h = h
        self.magic = h[:4].decode("ascii", "replace")
        if self.magic.rstrip() not in ("LIVE", "PIRS", "CON"):
            raise SystemExit(f"not an XContent package: magic={h[:4]!r}")
        be32 = lambda o: struct.unpack(">I", h[o:o + 4])[0]
        self.header_size = be32(0x340)
        self.content_type = be32(0x344)
        self.metadata_version = be32(0x348)
        self.content_size = struct.unpack(">Q", h[0x34C:0x354])[0]
        self.media_id = be32(0x354)
        self.version = be32(0x358)
        self.base_version = be32(0x35C)
        self.title_id = be32(0x360)
        self.platform, self.exec_type, self.disc, self.discs = h[0x364:0x368]
        self.volume_type = be32(0x3A9)
        if self.volume_type != 0:
            raise SystemExit("volume type is not STFS (SVOD not supported here)")
        vd = h[0x379:0x379 + 0x24]
        self.vd_size = vd[0]
        self.flags = vd[2]
        self.read_only = bool(self.flags & 1)
        self.table_blocks = struct.unpack("<H", vd[3:5])[0]
        self.table_block = int.from_bytes(vd[5:8], "little")
        self.top_hash = vd[8:28].hex()
        self.total_blocks = struct.unpack(">I", vd[28:32])[0]
        self.free_blocks = struct.unpack(">I", vd[32:36])[0]
        self.per_table = 1 if self.read_only else 2
        self.step0 = PER_L0 + self.per_table
        self.step1 = PER_L1 + (PER_L0 + 1) * self.per_table
        self.base = (self.header_size + BLOCK - 1) & ~(BLOCK - 1)
        s = lambda o: h[o:o + 0x80].decode("utf-16-be").split("\0")[0]
        self.display_name = s(0x411)
        self.description = s(0xD11)
        self.publisher = s(0x1611)
        self.title_name = s(0x1691)
        self._l0 = {}
        if not self.read_only:
            raise SystemExit("non-read-only STFS (dual hash tables) not supported")

    def info(self):
        v = self.version
        return {
            "magic": self.magic,
            "header_size": hex(self.header_size),
            "content_type": f"{self.content_type:08X}",
            "metadata_version": self.metadata_version,
            "content_size": self.content_size,
            "media_id": f"{self.media_id:08X}",
            "version_raw": f"{v:08X}",
            "base_version_raw": f"{self.base_version:08X}",
            "title_id": f"{self.title_id:08X}",
            "platform": self.platform,
            "executable_type": self.exec_type,
            "disc": [self.disc, self.discs],
            "volume_type": "STFS",
            "read_only_format": self.read_only,
            "file_table_block_count": self.table_blocks,
            "file_table_block_number": self.table_block,
            "top_hash_table_hash": self.top_hash,
            "total_allocated_blocks": self.total_blocks,
            "total_unallocated_blocks": self.free_blocks,
            "display_name": self.display_name,
            "description": self.description,
            "publisher": self.publisher,
            "title_name": self.title_name,
        }

    def block_offset(self, n):
        base, block = PER_L0, n
        for _ in range(3):
            block += ((n + base) // base) * self.per_table
            if n < base:
                break
            base *= PER_L0
        return self.base + (block << 12)

    def hash_block_offset(self, n):
        if n < PER_L0:
            b = 0
        else:
            b = (n // PER_L0) * self.step0
            b += ((n // PER_L1) + 1) * self.per_table
            if n >= PER_L1:
                b += self.per_table
        return self.base + (b << 12)

    def hash_entry(self, n):
        off = self.hash_block_offset(n)
        t = self._l0.get(off)
        if t is None:
            self.f.seek(off)
            t = self._l0[off] = self.f.read(BLOCK)
        e = t[(n % PER_L0) * 0x18:(n % PER_L0) * 0x18 + 0x18]
        info = struct.unpack(">I", e[20:24])[0]
        return e[:20], info >> 30, info & 0xFFFFFF

    def read_block(self, n):
        self.f.seek(self.block_offset(n))
        d = self.f.read(BLOCK)
        sha, _, nxt = self.hash_entry(n)
        if hashlib.sha1(d).digest() != sha:
            raise SystemExit(f"SHA-1 mismatch in data block {n:#x}")
        return d, nxt

    def entries(self):
        out, n = [], self.table_block
        for _ in range(self.table_blocks):
            d, nxt = self.read_block(n)
            for i in range(0, BLOCK, 0x40):
                e = d[i:i + 0x40]
                if e[0] == 0:
                    break
                fl = e[0x28]
                out.append({
                    "name": e[:fl & 0x3F].decode("latin-1"),
                    "dir": bool(fl & 0x80),
                    "contiguous": bool(fl & 0x40),
                    "valid_blocks": int.from_bytes(e[0x29:0x2C], "little"),
                    "alloc_blocks": int.from_bytes(e[0x2C:0x2F], "little"),
                    "start": int.from_bytes(e[0x2F:0x32], "little"),
                    "parent": struct.unpack(">H", e[0x32:0x34])[0],
                    "size": struct.unpack(">I", e[0x34:0x38])[0],
                })
            n = nxt
        for e in out:
            parts, p = [e["name"]], e["parent"]
            while p != 0xFFFF:
                parts.append(out[p]["name"])
                p = out[p]["parent"]
            e["path"] = "/".join(reversed(parts))
        return out

    def file_blocks(self, e):
        n, left = e["start"], e["size"]
        while left > 0:
            d, nxt = self.read_block(n)
            yield d[:min(left, BLOCK)]
            left -= BLOCK
            n = nxt


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("package")
    ap.add_argument("--info", action="store_true")
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--extract")
    ap.add_argument("--manifest", help="write path/size/sha256 TSV here")
    a = ap.parse_args()
    s = Stfs(a.package)
    if a.info:
        print(json.dumps(s.info(), indent=2))
    ents = s.entries()
    if a.list:
        for e in ents:
            print(f"{'d' if e['dir'] else '-'} {e['size']:>11} {e['path']}")
    if a.extract:
        rows = []
        for e in ents:
            dst = os.path.join(a.extract, *e["path"].split("/"))
            if e["dir"]:
                os.makedirs(dst, exist_ok=True)
                continue
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            sha = hashlib.sha256()
            with open(dst, "wb") as o:
                for chunk in s.file_blocks(e):
                    o.write(chunk)
                    sha.update(chunk)
            rows.append((e["path"], e["size"], sha.hexdigest()))
        print(f"extracted {len(rows)} files, {sum(r[1] for r in rows)} bytes; all block SHA-1 hashes verified",
              file=sys.stderr)
        if a.manifest:
            with open(a.manifest, "w", newline="\n") as m:
                for r in sorted(rows):
                    m.write(f"{r[0]}\t{r[1]}\t{r[2]}\n")


if __name__ == "__main__":
    main()
