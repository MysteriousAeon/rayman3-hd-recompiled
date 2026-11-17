// Authored host bridge for the retained power-transition helix (D-218).
// No effect assets or translated guest implementation are embedded here.
#include "r3hd_swirl_policy.h"
#include "m2_trace.h"
#include <atomic>
#include <cstdlib>
#include <rex/logging.h>
#include <rex/ppc/context.h>
#include <rex/system/kernel_state.h>

extern "C" void __imp__sub_821E21B0(PPCContext&, uint8_t*);
extern "C" void sub_821E1CE8(PPCContext&, uint8_t*);
extern "C" void sub_8231A608(PPCContext&, uint8_t*);
extern "C" void sub_8231A6E0(PPCContext&, uint8_t*);
extern "C" void sub_821D1BE8(PPCContext&, uint8_t*);

namespace {
bool Enabled() { static const bool on = r3hd::swirl::Enabled(std::getenv("R3HD_POWER_SWIRL")); return on; }
bool Trace() { static const bool on = [] { auto p = std::getenv("R3HD_SWIRL_TRACE"); return p && !std::strcmp(p,"1"); }(); return on; }
uint32_t Load(const uint8_t* base, uint32_t a) { uint32_t v; std::memcpy(&v,base+a,4); return __builtin_bswap32(v); }
void Store(uint8_t* base, uint32_t a, uint32_t v) { v=__builtin_bswap32(v); std::memcpy(base+a,&v,4); }
float Float(const uint8_t* base, uint32_t a) { auto v=Load(base,a); float f; std::memcpy(&f,&v,4); return f; }
void Put(uint8_t* base, uint32_t a, const r3hd::swirl::Point& p) {
  for(unsigned i=0;i<3;++i) { uint32_t v;std::memcpy(&v,&p[i],4);Store(base,a+4*i,v); }
}
uint64_t Hash(const uint8_t* p, size_t n) { uint64_t h=14695981039346656037ull;for(size_t i=0;i<n;++i) h=(h^p[i])*1099511628211ull;return h; }
}  // namespace

void R3hdSwirlInitialize() { REXLOG_INFO("SWIRL power_swirl={}",Enabled()?"restored":"original"); }

// Replaces the weak alias, retaining the original entry and its instrumentation.
// Fixed profiles and Custom resolve the switch in the existing launcher registry.
extern "C" void sub_821E21B0(PPCContext& ctx, uint8_t* base) {
  __imp__sub_821E21B0(ctx,base);
  if (!Enabled() || uint32_t(ctx.lr)!=0x821E8688) return; // Vanilla: no guest reads or new submissions.
  const uint32_t old_sp=ctx.r1.u32;
  if (old_sp<0x20000 || !r3hd::swirl::Owns(uint32_t(ctx.lr),Load(base,old_sp+152))) return;
  // The world helper saved the particle owner's r31 at SP+144 (64-bit BE).
  // Require the exact native particle, not every user of the type14 renderer.
  const uint32_t particle=Load(base,old_sp+148);
  if(particle<0x82C21D80 || particle>=0x82C21D80+800*132 ||
     (particle-0x82C21D80)%132 || !r3hd::swirl::Owns(uint32_t(ctx.lr),Load(base,old_sp+152),Load(base,particle))) return;
  r3hd::swirl::Quad q{};
  const uint32_t corners[]={ctx.r27.u32,ctx.r26.u32,ctx.r25.u32,ctx.r24.u32};
  for(unsigned i=0;i<4;++i)for(unsigned j=0;j<3;++j)q[i][j]=Float(base,corners[i]+4*j);
  r3hd::swirl::Basis basis{};
  if(!r3hd::swirl::MakeBasis(q,basis)) { REXLOG_WARN("SWIRL rejected unexpected native quad"); return; }
  const uint32_t device=Load(base,0x829A45D0), material=ctx.r28.u32;
  const uint32_t color=Load(base,ctx.r31.u32+0x5A660);
  // Native helper uses a local matrix. Preserve both float-constant banks via
  // their native setters; invalidate native binding caches so following owners
  // re-establish shaders, resources, streams, blending and depth/stencil normally.
  PPCContext call=ctx;
  struct RestoreFaultContext {
    const char* function=m2_current_function;
    PPCContext* context=m2_current_context;
    ~RestoreFaultContext() { m2_current_function=function;m2_current_context=context; }
  } restore_fault_context;
  const uint32_t sp=old_sp-16384, saved=sp+256;
  call.r1.u64=sp;Store(base,sp,old_sp);
  Put(base,sp+80,basis.center);Put(base,sp+96,basis.x);Put(base,sp+112,basis.y);
  std::memcpy(base+saved,base+device+1920,8192);
  call.r3.u64=sp+80;call.r6.u64=color;call.r7.u64=sp+96;call.r8.u64=sp+112;
  call.f1.f64=1;call.f2.f64=1;
  sub_821E1CE8(call,base);
  for(unsigned bank=0;bank<2;++bank) {
    auto mask=r3hd::swirl::ChangedGroups(base+saved+bank*4096,base+device+1920+bank*4096);
    for(unsigned group=0;group<64;++group) {
      const uint64_t bit=uint64_t(1)<<(63-group);
      if(!(mask&bit)) continue;
      call.r3.u64=device;call.r4.u64=group*4;call.r5.u64=saved+bank*4096+group*64;
      call.r6.u64=4;call.r7.u64=bit;
      if(bank) sub_8231A6E0(call,base); else sub_8231A608(call,base);
    }
  }
  sub_821D1BE8(call,base);
  const bool constants_restored=std::memcmp(base+saved,base+device+1920,8192)==0;
  static std::atomic<bool> reported_failure{false};
  if(!constants_restored && !reported_failure.exchange(true)) REXLOG_ERROR("SWIRL constant restoration failed");
  static std::atomic<unsigned> count{0};auto n=++count;
  if(n==1) REXLOG_INFO("SWIRL native_quad submitted material={:08X}",material);
  if(Trace() && (n<=8 || !(n&(n-1)))) {
    const uint32_t texture=Load(base,material+104), resource=Load(base,texture+16);
    const uint32_t physical=r3hd::swirl::TextureBase(Load(base,resource+32));
    const uint32_t fetch=Load(base,device+1156)&0xFFFFF000;
    // Exact full native 32x32 DXT1 allocation, including padding. Diagnostics only;
    // no lookup/cache by filename and no replacement of mod-selected resources.
    uint64_t hash=0;
    if((Load(base,device+1156)&63)==18 && (Load(base,device+1160)&0x3FFFFFF)==0x3E01F && physical && physical<=0x1FFFE000)
      hash=Hash(REX_KERNEL_MEMORY()->physical_membase()+physical,8192);
    char name[97]={};std::memcpy(name,base+texture+0x4A,96);
    REXLOG_INFO("SWIRL trace n={} material={:08X} texture={} resource={:08X} physical={:08X} fetch={:08X} hash={:016X} packed={:08X} constants_restored={}",
      n,material,name,resource,physical,fetch,hash,color,constants_restored);
  }
}
