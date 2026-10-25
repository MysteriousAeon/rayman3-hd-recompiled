#ifdef NDEBUG
#undef NDEBUG
#endif
#include <cassert>
#include "m6_test_input.h"
#undef NDEBUG
int main() {
  const char* path="m6_input_test_schedule.txt";
  { std::ofstream f(path); f << "100 40 1\n101 40 0\n200 44 1\n201 44 0\n300 26 1\n400 26 0\n"; }
  {
    m6input::Source src(path);
    assert(src.Sample(0).buttons == 0);
    auto query=src.Sample(150, false); assert(query.buttons == 0x10);
    auto press=src.Sample(150); assert(press.buttons == 0x10 && press.packet==query.packet);
    auto release=src.Sample(151); assert(release.buttons==0 && release.packet==press.packet+1);
    assert(src.Sample(250).buttons==0x1000); assert(src.Sample(251).buttons==0);
    auto move=src.Sample(350); assert(move.ly==32767);
    assert(src.Sample(399).packet==move.packet); assert(src.Sample(450).ly==0);
    { std::ofstream f(path, std::ios::app); f << "0 15 1"; }
    assert(src.Sample(500).buttons==0); // unfinished append must wait
    { std::ofstream f(path, std::ios::app); f << "\n0 15 0\n"; }
    assert(src.Sample(501).buttons==0x4000); assert(src.Sample(502).buttons==0);
    { std::ofstream f(path, std::ios::app); f << "0 300 -12000\n0 301 40000\n0 26 1\n0 44 2\n"; }
    auto analog=src.Sample(503); assert(analog.lx==-12000 && analog.ly==32767 && analog.buttons==0);
    { std::ofstream f(path, std::ios::app); f << "0 300 0\n0 301 0\n"; }
    auto digital=src.Sample(504); assert(digital.lx==0 && digital.ly==32767 && digital.packet==analog.packet+1);
  }
  assert(std::remove(path) == 0);
  { std::ifstream removed(path); assert(!removed.good()); }
  std::puts("M6 input PASS: null-query retention, edges, packets, axes, analog axes, partial/follow append");
}
