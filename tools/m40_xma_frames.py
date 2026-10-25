"""M40: cuts XMA2 frames out of a raw packet file of the game (2048-byte packets, e.g. WORLD/SOUND/Stream.h00) into
the byte form XmaContext hands FFmpeg: one padding byte ((padding_end & 7) << 2, padding_start 0), then the frame
bits from bit 0. Output (game-derived, private only): per stream run, u32 frame count, then per frame u16 size +
bytes. Usage: m40_xma_frames.py SOURCE OUT [--packets N]"""
import argparse
import struct

PKT = 2048
DATA_BITS = (PKT - 4) * 8


def header(p):
    count = p[0] >> 2
    offset = (((p[0] & 3) << 13) | (p[1] << 5) | (p[2] >> 3)) + 32  # bit offset of the first frame in the packet
    skip = p[3]
    return count, offset, skip


def cut(data):
    n = len(data) // PKT
    streams = []
    i = 0
    while i < n:
        count, offset, skip = header(data[i * PKT:(i + 1) * PKT])
        if skip == 0xFF or count == 0 or offset >= PKT * 8:
            i += 1
            continue
        chain, j = [], i
        while j < n and len(chain) < 1024:
            c, o, s = header(data[j * PKT:(j + 1) * PKT])
            if o > PKT * 8:
                break
            chain.append(j)
            j += (s + 1) if s != 0xFF else 1
        buf = b''.join(data[k * PKT + 4:(k + 1) * PKT] for k in chain)
        total = len(buf) * 8
        pos = offset - 32
        frames = []
        while pos + 15 <= total:
            b0 = pos >> 3
            length = (int.from_bytes(buf[b0:b0 + 3], 'big') >> (24 - 15 - (pos & 7))) & 0x7FFF
            if length == 0x7FFF:
                # Padding (all ones) to the end of this packet: the next packet says where its first frame starts.
                nxt = pos // DATA_BITS + 1
                if nxt >= len(chain):
                    break
                c, o, s = header(data[chain[nxt] * PKT:(chain[nxt] + 1) * PKT])
                if c == 0 or s == 0xFF:
                    break
                pos = nxt * DATA_BITS + o - 32
                continue
            if length < 16 or length > 0x4000 or pos + length > total:
                break
            first, last = pos >> 3, (pos + length - 1) >> 3
            raw = int.from_bytes(buf[first:last + 1], 'big')
            raw = (raw >> ((last - first + 1) * 8 - (pos & 7) - length)) & ((1 << length) - 1)
            nbytes = (length + 7) // 8
            pad_end = nbytes * 8 - length
            frames.append(bytes([(pad_end & 7) << 2]) + (raw << pad_end).to_bytes(nbytes, 'big'))
            pos += length
        if frames:
            streams.append(frames)
        i = chain[min(pos // DATA_BITS, len(chain) - 1)] + 1
    return streams


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('source')
    ap.add_argument('out')
    ap.add_argument('--packets', type=int, default=8000)
    a = ap.parse_args()
    with open(a.source, 'rb') as f:
        data = f.read(a.packets * PKT)
    streams = cut(data)
    with open(a.out, 'wb') as f:
        for s in streams:
            f.write(struct.pack('<I', len(s)))
            for fr in s:
                f.write(struct.pack('<H', len(fr)) + fr)
    print(f'M40_XMA_FRAMES streams={len(streams)} frames={sum(len(s) for s in streams)} '
          f'packets={len(data) // PKT}')


if __name__ == '__main__':
    main()
