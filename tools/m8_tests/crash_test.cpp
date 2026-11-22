// M8 crash-report regression fixture: `crash_test fault` dies on a null write with the reporter
// installed; `crash_test ok` exits normally; `crash_test heap` (D-311) dies on a null write with a heap object in
// r15 (level 1, which points to a level-2 object, which points to a level-3 object) and a file-mapping view in r14.
// Driven by tools/m8_crash_regression.py.
#include "m8_crash_report.h"
#include <cstdint>
#include <cstdio>
#include <cstring>

struct Node {
  uint64_t marker;
  Node* next;
  uint64_t pad[6];
};

// level1 (CRT heap) -> level2 -> level3, the last two far apart in one private allocation so no window of one
// reaches the other; only level1 is returned, so the deeper addresses live in heap memory only.
__declspec(noinline) static Node* Chain() {
  auto* region = static_cast<uint8_t*>(VirtualAlloc(nullptr, 0x40000, MEM_COMMIT | MEM_RESERVE, PAGE_READWRITE));
  auto* level2 = reinterpret_cast<Node*>(region + 0x8000);
  auto* level3 = reinterpret_cast<Node*>(region + 0x30000);
  level3->marker = 0x335645444C483352ull;  // "R3HLDEV3" in memory
  level2->marker = 0x325645444C483352ull;
  level2->next = level3;
  return new Node{0x315645444C483352ull, level2, {}};
}

static int Describe(char* out, int size) {
  return std::snprintf(out, size, "last_entered_function=fixture_function lr=82001234 sp=70001000\n");
}

int main(int argc, char** argv) {
  m8crash::Install(Describe);
  if (argc == 2 && !std::strcmp(argv[1], "ok")) return 0;
  if (argc == 2 && !std::strcmp(argv[1], "fault")) {
    volatile int* target = nullptr;
    *target = 1;
    return 3;  // not reached
  }
  if (argc == 2 && !std::strcmp(argv[1], "heap")) {
    Node* level1 = Chain();
    HANDLE mapping = CreateFileMappingW(INVALID_HANDLE_VALUE, nullptr, PAGE_READWRITE, 0, 0x10000, nullptr);
    auto* view = static_cast<uint64_t*>(MapViewOfFile(mapping, FILE_MAP_ALL_ACCESS, 0, 0, 0x10000));
    view[0x1000] = 0x5050414D4C483352ull;  // "R3HLMAPP": guest memory is a view like this one
    // The regression checks which of these addresses the dump covers (the marker values alone can also sit in
    // saved registers on the stack).
    std::printf("level1=%p level2=%p level3=%p mapped=%p\n", static_cast<void*>(level1),
                static_cast<void*>(level1->next), static_cast<void*>(level1->next->next),
                static_cast<void*>(view + 0x1000));
    std::fflush(stdout);
    __asm__ __volatile__(
        "movq %0, %%r15\n\t"
        "movq %1, %%r14\n\t"
        "xorl %%eax, %%eax\n\t"
        "movl %%eax, (%%rax)\n\t"
        :
        : "r"(level1), "r"(view + 0x1000)
        : "rax", "r14", "r15", "memory");
    return 3;  // not reached
  }
  return 2;
}
