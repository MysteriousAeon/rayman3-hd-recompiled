"""G6-P88 (D-337 / E-574): offline corrective model of 3:2 scaled-resolve addressing on the SDK's own layout.

G6-P87 found that the SDK's scaled shaders (Xenia 0b2ffa314) do not use the group-linear layout E-572 modelled; they
use one-row Nx1 sub-units (`XeTextureScaledTiledOffset`, N = 8 / 8 / 4 / 2 / 1 blocks at 1 / 2 / 4 / 8 / 16 bytes per
block). This model is an exact integer port of that helper (and of `XeTextureTiledOffset2D`) and asks:

  S1  control: at integer scales 1..3 the SDK helper is a bijection over the host surface, its host bytes are the
      guest units' bytes x area (range-linear) and every host pixel belongs to the guest unit of guest pixel
      floor(h / s) (exact invalidation);
  S2  the SDK helper cannot express 3:2: a one-row guest unit owns 1.5 host rows. The best direct generalisation
      (floor division by 3/2) is shown to collide or to mis-assign ownership;
  S3  corrective model R: a guest group of 2 x 2 SDK units (2N x 2 blocks) is one aligned contiguous run of 4 unit
      sizes in guest memory, and maps to 3 x 3 host Nx1 sub-units of the SDK's own shape, column-major, at 9/4 of the
      group's guest address. R is checked for contiguity, bijection, range linearity and exact invalidation per
      bytes-per-block on the title's surfaces;
  S4  the companion helper (`...RightSubUnitOffsetInConsecutivePair`) under R: the offset of the next host sub-unit
      to the right takes three values per sub-unit column, derived and checked against R directly.
  S6  (G6-P92) the dispatch of the 3:2 fast 32bpp copy variant, simulated thread by thread: coverage of the host
      rectangle (nothing missing, nothing extra), collision freedom, ownership and rectangle-group membership against
      the guest tiled addresses only, allocation bounds, the bounded 3:2 load round trip, the observed adjacent
      destinations, with negative controls (SDK 8-row groups, floor group count, a crossing write, a disagreeing load
      mapping, an odd width admitted, a rectangle beyond its allocation).

Usage: g6p88_sdk_scaled_model.py selftest | report [--json OUT] | s6 [--json OUT]. Pure arithmetic; reads no title
data.
"""
import argparse
import json
import sys
from fractions import Fraction
from pathlib import Path

TILE = 32


def align(v, a):
    return (v + a - 1) // a * a


def tiled2d(x, y, pitch, bpb_log2):
    """XeTextureTiledOffset2D (0b2ffa314 texture_address.xesli:15) == SDK texture_util::GetTiledOffset2D."""
    pitch = align(pitch, TILE)
    macro = ((x >> 5) + (y >> 5) * (pitch >> 5)) << (bpb_log2 + 7)
    micro = ((x & 7) + ((y & 0xE) << 2)) << bpb_log2
    offset = macro + ((micro & ~0xF) << 1) + (micro & 0xF) + ((y & 1) << 4)
    return (((offset & ~0x1FF) << 3) + ((y & 16) << 7) + ((offset & 0x1C0) << 2)
            + (((((y & 8) >> 2) + (x >> 3)) & 3) << 6) + (offset & 0x3F))


def unit_log2(bpb_log2):
    """XeTextureTiledConsecutiveBlocksLog2."""
    return min(4 - bpb_log2, 3)


def odd_consecutive_offset(bpb_log2):
    """XeTextureTiledOddConsecutiveBlocksOffset."""
    return 32 if bpb_log2 >= 2 else 64


def sdk_scaled_offset(hx, hy, pitch, bpb_log2, sx, sy):
    """XeTextureScaledTiledOffset (2D), integer scale (0b2ffa314 texture_address.xesli:92)."""
    n_log2 = unit_log2(bpb_log2)
    x_sub = hx >> n_log2
    ux, uy = x_sub // sx, hy // sy
    unit_addr = tiled2d(ux << n_log2, uy, pitch, bpb_log2)
    sub_x, sub_y = x_sub - ux * sx, hy - uy * sy
    return unit_addr * (sx * sy) + ((((sub_x * sy + sub_y) << n_log2) + (hx & ((1 << n_log2) - 1))) << bpb_log2)


def unit_bytes(bpb_log2):
    return (1 << unit_log2(bpb_log2)) << bpb_log2


def check_integer(width, height, pitch, bpb_log2, s):
    """S1. Returns (collisions, nonlinear, ownership_errors)."""
    ub = unit_bytes(bpb_log2)
    bpb = 1 << bpb_log2
    n = 1 << unit_log2(bpb_log2)
    seen, own = set(), 0
    for hy in range(height * s):
        for hx in range(width * s):
            a = sdk_scaled_offset(hx, hy, pitch, bpb_log2, s, s)
            if a in seen:
                return 1, True, 0
            seen.add(a)
            gx, gy = hx // s, hy // s
            if a // (ub * s * s) != tiled2d(gx, gy, pitch, bpb_log2) // ub:
                own += 1
    expected = set()
    for gy in range(height):
        for gx in range(0, width, n):
            u = tiled2d(gx, gy, pitch, bpb_log2) // ub
            expected.update(range(u * ub * s * s, (u + 1) * ub * s * s, bpb))
    return 0, seen != expected, own


def check_direct_generalisation(width, height, pitch, bpb_log2):
    """S2: XeTextureScaledTiledOffset with scale 3/2 done by floor division (the only direct reading): unit =
    floor(sub * 2/3), sub-unit index from the remainder in thirds, base x 9/4. Counts collisions, ownership
    errors, non-integer bases and host bytes outside the unit's own [base, base + 9/4 x unit) range."""
    n_log2 = unit_log2(bpb_log2)
    bpb = 1 << bpb_log2
    ub = unit_bytes(bpb_log2)
    seen, coll, own, nonint, outside = set(), 0, 0, 0, 0
    for hy in range(height * 3 // 2):
        for hx in range(width * 3 // 2):
            x_sub = hx >> n_log2
            ux, uy = (x_sub * 2) // 3, (hy * 2) // 3
            base = Fraction(tiled2d(ux << n_log2, uy, pitch, bpb_log2) * 9, 4)
            nonint += base.denominator != 1
            sub_x, sub_y = x_sub - (ux * 3) // 2, hy - (uy * 3) // 2   # 0..1 per axis: 1.5 sub-units per unit
            a = int(base) + ((((sub_x * 2 + sub_y) << n_log2) + (hx & ((1 << n_log2) - 1))) << bpb_log2)
            coll += a in seen
            seen.add(a)
            outside += not (base <= a < base + Fraction(ub * 9, 4))   # must stay in the unit's own 9/4 range
            if tiled2d((hx * 2) // 3, (hy * 2) // 3, pitch, bpb_log2) // ub != tiled2d(ux << n_log2, uy, pitch, bpb_log2) // ub:
                own += 1
    return coll, own, nonint, outside


def group_contiguous(width, height, pitch, bpb_log2):
    """S3a: every 2N x 2 block group at even unit coordinates is one aligned run of 4 x unit bytes."""
    n = 1 << unit_log2(bpb_log2)
    ub = unit_bytes(bpb_log2)
    bad = 0
    for gy in range(0, height, 2):
        for gx in range(0, width, 2 * n):
            addrs = {tiled2d(x, y, pitch, bpb_log2) for y in (gy, gy + 1) for x in range(gx, gx + 2 * n)}
            lo = min(addrs)
            span = set(range(lo, lo + 4 * ub, 1 << bpb_log2))
            if addrs != span or lo % (4 * ub):
                bad += 1
    return bad


def rational_offset(hx, hy, pitch, bpb_log2):
    """Corrective model R: group = 2N x 2 guest blocks (2 x 2 SDK units) -> 3 x 3 host Nx1 sub-units of the SDK
    shape, column-major like the SDK; host = group guest address x 9/4 + sub-unit index x unit bytes + offset."""
    n_log2 = unit_log2(bpb_log2)
    x_sub = hx >> n_log2
    gxu, gy = (x_sub // 3) * 2, (hy // 3) * 2          # guest group origin: units along x, rows along y
    g_addr = tiled2d(gxu << n_log2, gy, pitch, bpb_log2)
    sub_x, sub_y = x_sub - (x_sub // 3) * 3, hy - (hy // 3) * 3
    base = Fraction(g_addr * 9, 4)
    return base, int(base) + ((((sub_x * 3 + sub_y) << n_log2) + (hx & ((1 << n_log2) - 1))) << bpb_log2)


def check_rational(width, height, pitch, bpb_log2):
    """S3b. width, height even multiples of the group (2N x 2)."""
    bpb = 1 << bpb_log2
    ub = unit_bytes(bpb_log2)
    seen, coll, own, nonint = set(), 0, 0, 0
    for hy in range(height * 3 // 2):
        for hx in range(width * 3 // 2):
            base, a = rational_offset(hx, hy, pitch, bpb_log2)
            nonint += base.denominator != 1
            coll += a in seen
            seen.add(a)
            gx, gy = (hx * 2) // 3, (hy * 2) // 3      # guest pixel under the host pixel (3:2 nearest-left)
            if a // (4 * ub * 9 // 4) != tiled2d(gx, gy, pitch, bpb_log2) // (4 * ub):
                own += 1
    expected = set()
    n = 1 << unit_log2(bpb_log2)
    for gy in range(0, height, 2):
        for gx in range(0, width, 2 * n):
            g = tiled2d(gx, gy, pitch, bpb_log2) // (4 * ub)
            expected.update(range(g * 9 * ub, (g + 1) * 9 * ub, bpb))
    return coll, own, nonint, seen == expected


def right_neighbour_table(pitch, bpb_log2):
    """S4: under R, offset from a host sub-unit to the next one to the right, by sub-unit column (0, 1) inside a
    group. Column 2 is the group edge (the SDK's pair edge), where a full offset recalculation is required, as in
    the SDK. Returns {sub_x: set(offsets)} measured from R over a row band."""
    n = 1 << unit_log2(bpb_log2)
    table = {}
    for hy in range(0, 6):
        for x_sub in range(0, 24):
            hx = x_sub * n
            if x_sub % 3 == 2:        # group edge: full recalculation (SDK: next pair of consecutive blocks)
                continue
            d = rational_offset(hx + n, hy, pitch, bpb_log2)[1] - rational_offset(hx, hy, pitch, bpb_log2)[1]
            table.setdefault(x_sub % 3, set()).add(d)
    return table


def predicted_right(bpb_log2, sub_x):
    """Closed form for S4 inside a group: the next column is 3 sub-units (column-major, 3 rows) further.
    The SDK's same-unit case is `unit bytes x scale.y`; R replaces it by 3 x unit bytes and moves the pair edge
    (odd-consecutive case, `XeTextureTiledOddConsecutiveBlocksOffset`) inside the group."""
    assert sub_x < 2
    return 3 * unit_bytes(bpb_log2)


def transfer_3_2(guest_width_1x):
    """S5: the ownership transfers G6-P88 observed every frame: a 1x surface of guest width G and the 4x view of the
    same EDRAM (G / 2 pixels x 2 x 2 samples). At 3:2 the host 1x RT has 1.5 G columns and the host 4x RT 0.75 G
    pixels x 2 sample columns. Host-sample-major convention (G6-P86 V9): host 1x column X <-> 4x pixel X >> 1,
    sample X & 1 (the same along Y). Returns (integer host 4x width, bijective, round trip exact, fraction of host
    columns whose guest sample after the transfer differs from the guest-exact sample)."""
    g = guest_width_1x
    host_1x = Fraction(3 * g, 2)
    host_4x_px = Fraction(3 * (g // 2), 2)
    if host_1x.denominator != 1 or host_4x_px.denominator != 1 or host_4x_px * 2 != host_1x:
        return False, False, False, None
    n = int(host_1x)
    forward = {x: (x >> 1, x & 1) for x in range(n)}
    bijective = len(set(forward.values())) == n
    back = {v: k for k, v in forward.items()}
    round_trip = all(back[forward[x]] == x for x in range(n))
    mismatched = 0
    for x in range(n):
        guest_exact = (2 * x) // 3                       # guest 1x pixel = guest 4x sample column of host column x
        p, s = forward[x]
        landed = 2 * ((2 * p) // 3) + s                  # guest sample column the 4x host sample stands for
        mismatched += landed != guest_exact
    return True, bijective, round_trip, Fraction(mismatched, n)


# --- S6 (G6-P92): coverage of the 3:2 fast 32bpp 1x/2x resolve copy dispatch -------------------------------------
# The copy variant (G6-P89 resolve_fast_32bpp_1x2xmsaa_scaled32) runs one thread per 8 host pixels along X with an X
# bound at width_div_8_scaled = (width_div_8 x 3) >> 1 (resolve.xesli at 3:2) and NO Y bound; GetCopyShader dispatches
# ceil(host width / 64) x ceil(host height / group height) groups. G6-P89 used the SDK's 8-row groups; G6-P92 uses 4.
# Guest resolve extents and offsets are multiples of 8 guest pixels (xenos::kResolveAlignmentPixels) = 12 host pixels.
COPY_THREAD_PIXELS = 8
COPY_GROUP_WIDTH_LOG2 = 6        # SDK resolve_copy_shader_info, fast 32bpp 1x/2x MSAA
SDK_GROUP_HEIGHT_LOG2 = 3        # the same table entry (integer scales)
G6P92_GROUP_HEIGHT_LOG2 = 2      # g6p89::kResolveGroupHeightLog2 (the 3:2 variant's LOCAL_SIZE_Y_XE = 4)
GROUP_GUEST, GROUP_HOST = 64, 144


def r_offset_int(hx, hy, pitch, bpb_log2):
    """Model R closed form (integer); tied to rational_offset by selftest and the G6-P89 checksum."""
    n_log2 = unit_log2(bpb_log2)
    xs = hx >> n_log2
    g = tiled2d(((xs // 3) * 2) << n_log2, (hy // 3) * 2, pitch, bpb_log2)
    return g * 9 // 4 + (((((xs % 3) * 3 + hy % 3) << n_log2) + (hx & ((1 << n_log2) - 1))) << bpb_log2)


def resolve_extent_exact(width_div_8, height_div_8, group_height_log2=G6P92_GROUP_HEIGHT_LOG2):
    """Mirror of g6p89::ResolveExtentExact: whole 8-pixel threads along X and whole groups along Y at 3:2."""
    host_w, host_h = width_div_8 * 12, height_div_8 * 12
    return host_w % COPY_THREAD_PIXELS == 0 and host_h % (1 << group_height_log2) == 0


def surface_extent_bytes(pitch, height_aligned, bpb_log2=2):
    """Guest bytes of a 2D tiled surface (pitch and height aligned to 32): the destination allocation."""
    return align(pitch, TILE) * align(height_aligned, TILE) << bpb_log2


def simulate_copy_3_2(w, h, pitch, dest_height, off=(0, 0), group_height_log2=G6P92_GROUP_HEIGHT_LOG2,
                      floor_groups=False, texture=None, load_offset=None):
    """Simulate the dispatch of one 3:2 copy of a guest w x h rectangle (multiples of 8) into a 32bpp tiled
    destination (pitch, dest_height before alignment) at guest offset `off` (multiples of 8), and check it against
    independent references. `texture` = (tw, th): also load that texture at the destination base with the bounded
    3:2 load (size_blocks = 1.5 tw x 1.5 th, explicit XY bound) and check the round trip. Returns counts."""
    load_offset = load_offset or r_offset_int
    w8, h8 = w // 8, h // 8
    host_w, host_h = w8 * 12, h8 * 12
    ox, oy = off[0] * 3 // 2, off[1] * 3 // 2
    x_bound = (w8 * 3) >> 1
    gx = (host_w + (1 << COPY_GROUP_WIDTH_LOG2) - 1) >> COPY_GROUP_WIDTH_LOG2
    gh = 1 << group_height_log2
    gy = host_h >> group_height_log2 if floor_groups else (host_h + gh - 1) >> group_height_log2
    alloc_host = surface_extent_bytes(pitch, dest_height) * 9 // 4
    # Independent references: the guest 64-byte groups the guest rectangle touches (guest tiled addresses only).
    rect_groups = {tiled2d(x, y, pitch, 2) // GROUP_GUEST
                   for y in range(off[1], off[1] + h) for x in range(off[0], off[0] + w)}
    written = {}
    extra = collisions = ownership = outside_groups = out_of_alloc = 0
    for ty in range(gy * gh):
        for t in range(gx * (1 << COPY_GROUP_WIDTH_LOG2) // COPY_THREAD_PIXELS):
            if t >= x_bound:
                continue
            for i in range(COPY_THREAD_PIXELS):
                hx = t * COPY_THREAD_PIXELS + i
                dx, dy = hx + ox, ty + oy
                a = r_offset_int(dx, dy, pitch, 2)
                if not (hx < host_w and ty < host_h):
                    extra += 1
                if a in written:
                    collisions += 1
                written[a] = (dx, dy)
                if a + 4 > alloc_host:
                    out_of_alloc += 1
                    continue
                guest = tiled2d((dx * 2) // 3, (dy * 2) // 3, pitch, 2)
                ownership += a // GROUP_HOST != guest // GROUP_GUEST
                outside_groups += a // GROUP_HOST not in rect_groups
    covered = {p for p in written.values()}
    missing = sum(1 for y in range(oy, oy + host_h) for x in range(ox, ox + host_w) if (x, y) not in covered)
    out = {"host": [host_w, host_h], "groups": [gx, gy], "group_height": gh, "writes": len(written) + collisions,
           "missing": missing, "extra": extra, "collisions": collisions, "ownership": ownership,
           "outside_rect_groups": outside_groups, "out_of_alloc": out_of_alloc,
           "max_host_byte": (max(written) + 4) if written else 0, "alloc_host_bytes": alloc_host,
           "rule_admits": resolve_extent_exact(w8, h8, group_height_log2)}
    if texture:
        tw, th = texture
        lw, lh = tw * 3 // 2, th * 3 // 2
        rt = 0
        for y in range(lh):
            for x in range(lw):
                src = written.get(load_offset(x, y, pitch, 2))
                rt += src != (x, y)
        out["load"] = {"host": [lw, lh], "round_trip_errors": rt}
    return out


def s6_cases(full=False):
    """The observed knaar_10 family, its neighbours and the negative controls (G6-P92 E1 plan)."""
    c = {
        "knaar10_640x360": dict(w=640, h=360, pitch=640, dest_height=360, texture=(640, 360)),
        "ctrl_640x352": dict(w=640, h=352, pitch=640, dest_height=352, texture=(640, 352)),
        "ctrl_640x368": dict(w=640, h=368, pitch=640, dest_height=368, texture=(640, 368)),
        "640x360_pitch1280": dict(w=640, h=360, pitch=1280, dest_height=720),
        "640x360_offset8": dict(w=640, h=360, pitch=1280, dest_height=384, off=(8, 8)),
        # negative controls (each must show the defect it names)
        "neg_sdk_8row_groups": dict(w=640, h=360, pitch=640, dest_height=360, group_height_log2=SDK_GROUP_HEIGHT_LOG2),
        "neg_floor_group_count": dict(w=640, h=360, pitch=640, dest_height=360, floor_groups=True,
                                      group_height_log2=SDK_GROUP_HEIGHT_LOG2),
        "neg_8row_crosses_surface": dict(w=640, h=360, pitch=640, dest_height=384, off=(0, 24),
                                         group_height_log2=SDK_GROUP_HEIGHT_LOG2),
        "neg_load_mapping_disagrees": dict(w=640, h=360, pitch=640, dest_height=360, texture=(640, 360),
                                           load_offset="row_major"),
        "neg_odd_width_admitted": dict(w=648, h=360, pitch=1280, dest_height=384),
        "neg_rect_beyond_allocation": dict(w=640, h=384, pitch=640, dest_height=384, off=(0, 8)),
    }
    if full:
        c["main_1280x720"] = dict(w=1280, h=720, pitch=1280, dest_height=720, texture=(1280, 720))
        c["shadow_1024x1024"] = dict(w=1024, h=1024, pitch=1024, dest_height=1024, texture=(1024, 1024))
    return c


def row_major_load(hx, hy, pitch, bpb_log2):
    """Negative control: a load mapping whose sub-units are row-major (disagrees with the resolve's column-major R)."""
    n_log2 = unit_log2(bpb_log2)
    xs = hx >> n_log2
    g = tiled2d(((xs // 3) * 2) << n_log2, (hy // 3) * 2, pitch, bpb_log2)
    return g * 9 // 4 + (((((hy % 3) * 3 + xs % 3) << n_log2) + (hx & ((1 << n_log2) - 1))) << bpb_log2)


def run_s6(full=False):
    out = {}
    for name, kw in s6_cases(full).items():
        kw = dict(kw)
        if kw.get("load_offset") == "row_major":
            kw["load_offset"] = row_major_load
        out[name] = simulate_copy_3_2(**kw)
    # Observed aliasing pair (G6-P88 census, knaar_10): the 640x360 destination's extent ends where the 1280x720
    # destination begins; its host image must end at or before the neighbour's host image begins.
    b640, len640, b1280 = 522272768, 983040, 523255808  # 0x1F214000, 0x1F304000 (census dest ids 6 and 5)
    out["alias_observed_pair"] = {"neighbour_adjacent": b640 + len640 == b1280,
                                  "host_end_640": (b640 + len640) // GROUP_GUEST * GROUP_HOST,
                                  "host_start_1280": b1280 // GROUP_GUEST * GROUP_HOST}
    # I7: at integer scales the SDK's 8-row groups always divide the host height (8 x h8 x s); at 3:2 they do only for
    # an even h8 - the exact reason for G6-P89's refusal - while 4-row groups always do.
    out["dispatch_exactness"] = {
        "integer_8row_all_exact": all((8 * h8 * s) % 8 == 0 for s in (1, 2, 3) for h8 in range(1, 1025)),
        "scale32_8row_exact_iff_even": all(((12 * h8) % 8 == 0) == (h8 % 2 == 0) for h8 in range(1, 1025)),
        "scale32_4row_all_exact": all((12 * h8) % 4 == 0 for h8 in range(1, 1025)),
        "width_rule_iff_even_w8": all(resolve_extent_exact(w8, 1) == (w8 % 2 == 0) for w8 in range(1, 1025)),
    }
    return out


def s6_verdict(s6):
    def clean(r):
        return (r["missing"] == r["extra"] == r["collisions"] == r["ownership"] == r["outside_rect_groups"] ==
                r["out_of_alloc"] == 0 and r.get("load", {}).get("round_trip_errors", 0) == 0 and r["rule_admits"])
    v = {name: clean(r) for name, r in s6.items() if name.startswith(("knaar10", "ctrl", "640x360", "main", "shadow"))}
    v["neg_sdk_8row_groups"] = s6["neg_sdk_8row_groups"]["extra"] > 0 and not s6["neg_sdk_8row_groups"]["rule_admits"]
    v["neg_floor_group_count"] = s6["neg_floor_group_count"]["missing"] > 0
    v["neg_8row_crosses_surface"] = s6["neg_8row_crosses_surface"]["out_of_alloc"] > 0
    n = s6["neg_load_mapping_disagrees"]
    v["neg_load_mapping_disagrees"] = n["load"]["round_trip_errors"] > 0 and n["ownership"] == 0
    v["neg_odd_width_admitted"] = (s6["neg_odd_width_admitted"]["missing"] > 0 and
                                   not s6["neg_odd_width_admitted"]["rule_admits"])
    v["neg_rect_beyond_allocation"] = s6["neg_rect_beyond_allocation"]["out_of_alloc"] > 0
    a = s6["alias_observed_pair"]
    v["alias_observed_pair"] = a["neighbour_adjacent"] and a["host_end_640"] <= a["host_start_1280"]
    v.update(s6["dispatch_exactness"])
    return v


SURFACES = [("main_1280", 1280, 64, 16), ("half_640", 640, 64, 16), ("shadow_1024", 1024, 64, 16)]


def run():
    out = {"S1_integer_control": {}, "S2_direct_3_2": {}, "S3_groups_contiguous": {}, "S3_rational": {},
           "S4_right_neighbour": {}, "S5_transfer_3_2": {}}
    for bpb_log2 in range(5):
        for name, pitch, w, h in SURFACES:
            key = f"{name}_bpb{1 << bpb_log2}"
            out["S1_integer_control"][key] = {s: check_integer(w, h, pitch, bpb_log2, s) for s in (1, 2, 3)}
            out["S2_direct_3_2"][key] = check_direct_generalisation(w, h, pitch, bpb_log2)
            out["S3_groups_contiguous"][key] = group_contiguous(w, h, pitch, bpb_log2)
            if out["S3_groups_contiguous"][key] == 0:
                out["S3_rational"][key] = check_rational(w, h, pitch, bpb_log2)
        if bpb_log2 >= 2:
            t = right_neighbour_table(1280, bpb_log2)
            out["S4_right_neighbour"][f"bpb{1 << bpb_log2}"] = {
                k: (sorted(v), predicted_right(bpb_log2, k)) for k, v in sorted(t.items())}
    for name, g in (("colour_1280_vs_4x_640", 1280), ("depth_1040_vs_4x_520", 1040)):
        ok, bij, rt, mis = transfer_3_2(g)
        out["S5_transfer_3_2"][name] = {"integer": ok, "bijective": bij, "round_trip": rt,
                                         "guest_sample_mismatch": str(mis)}
    return out


def verdicts(r):
    v = {}
    v["S1"] = all(c == (0, False, 0) for per in r["S1_integer_control"].values() for c in per.values())
    v["S2_fails"] = all(any(c) for c in r["S2_direct_3_2"].values())
    by_bpb = {}
    for k, bad in r["S3_groups_contiguous"].items():
        by_bpb.setdefault(int(k.split("_bpb")[1]), []).append(bad)
    v["S3_contiguous_bpb"] = sorted(b for b, bads in by_bpb.items() if not any(bads))
    v["S3_not_contiguous_bpb"] = sorted(b for b, bads in by_bpb.items() if any(bads))
    v["S3_rational_ok"] = {k: (c[0] == 0 and c[1] == 0 and c[2] == 0 and c[3]) for k, c in r["S3_rational"].items()}
    v["S4_closed_form"] = all(len(meas) == 1 and meas[0] == pred for t in r["S4_right_neighbour"].values()
                              for meas, pred in t.values())
    v["S5_round_trip_exact"] = all(x["bijective"] and x["round_trip"] for x in r["S5_transfer_3_2"].values())
    v["S5_guest_exact"] = all(x["guest_sample_mismatch"] == "0" for x in r["S5_transfer_3_2"].values())
    return v


def selftest():
    failures = []
    # S1 control must pass for every bpb on a small surface, and the port must equal the SDK formula's known values.
    if sdk_scaled_offset(0, 0, 1280, 2, 2, 2) != 0 or sdk_scaled_offset(0, 1, 1280, 2, 2, 2) != 16:
        failures.append("port: sub-unit (0,1) of unit 0 must be the second 16-byte sub-unit (column-major)")
    if sdk_scaled_offset(4, 0, 1280, 2, 2, 2) != 32:
        failures.append("port: sub-unit (1,0) must follow the column (offset 2 x 16)")
    for b in range(5):
        if check_integer(64, 8, 1280, b, 2) != (0, False, 0):
            failures.append(f"S1 bpb{1 << b}")
    if not all(any(check_direct_generalisation(64, 8, 1280, b)) for b in range(5)):
        failures.append("S2 must fail")
    if group_contiguous(64, 16, 1280, 2) or group_contiguous(64, 16, 1280, 3) or group_contiguous(64, 16, 1280, 4):
        failures.append("S3 groups must be contiguous at 4 / 8 / 16 bytes per block")
    if not group_contiguous(64, 16, 1280, 1):
        failures.append("S3 must reject 2 bytes per block (2N x 2 is not one aligned run)")
    c = check_rational(64, 16, 1280, 2)
    if c != (0, 0, 0, True):
        failures.append(f"S3 rational 32bpp {c}")
    # mutation: a row-major sub-unit index must break bijection or ownership at 3:2 (the G6-P87 mutation class).
    global rational_offset
    original = rational_offset

    def mutant(hx, hy, pitch, bpb_log2):
        n_log2 = unit_log2(bpb_log2)
        x_sub = hx >> n_log2
        g_addr = tiled2d(((x_sub // 3) * 2) << n_log2, (hy // 3) * 2, pitch, bpb_log2)
        sub_x, sub_y = x_sub % 3, hy % 3
        base = Fraction(g_addr * 9, 4)
        return base, int(base) + ((((sub_y * 3 + sub_x) << n_log2) + (hx & ((1 << n_log2) - 1))) << bpb_log2)
    rational_offset = mutant
    try:
        if check_rational(64, 16, 1280, 2) == (0, 0, 0, True) and right_neighbour_table(1280, 2) == \
                {k: {predicted_right(2, k)} for k in range(2)}:
            failures.append("mutation (row-major sub-units) not detected by S3 + S4")
    finally:
        rational_offset = original
    for b in (2, 3, 4):
        t = right_neighbour_table(1280, b)
        if any(v != {predicted_right(b, k)} for k, v in t.items()):
            failures.append(f"S4 closed form bpb{1 << b}: {t}")
    ok, bij, rt, mis = transfer_3_2(1280)
    if not (ok and bij and rt and mis > 0):
        failures.append(f"S5 1280: {ok} {bij} {rt} {mis}")
    if transfer_3_2(1282)[0]:
        failures.append("S5 must refuse a 4x view whose 3:2 width is fractional")
    print("G6P88 sdk scaled model selftest", "PASS" if not failures else "FAIL " + "; ".join(failures))
    return 0 if not failures else 1


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=("selftest", "report", "s6"))
    ap.add_argument("--json", type=Path)
    a = ap.parse_args()
    if a.cmd == "selftest":
        return selftest()
    if a.cmd == "s6":
        r = {"S6_resolve_dispatch_3_2": run_s6(full=True)}
        r["verdicts"] = {"S6": s6_verdict(r["S6_resolve_dispatch_3_2"])}
    else:
        r = run()
        r["verdicts"] = verdicts(r)
    text = json.dumps(r, indent=1, default=str)
    if a.json:
        a.json.parent.mkdir(parents=True, exist_ok=True)
        a.json.write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
