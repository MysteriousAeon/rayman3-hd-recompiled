#include "m2_host/r3hd_swirl_policy.h"
#include <cstdio>
#include <limits>
#include <stdexcept>
using namespace r3hd::swirl;
int main() {
  unsigned n=0;
  auto require=[&](bool ok){++n;if(!ok) throw std::runtime_error("swirl policy regression");};
  require(!Enabled(nullptr));require(!Enabled("original"));require(!Enabled("1"));require(Enabled("restored"));
  require(Owns(0x821E8688,0x8218CC90));require(!Owns(0x821E8688,0x8218CE74));
  require(!Owns(0x821E8678,0x8218CC90));require(!Owns(0,0));
  require(!Owns(0x821E8688,0x8218CC90,0x1014));
  require(!Owns(0x821E8688,0x8218CC90,0x3013));
  require(TextureBase(0xFB069000)==0x1B06A000);
  require(TextureBase(0x1B069000)==0x1B069000);
  for(const auto& center: {Point{0,0,0},Point{141,-308,-104},Point{-2000,1000,80}}) {
    const Point x{.5f,.25f,.125f},y{0,0,-.75f};Quad q{};const int signs[][2]={{1,-1},{-1,-1},{-1,1},{1,1}};
    for(unsigned i=0;i<4;++i)for(unsigned j=0;j<3;++j)q[i][j]=center[j]+signs[i][0]*x[j]+signs[i][1]*y[j];
    Basis b{};require(MakeBasis(q,b));
    for(unsigned i=0;i<4;++i)for(unsigned j=0;j<3;++j) require(std::abs(q[i][j]-(b.center[j]+signs[i][0]*b.x[j]+signs[i][1]*b.y[j]))<.0001f);
    q[2][0]+=.1f;require(!MakeBasis(q,b));q[2][0]=std::numeric_limits<float>::quiet_NaN();require(!MakeBasis(q,b));
  }
  std::array<uint8_t,4096> a{},b{};require(ChangedGroups(a.data(),b.data())==0);
  b[0]=1;require(ChangedGroups(a.data(),b.data())==(uint64_t(1)<<63));
  b[4095]=1;require(ChangedGroups(a.data(),b.data())==((uint64_t(1)<<63)|1));
  b.fill(1);require(ChangedGroups(a.data(),b.data())==~uint64_t(0));
  std::printf("R3HD_SWIRL_TEST PASS checks=%u\n",n);
}
