// M45 (D-083): DXBC container hash for the shaders ReXGlue builds (replaces AMD's DXBCChecksum.cpp, whose source
// carries no licence grant). Installed into the SDK as include/rex/m45_dxbc_hash.h by tools/m45_runtime_patch.py.
//
// Derived from ComputeHashRetail in Microsoft DirectXShaderCompiler lib/DxilHash/DxilHash.cpp
// (github.com/microsoft/DirectXShaderCompiler, commit 194bb75bea2becb42810d72a16195089c1908e10), whose notice reads:
//
//   DxilHash.cpp
//   Copyright (C) Microsoft Corporation. All rights reserved.
//   This file is distributed under the University of Illinois Open Source
//   License. See LICENSE.TXT for details.
//
//   DXBC/DXIL container hashing functions
//
// The University of Illinois/NCSA Open Source License text is shipped as licenses\DirectXShaderCompiler-LICENSE.txt
// (repository: tools/installer/DirectXShaderCompiler-LICENSE.txt). Like its upstream, this code is derived from the
// RSA Data Security, Inc. MD5 Message-Digest Algorithm. Changes from upstream: Windows types replaced by <cstdint>
// types; every 64-byte block is copied before use instead of read through a cast pointer; the round helpers are
// static inline functions in a namespace; the container's leading 20 bytes are skipped here (upstream's caller does
// that); a size below 20 hashes an empty payload instead of reading out of bounds.
//
// Not a secure hash. It is the checksum Direct3D 12 verifies in a DXBC container header.

#pragma once

#include <cstdint>
#include <cstring>

namespace m45dxbc {

namespace detail {

inline constexpr uint8_t kPadding[64] = {0x80};

inline void FF(uint32_t& a, uint32_t b, uint32_t c, uint32_t d, uint32_t x, uint32_t s, uint32_t ac) {
  a += ((b & c) | (~b & d)) + x + ac;
  a = ((a << s) | (a >> (32 - s))) + b;
}
inline void GG(uint32_t& a, uint32_t b, uint32_t c, uint32_t d, uint32_t x, uint32_t s, uint32_t ac) {
  a += ((b & d) | (c & ~d)) + x + ac;
  a = ((a << s) | (a >> (32 - s))) + b;
}
inline void HH(uint32_t& a, uint32_t b, uint32_t c, uint32_t d, uint32_t x, uint32_t s, uint32_t ac) {
  a += (b ^ c ^ d) + x + ac;
  a = ((a << s) | (a >> (32 - s))) + b;
}
inline void II(uint32_t& a, uint32_t b, uint32_t c, uint32_t d, uint32_t x, uint32_t s, uint32_t ac) {
  a += (c ^ (b | ~d)) + x + ac;
  a = ((a << s) | (a >> (32 - s))) + b;
}

inline void Transform(uint32_t state[4], const uint32_t x[16]) {
  uint32_t a = state[0], b = state[1], c = state[2], d = state[3];
  FF(a, b, c, d, x[0], 7, 0xd76aa478);   FF(d, a, b, c, x[1], 12, 0xe8c7b756);
  FF(c, d, a, b, x[2], 17, 0x242070db);  FF(b, c, d, a, x[3], 22, 0xc1bdceee);
  FF(a, b, c, d, x[4], 7, 0xf57c0faf);   FF(d, a, b, c, x[5], 12, 0x4787c62a);
  FF(c, d, a, b, x[6], 17, 0xa8304613);  FF(b, c, d, a, x[7], 22, 0xfd469501);
  FF(a, b, c, d, x[8], 7, 0x698098d8);   FF(d, a, b, c, x[9], 12, 0x8b44f7af);
  FF(c, d, a, b, x[10], 17, 0xffff5bb1); FF(b, c, d, a, x[11], 22, 0x895cd7be);
  FF(a, b, c, d, x[12], 7, 0x6b901122);  FF(d, a, b, c, x[13], 12, 0xfd987193);
  FF(c, d, a, b, x[14], 17, 0xa679438e); FF(b, c, d, a, x[15], 22, 0x49b40821);
  GG(a, b, c, d, x[1], 5, 0xf61e2562);   GG(d, a, b, c, x[6], 9, 0xc040b340);
  GG(c, d, a, b, x[11], 14, 0x265e5a51); GG(b, c, d, a, x[0], 20, 0xe9b6c7aa);
  GG(a, b, c, d, x[5], 5, 0xd62f105d);   GG(d, a, b, c, x[10], 9, 0x02441453);
  GG(c, d, a, b, x[15], 14, 0xd8a1e681); GG(b, c, d, a, x[4], 20, 0xe7d3fbc8);
  GG(a, b, c, d, x[9], 5, 0x21e1cde6);   GG(d, a, b, c, x[14], 9, 0xc33707d6);
  GG(c, d, a, b, x[3], 14, 0xf4d50d87);  GG(b, c, d, a, x[8], 20, 0x455a14ed);
  GG(a, b, c, d, x[13], 5, 0xa9e3e905);  GG(d, a, b, c, x[2], 9, 0xfcefa3f8);
  GG(c, d, a, b, x[7], 14, 0x676f02d9);  GG(b, c, d, a, x[12], 20, 0x8d2a4c8a);
  HH(a, b, c, d, x[5], 4, 0xfffa3942);   HH(d, a, b, c, x[8], 11, 0x8771f681);
  HH(c, d, a, b, x[11], 16, 0x6d9d6122); HH(b, c, d, a, x[14], 23, 0xfde5380c);
  HH(a, b, c, d, x[1], 4, 0xa4beea44);   HH(d, a, b, c, x[4], 11, 0x4bdecfa9);
  HH(c, d, a, b, x[7], 16, 0xf6bb4b60);  HH(b, c, d, a, x[10], 23, 0xbebfbc70);
  HH(a, b, c, d, x[13], 4, 0x289b7ec6);  HH(d, a, b, c, x[0], 11, 0xeaa127fa);
  HH(c, d, a, b, x[3], 16, 0xd4ef3085);  HH(b, c, d, a, x[6], 23, 0x04881d05);
  HH(a, b, c, d, x[9], 4, 0xd9d4d039);   HH(d, a, b, c, x[12], 11, 0xe6db99e5);
  HH(c, d, a, b, x[15], 16, 0x1fa27cf8); HH(b, c, d, a, x[2], 23, 0xc4ac5665);
  II(a, b, c, d, x[0], 6, 0xf4292244);   II(d, a, b, c, x[7], 10, 0x432aff97);
  II(c, d, a, b, x[14], 15, 0xab9423a7); II(b, c, d, a, x[5], 21, 0xfc93a039);
  II(a, b, c, d, x[12], 6, 0x655b59c3);  II(d, a, b, c, x[3], 10, 0x8f0ccc92);
  II(c, d, a, b, x[10], 15, 0xffeff47d); II(b, c, d, a, x[1], 21, 0x85845dd1);
  II(a, b, c, d, x[8], 6, 0x6fa87e4f);   II(d, a, b, c, x[15], 10, 0xfe2ce6e0);
  II(c, d, a, b, x[6], 15, 0xa3014314);  II(b, c, d, a, x[13], 21, 0x4e0811a1);
  II(a, b, c, d, x[4], 6, 0xf7537e82);   II(d, a, b, c, x[11], 10, 0xbd3af235);
  II(c, d, a, b, x[2], 15, 0x2ad7d2bb);  II(b, c, d, a, x[9], 21, 0xeb86d391);
  state[0] += a; state[1] += b; state[2] += c; state[3] += d;
}

}  // namespace detail

// Offset of the first hashed byte: the "DXBC" magic (4) and the hash field (16) are not hashed.
inline constexpr uint32_t kHashedOffset = 20;

// ComputeHashRetail over bytes [20, size) of a DXBC container; out receives the four little-endian words of the
// 16-byte hash field (container offset 4). Block words are read in host byte order (little-endian on x86-64).
inline void ContainerHash(const void* container, uint32_t size, uint32_t out[4]) {
  const uint8_t* data = static_cast<const uint8_t*>(container) + kHashedOffset;
  const uint32_t byte_count = size > kHashedOffset ? size - kHashedOffset : 0;
  const uint32_t left_over = byte_count & 0x3f;
  const bool two_rows = left_over >= 56;
  const uint32_t pad_amount = two_rows ? 120 - left_over : 56 - left_over;
  uint32_t state[4] = {0x67452301, 0xefcdab89, 0x98badcfe, 0x10325476};
  const uint32_t full = byte_count & ~0x3fu;
  uint32_t x[16];
  for (uint32_t offset = 0; offset < full; offset += 64) {
    std::memcpy(x, data + offset, 64);
    detail::Transform(state, x);
  }
  const uint32_t remainder = byte_count - full;
  uint8_t* xb = reinterpret_cast<uint8_t*>(x);
  if (!two_rows) {
    // One closing block: bit count, the tail, padding, and the size word in x[15].
    x[0] = byte_count << 3;
    std::memcpy(xb + 4, data + full, remainder);
    std::memcpy(xb + 4 + remainder, detail::kPadding, pad_amount);
    x[15] = 1 | (byte_count << 1);
    detail::Transform(state, x);
  } else {
    // Two closing blocks: the tail with padding, then the bit count, zeros and the size word.
    std::memcpy(xb, data + full, remainder);
    std::memcpy(xb + remainder, detail::kPadding, pad_amount - 56);
    detail::Transform(state, x);
    x[0] = byte_count << 3;
    std::memcpy(xb + 4, detail::kPadding + pad_amount - 56, 56);
    x[15] = 1 | (byte_count << 1);
    detail::Transform(state, x);
  }
  std::memcpy(out, state, 16);
}

}  // namespace m45dxbc
