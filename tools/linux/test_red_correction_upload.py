#!/usr/bin/env python3
"""Compile and execute actual SDK upload regions with synthetic buffer/device storage.

No shader/game data, GPU, window or device. Tests bytes handed to uniform buffers,
descriptor dirtiness, cache reuse/restoration, allocation failure, and D3D12 parity.
The extracted C++ is private. This is component evidence, not native visual acceptance.
"""
import argparse
import os
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[2]


def program(sdk):
    vk = (sdk / 'src/graphics/vulkan/command_processor.cpp').read_text()
    vk = vk[vk.index('  // Check if the float constant layout is still the same'):]
    vk = vk[:vk.index('  // Textures and samplers.')]
    dx = (sdk / 'src/graphics/d3d12/command_processor.cpp').read_text()
    select = dx[dx.index('  // HD+ lighting L1 (D-150): optional red-correction bypass'):]
    select = select[:select.index('  // Write the constant buffer data.')]
    upload = dx[dx.index('  if (!cbuffer_binding_float_pixel_.up_to_date) {'):]
    upload = upload[:upload.index('  if (!cbuffer_binding_bool_loop_.up_to_date) {')]
    return PRELUDE + '\nbool vulkan(const Shader* vertex_shader, const Shader* pixel_shader) {\n' + vk + \
        '\nreturn true; }\nbool d3d12(const Shader* pixel_shader) {\n' + \
        'uint32_t float_constant_count_pixel = pixel_shader ? pixel_shader->map.float_count : 0;\n' + select + upload + \
        '\nreturn true; }\n' + MAIN


PRELUDE = r'''
#include <algorithm>
#include <array>
#include <cassert>
#include <cstdint>
#include <cstring>
#include <cstdio>
#include <vector>
#include "hdl_red_correction.h"
#define REXGPU_INFO(...) ((void)0)
#define assert_zero(x) assert(!(x))
namespace rex { bool bit_scan_forward(uint64_t x, uint32_t* out) {
  if (!x) return false; *out=0; while (!(x & 1)) { ++*out; x >>= 1; } return true;
} }
struct Shader {
  struct ConstantRegisterMap { uint64_t float_bitmap[4] = {1,0,0,1ull<<63}; uint32_t float_count=2; } map;
  uint64_t hash = hdlred::kPixelShaderHash;
  uint64_t ucode_data_hash() const { return hash; }
  const ConstantRegisterMap& constant_register_map() const { return map; }
};
struct SpirvShaderTranslator {
  enum { kConstantBufferSystem, kConstantBufferFloatVertex, kConstantBufferFloatPixel,
         kConstantBufferBoolLoop, kConstantBufferFetch, kConstantBufferCount, kDescriptorSetConstants=0 };
  struct SystemConstants { uint32_t unused=0; };
};
constexpr int XE_GPU_REG_SHADER_CONSTANT_000_X=0, XE_GPU_REG_SHADER_CONSTANT_256_X=1024,
  XE_GPU_REG_SHADER_CONSTANT_BOOL_000_031=2048, XE_GPU_REG_SHADER_CONSTANT_FETCH_00_0=2100;
using VkDeviceSize = size_t;
struct VkDescriptorBufferInfo { size_t buffer=0, offset=0, range=0; };
struct Pool {
  std::vector<std::vector<uint8_t>> allocations; bool fail=false;
  uint8_t* Request(int, size_t n, size_t, size_t& buffer, size_t& offset) {
    if (fail) return nullptr;
    allocations.emplace_back(n, 0); buffer=allocations.size(); offset=0; return allocations.back().data();
  }
  uint8_t* Request(int f, size_t n, size_t a, void*, void*, size_t* addr) {
    size_t offset=0; return Request(f,n,a,*addr,offset);
  }
} pool;
Pool *uniform_buffer_pool_=&pool, *constant_buffer_pool_=&pool;
uint32_t regs[2400] = {};
int frame_current_=1;
size_t uniform_buffer_alignment=256;
struct Device { struct Properties { size_t minUniformBufferOffsetAlignment=256; };
  Properties properties() const { return {}; }
} device;
Device* vulkan_device=&device;
uint64_t current_float_constant_map_vertex_[4]={}, current_float_constant_map_pixel_[4]={};
uint32_t current_constant_buffers_up_to_date_=31, current_graphics_descriptor_set_values_up_to_date_=1;
VkDescriptorBufferInfo current_constant_buffer_infos_[5];
SpirvShaderTranslator::SystemConstants system_constants_;
struct { bool up_to_date=false; size_t address=0; } cbuffer_binding_float_pixel_;
uint32_t current_graphics_root_up_to_date_=~0u;
constexpr int root_parameter_float_constants_pixel=0, D3D12_CONSTANT_BUFFER_DATA_PLACEMENT_ALIGNMENT=256;
std::vector<uint8_t> vkbytes() { return pool.allocations.at(current_constant_buffer_infos_[2].buffer-1); }
std::vector<uint8_t> dxbytes() { return pool.allocations.at(cbuffer_binding_float_pixel_.address-1); }
float first(const std::vector<uint8_t>& bytes) { float x; std::memcpy(&x,bytes.data(),4); return x; }
'''

MAIN = r'''
int main() {
  Shader vertex, target, other, missing, empty;
  other.hash=7; missing.map.float_bitmap[0]=2; empty.map.float_bitmap[0]=0;
  empty.map.float_bitmap[3]=0; empty.map.float_count=0;
  for (unsigned i=0;i<2400;++i) regs[i]=0x3f000000u+i;
  float c0[4]={0.6f,0.4f,0.25f,0.75f}; std::memcpy(regs+1024,c0,16);
  const std::vector<uint32_t> saved(regs,regs+2400);
  const bool bypass=hdlred::Wanted();
  // Seed the same packed layout and original buffer; target must not reuse it in HD+.
  assert(vulkan(&vertex,&other)); auto original=vkbytes();
  size_t count=pool.allocations.size(); current_graphics_descriptor_set_values_up_to_date_=1;
  assert(vulkan(&vertex,&target)); auto result=vkbytes();
  assert(first(result)==(bypass ? 2.0f : 0.6f));
  assert(pool.allocations.size()==count+(bypass ? 1 : 0));
  if (bypass) {
    assert(!(current_graphics_descriptor_set_values_up_to_date_ & 1));
    assert(!(current_constant_buffers_up_to_date_ & 4));
  }
  auto expected=original; if (bypass) std::memcpy(expected.data(),&hdlred::kBypassThreshold,4);
  assert(result==expected); // c0.yzw and packed c255 bit-identical
  assert(vulkan(&vertex,&other)); assert(vkbytes()==original); // same-layout next draw restores
  count=pool.allocations.size(); assert(vulkan(&vertex,&other)); assert(count==pool.allocations.size());
  assert(vulkan(&vertex,&target)); assert(vulkan(&vertex,&target));
  assert(first(vkbytes())==(bypass ? 2.0f : 0.6f));
  assert(vulkan(&vertex,&missing)); assert(first(vkbytes())!=2.0f);
  assert(vulkan(&vertex,&empty)); assert(vulkan(&vertex,nullptr));
  assert(vulkan(&vertex,&target));
  // Execute Windows select + upload with identical registers, map and process environment.
  assert(d3d12(&target)); assert(dxbytes()==result);
  assert(d3d12(&other)); assert(dxbytes()==original);
  // Allocation failures must return false; retry must still upload and invalidate descriptors.
  current_constant_buffers_up_to_date_ &= ~4u; pool.fail=true;
  assert(!vulkan(&vertex,&target)); pool.fail=false; assert(vulkan(&vertex,&target));
  assert(std::equal(saved.begin(),saved.end(),regs));
  std::puts("RED_UPLOAD PASS bytes/cache/descriptor/restore/failure/D3D12-parity guest-unchanged");
}
'''


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--sdk', type=Path, default=ROOT / 'external/rexglue-sdk')
    ap.add_argument('--cxx', default='clang++')
    a = ap.parse_args()
    out = ROOT / 'private/work/linux_build/redcorr'
    out.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='upload-', dir=out) as folder:
        p = Path(folder)
        source = p / 'upload.cpp'
        source.write_text(program(a.sdk))
        for opt in ('-O0', '-O2'):
            exe = p / ('upload.exe' if os.name == 'nt' else 'upload')
            subprocess.run([a.cxx, '-std=c++17', opt, '-Wno-deprecated-declarations',
                            '-I' + str(ROOT / 'tools'), str(source), '-o', str(exe)], check=True)
            for mode in ('original', 'bypass', 'invalid'):
                env = dict(os.environ, R3HD_RED_CORRECTION=mode)
                for key in ('R3HD_RED_CORRECTION_AB', 'R3HD_FRAME_REQUEST', 'R3HD_NONINTRUSIVE'):
                    env.pop(key, None)
                print(opt, mode, flush=True)
                subprocess.run([str(exe.resolve())], env=env, check=True)


if __name__ == '__main__':
    main()
