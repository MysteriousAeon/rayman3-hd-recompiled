#!/usr/bin/env python3
"""XEX2 header characterization (read-only).

Prints security info, optional headers, import libraries (with per-record
ordinals), static libraries, TLS, execution info and page descriptors.

No key material is embedded here. With --image-out the XEX2 retail key is read
at runtime from a local xenia checkout (--xenia), the basefile is decrypted, and
for "basic" compression the flat PE image is written. LZX ("normal") images are
written still-compressed with --lzx-out for an external decoder (libmspack).

Field layout follows xenia src/xenia/kernel/util/xex2_info.h.
"""
import argparse, hashlib, json, re, struct, subprocess, sys

HDR = {
    0x000002FF: "RESOURCE_INFO", 0x000003FF: "FILE_FORMAT_INFO", 0x000005FF: "DELTA_PATCH_DESCRIPTOR",
    0x00000405: "BASE_REFERENCE", 0x000080FF: "BOUNDING_PATH", 0x00008105: "DEVICE_ID",
    0x00010001: "ORIGINAL_BASE_ADDRESS", 0x00010100: "ENTRY_POINT", 0x00010201: "IMAGE_BASE_ADDRESS",
    0x000103FF: "IMPORT_LIBRARIES", 0x00018002: "CHECKSUM_TIMESTAMP", 0x00018102: "ENABLED_FOR_CALLCAP",
    0x00018200: "ENABLED_FOR_FASTCAP", 0x000183FF: "ORIGINAL_PE_NAME", 0x000200FF: "STATIC_LIBRARIES",
    0x00020104: "TLS_INFO", 0x00020200: "DEFAULT_STACK_SIZE", 0x00020301: "DEFAULT_FILESYSTEM_CACHE_SIZE",
    0x00020401: "DEFAULT_HEAP_SIZE", 0x00028002: "PAGE_HEAP_SIZE_AND_FLAGS", 0x00030000: "SYSTEM_FLAGS",
    0x00040006: "EXECUTION_INFO", 0x00040201: "TITLE_WORKSPACE_SIZE", 0x00040310: "GAME_RATINGS",
    0x00040404: "LAN_KEY", 0x000405FF: "XBOX360_LOGO", 0x000406FF: "MULTIDISC_MEDIA_IDS",
    0x000407FF: "ALTERNATE_TITLE_IDS", 0x00040801: "ADDITIONAL_TITLE_MEMORY", 0x00E10402: "EXPORTS_BY_NAME",
}
MODULE_FLAGS = ["TITLE", "EXPORTS_TO_TITLE", "SYSTEM_DEBUGGER", "DLL_MODULE", "MODULE_PATCH", "PATCH_FULL",
                "PATCH_DELTA", "USER_MODE"]


def u32(b, o):
    return struct.unpack_from(">I", b, o)[0]


def u16(b, o):
    return struct.unpack_from(">H", b, o)[0]


def parse(path):
    d = open(path, "rb").read()
    if d[:4] != b"XEX2":
        raise SystemExit(f"not XEX2: {d[:4]!r}")
    r = {"file_size": len(d), "sha256": hashlib.sha256(d).hexdigest(), "magic": "XEX2"}
    mf = u32(d, 4)
    r["module_flags"] = f"{mf:#010x} " + "|".join(n for i, n in enumerate(MODULE_FLAGS) if mf >> i & 1)
    r["pe_data_offset"] = hex(u32(d, 8))
    sec = u32(d, 0x10)
    n = u32(d, 0x14)
    opt = {}
    for i in range(n):
        k, v = u32(d, 0x18 + i * 8), u32(d, 0x1C + i * 8)
        opt[k] = v
    r["optional_headers"] = [f"{k:#010x} {HDR.get(k, '?')} = {v:#x}" for k, v in opt.items()]

    def blob(k):
        if k not in opt:
            return None
        o = opt[k]
        if k & 0xFF == 0xFF:
            return d[o:o + u32(d, o)]
        return d[o:o + (k & 0xFF) * 4]

    # security info
    s = {
        "header_size": hex(u32(d, sec)), "image_size": hex(u32(d, sec + 4)),
        "image_flags": hex(u32(d, sec + 0x10C)), "load_address": hex(u32(d, sec + 0x110)),
        "import_table_count": u32(d, sec + 0x128), "export_table": hex(u32(d, sec + 0x160)),
        "game_regions": hex(u32(d, sec + 0x178)), "allowed_media_types": hex(u32(d, sec + 0x17C)),
    }
    npages = u32(d, sec + 0x180)
    page_size = 0x1000 if u32(d, sec + 0x10C) & 0x10000000 else 0x10000
    s["page_size"] = hex(page_size)
    pages, addr = [], u32(d, sec + 0x110)
    kinds = {1: "CODE", 2: "DATA", 3: "RODATA"}
    for i in range(npages):
        v = u32(d, sec + 0x184 + i * 24)
        cnt, kind = v >> 4, v & 0xF
        pages.append({"start": f"{addr:#010x}", "end": f"{addr + cnt * page_size:#010x}",
                      "pages": cnt, "type": kinds.get(kind, str(kind))})
        addr += cnt * page_size
    s["page_descriptors"] = pages
    r["security_info"] = s
    aes_key = d[sec + 0x150:sec + 0x160]

    for k, name in ((0x10100, "entry_point"), (0x10201, "image_base"), (0x10001, "original_base"),
                    (0x20200, "default_stack_size"), (0x20401, "default_heap_size"),
                    (0x20301, "default_fs_cache_size"), (0x30000, "system_flags"),
                    (0x40201, "title_workspace_size"), (0x40801, "additional_title_memory")):
        if k in opt:
            r[name] = hex(opt[k])
    b = blob(0x183FF)
    if b:
        r["original_pe_name"] = b[4:].split(b"\0")[0].decode("latin-1")
    b = blob(0x80FF)
    if b:
        r["bounding_path"] = b[4:].split(b"\0")[0].decode("latin-1")
    b = blob(0x18002)
    if b:
        r["checksum"], r["timestamp"] = hex(u32(b, 0)), u32(b, 4)
    b = blob(0x20104)
    if b:
        r["tls"] = {"slot_count": u32(b, 0), "raw_data_address": hex(u32(b, 4)),
                    "data_size": hex(u32(b, 8)), "raw_data_size": hex(u32(b, 12))}
    b = blob(0x40006)
    if b:
        v, bv = u32(b, 4), u32(b, 8)
        ver = lambda x: f"{x >> 28}.{x >> 24 & 0xF}.{x >> 8 & 0xFFFF}.{x & 0xFF}"
        r["execution_info"] = {"media_id": f"{u32(b, 0):08X}", "version": f"{v:08X} ({ver(v)})",
                               "base_version": f"{bv:08X} ({ver(bv)})", "title_id": f"{u32(b, 12):08X}",
                               "platform": b[16], "executable_table": b[17], "disc_number": b[18],
                               "disc_count": b[19], "savegame_id": f"{u32(b, 20):08X}"}
    b = blob(0x2FF)
    if b:
        r["resources"] = [{"name": b[o:o + 8].rstrip(b"\0").decode("latin-1"), "address": hex(u32(b, o + 8)),
                           "size": hex(u32(b, o + 12))} for o in range(4, len(b), 16)]
    b = blob(0x200FF)
    if b:
        libs = []
        for o in range(4, len(b), 16):
            nm = b[o:o + 8].rstrip(b"\0").decode("latin-1")
            libs.append(f"{nm} {u16(b, o + 8)}.{u16(b, o + 10)}.{u16(b, o + 12)}.{u16(b, o + 14) >> 8}"
                        f" approval={u16(b, o + 14) & 0xFF}")
        r["static_libraries"] = libs
    b = blob(0x3FF)
    comp = enc = None
    if b:
        enc, comp = u16(b, 4), u16(b, 6)
        ff = {"encryption": {0: "none", 1: "normal(AES)"}.get(enc, enc),
              "compression": {0: "none", 1: "basic", 2: "normal(LZX)", 3: "delta"}.get(comp, comp)}
        if comp == 1:
            blocks = [(u32(b, o), u32(b, o + 4)) for o in range(8, len(b), 8)]
            ff["basic_blocks"] = len(blocks)
            ff["basic_data_total"] = hex(sum(x for x, _ in blocks))
            ff["basic_zero_total"] = hex(sum(z for _, z in blocks))
            r["_blocks"] = blocks
        elif comp == 2:
            ff["lzx_window_size"] = hex(u32(b, 8))
            r["_lzx_first"] = u32(b, 12)
        r["file_format"] = ff
    b = blob(0x103FF)
    if b:
        strsz, nlib = u32(b, 4), u32(b, 8)
        names = b[12:12 + strsz].split(b"\0")
        names = [x.decode("latin-1") for x in names if x]
        o, libs = 12 + strsz, []
        for _ in range(nlib):
            sz = u32(b, o)
            ver_, vmin = u32(b, o + 0x1C), u32(b, o + 0x20)
            vs = lambda x: f"{x >> 28}.{x >> 24 & 0xF}.{x >> 8 & 0xFFFF}.{x & 0xFF}"
            name_idx, cnt = u16(b, o + 0x24) & 0xFF, u16(b, o + 0x26)
            recs = [u32(b, o + 0x28 + i * 4) for i in range(cnt)]
            libs.append({"name": names[name_idx], "version": vs(ver_), "version_min": vs(vmin),
                         "record_count": cnt, "records": [f"{x:#010x}" for x in recs]})
            o += sz
        r["import_libraries"] = libs
    r["_meta"] = {"enc": enc, "comp": comp, "pe_off": u32(d, 8), "aes_key": aes_key, "data": d}
    return r


def xenia_retail_key(xenia):
    src = subprocess.run(["git", "-C", xenia, "show", "HEAD:src/xenia/cpu/xex_module.cc"],
                         capture_output=True, text=True, check=True).stdout
    m = re.search(r"xe_xex2_retail_key\[16\]\s*=\s*\{([^}]*)\}", src)
    return bytes(int(x, 16) for x in re.findall(r"0x[0-9A-Fa-f]{2}", m.group(1)))


def basefile(r, xenia):
    m = r["_meta"]
    body = m["data"][m["pe_off"]:]
    if m["enc"] == 1:
        from Crypto.Cipher import AES
        sess = AES.new(xenia_retail_key(xenia), AES.MODE_ECB).decrypt(m["aes_key"])
        body = AES.new(sess, AES.MODE_CBC, iv=bytes(16)).decrypt(body[:len(body) & ~15])
    return body


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("xex")
    ap.add_argument("--xenia", default="external/xenia")
    ap.add_argument("--image-out", help="write flat memory image (basic/uncompressed only)")
    ap.add_argument("--lzx-out", help="write concatenated LZX stream (normal compression)")
    a = ap.parse_args()
    r = parse(a.xex)
    pub = {k: v for k, v in r.items() if not k.startswith("_")}
    print(json.dumps(pub, indent=1))
    comp = r["_meta"]["comp"]
    if a.image_out or a.lzx_out:
        body = basefile(r, a.xenia)
        if comp == 1 and a.image_out:
            out, p = bytearray(), 0
            for dsz, zsz in r["_blocks"]:
                out += body[p:p + dsz] + bytes(zsz)
                p += dsz
            open(a.image_out, "wb").write(out)
            print(f"image: {len(out):#x} bytes sha256={hashlib.sha256(out).hexdigest()} MZ={bytes(out[:2])!r}",
                  file=sys.stderr)
        elif comp == 0 and a.image_out:
            open(a.image_out, "wb").write(body)
        elif comp == 2 and a.lzx_out:
            out, p, bsz = bytearray(), 0, r["_lzx_first"]
            while bsz:
                blk = body[p:p + bsz]
                nxt = u32(blk, 0)
                q = 24
                while True:
                    csz = u16(blk, q)
                    q += 2
                    if not csz:
                        break
                    out += blk[q:q + csz]
                    q += csz
                p += bsz
                bsz = nxt
            open(a.lzx_out, "wb").write(out)
            print(f"lzx stream: {len(out):#x} bytes", file=sys.stderr)
        else:
            raise SystemExit("requested output not applicable to this compression type")


if __name__ == "__main__":
    main()
