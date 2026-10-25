"""Decode the private per-draw geometry dumps of one menu frame (m5_draw_<n>.bin written by
the M5 runtime observer) into metadata: selected indexed vertices, covered screen
rectangle, UV rectangle and texture fetch constant. Vertex layout for VS 9814110B...:
36-byte stride, big-endian floats: position xyz (+0), w (+12), colour (+16), uv (+20).
The layout is checked per draw (finite positions/uvs); other shaders are listed only.

usage: m5_menu_draws.py RUN_DIR OUTPUT_JSON
"""
import json, math, struct, sys
from pathlib import Path

run, output = Path(sys.argv[1]), Path(sys.argv[2])
rows = []
for path in sorted(run.glob('m5_draw_*.bin'), key=lambda p: int(p.stem.split('_')[2])):
    b = path.read_bytes(); h = struct.unpack('<20I', b[:80])
    assert h[0] == 0x4D354452
    prim, count, indexed, fmt, endian, ib_base, base_offset, vb_base, vb_bytes, ib_bytes, vs = h[1:12]
    fetch = h[12:18]; ps = h[19]
    indices = list(range(count))
    if indexed:
        raw = b[80:80 + ib_bytes]; width = 4 if fmt else 2
        # Xenos endian: 0 none, 1 8-in-16, 2 8-in-32, 3 16-in-32; guest memory bytes are raw here.
        code = {(2, 1): '>H', (2, 0): '<H', (4, 2): '>I', (4, 0): '<I'}.get((width, endian))
        indices = [x[0] for x in struct.iter_unpack(code, raw)] if code else None
    trailer = struct.unpack('<1248I', b[-4992:]); b = b[:-4992]  # regs 2000..23FF, 4000..403F, 4400..443F, 4800..485F
    vb = b[80 + ib_bytes:]
    reg = lambda index: trailer[index - 0x2000]
    def floats(offset, count): return [round(struct.unpack('<f', struct.pack('<I', x))[0], 4) for x in trailer[offset:offset + count]]
    state = dict(surface_info=reg(0x2000), color_info=reg(0x2001), screen_scissor=[reg(0x200E), reg(0x200F)], window_offset=reg(0x2080),
                 window_scissor=[reg(0x2081), reg(0x2082)], color_mask=reg(0x2104), stencil_ref=reg(0x210D), alpha_ref=floats(0x10E, 1)[0],
                 viewport=floats(0x10F, 6), depth_control=reg(0x2200), blend_control0=reg(0x2201), color_control=reg(0x2202),
                 clip_cntl=reg(0x2204), su_sc_mode=reg(0x2205), vte_cntl=reg(0x2206), mode_control=reg(0x2208))
    state = {k: (f'{v:08X}' if isinstance(v, int) else [f'{x:08X}' if isinstance(x, int) else x for x in v] if isinstance(v, list) else v) for k, v in state.items()}
    state.update(vs_constants=floats(0x400, 32), ps_constants=floats(0x440, 16),
                 fetch=[' '.join(f'{x:08X}' for x in trailer[0x480 + i * 6:0x486 + i * 6]) for i in range(4)])
    row = dict(draw=int(path.stem.split('_')[2]), primitive=prim, index_count=count, indexed=bool(indexed), index_format=fmt,
               index_endian=endian, index_base=f'{ib_base:08X}', vgt_indx_offset=base_offset, vertex_base=f'{vb_base:08X}',
               vertex_bytes=vb_bytes, vs=f'{vs:08X}', ps=f'{ps:08X}', fetch0=[f'{x:08X}' for x in fetch],
               texture=dict(base=f'{(fetch[1] & 0xFFFFF000):08X}', width=(fetch[2] & 0x1FFF) + 1, height=((fetch[2] >> 13) & 0x1FFF) + 1,
                            type=fetch[0] & 3), state=state)
    if vs == 0x9814110B and indices is not None:
        verts = []
        for i in indices:
            o = (i + base_offset) * 36
            if o + 36 > len(vb): verts = None; break
            x, y, z, w = struct.unpack_from('>4f', vb, o); u, v = struct.unpack_from('>2f', vb, o + 20)
            verts.append((x, y, z, w, u, v, vb[o + 16:o + 20].hex()))
        if verts and all(math.isfinite(c) for q in verts for c in q[:6]):
            xs, ys, us, vs_ = ([q[i] for q in verts] for i in (0, 1, 4, 5))
            row.update(max_index=max(indices), x=[round(min(xs), 4), round(max(xs), 4)], y=[round(min(ys), 4), round(max(ys), 4)],
                       u=[round(min(us), 4), round(max(us), 4)], v=[round(min(vs_), 4), round(max(vs_), 4)],
                       w=sorted({round(q[3], 3) for q in verts}), colours=sorted({q[6] for q in verts}),
                       area=round((max(xs) - min(xs)) * (max(ys) - min(ys)), 5))
        else:
            row['decode'] = 'out_of_range_or_nonfinite'
    rows.append(row)
output.parent.mkdir(parents=True, exist_ok=True)
output.write_text(json.dumps(rows, indent=1) + '\n')
big = [r for r in rows if r.get('area', 0) > 0.5]
print(json.dumps(dict(draws=len(rows), decoded=sum('area' in r for r in rows), large_area=len(big))))
