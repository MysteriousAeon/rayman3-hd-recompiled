#define _GNU_SOURCE 1
#include "lwr_restart.h"

#include <errno.h>
#include <pthread.h>
#include <signal.h>
#include <stdatomic.h>
#include <stdint.h>
#include <sys/mman.h>
#include <sys/syscall.h>
#include <ucontext.h>
#include <unistd.h>

#include "lrb_owner.h"
#include "lwr_decode.h"

#if !defined(__linux__) || !defined(__x86_64__)
#error LWR requires Linux x86-64.
#endif
_Static_assert(SYS_mprotect == 10, "x86-64 Linux mprotect syscall number");
_Static_assert(sizeof(greg_t) == 8, "x86-64 greg_t");

// Thread-local session. The signal path reads the registry and range table,
// and writes only claim records and page states, all preallocated here. Access
// is %fs-relative (initial-exec/local-exec): no __tls_get_addr, no allocation.
struct session {
  volatile sig_atomic_t open, window;
  uintptr_t page_size;
  unsigned page_count, range_count;
  volatile unsigned claim_count;
  uintptr_t pages[LWR_MAX_PAGES];
  volatile sig_atomic_t state[LWR_MAX_PAGES];
  struct lwr_range ranges[LWR_MAX_RANGES];
  struct lwr_claim claims[LWR_MAX_CLAIMS];
};
static _Thread_local struct session s __attribute__((tls_model("initial-exec")));
static pthread_mutex_t lifecycle_lock = PTHREAD_MUTEX_INITIALIZER;
static int session_held;  // One session per process (ordinary code, under the lock).

// Linux x86-64 syscall ABI, no libc wrapper: errno is never written, nothing
// is resolved through the PLT, and no other state is touched. Returns 0 or -errno.
static LWR_ALWAYS_INLINE long raw_mprotect(uintptr_t address, uintptr_t length, long protection) {
  long result;
  __asm__ volatile("syscall"
                   : "=a"(result)
                   : "0"((long)SYS_mprotect), "D"(address), "S"(length), "d"(protection)
                   : "rcx", "r11", "memory");
  return result;
}

int lwr_restart_admit(int sig, const void* raw_info, const void* raw_context) {
  const siginfo_t* info = (const siginfo_t*)raw_info;
  const ucontext_t* context = (const ucontext_t*)raw_context;
  if (sig != SIGSEGV || !info || !context || !s.open || !s.window) return 0;
  // Kernel-generated protection fault only (kill/tgkill/sigqueue carry si_code <= 0).
  if (info->si_code != SEGV_ACCERR) return 0;
  const volatile greg_t* g = (const volatile greg_t*)context->uc_mcontext.gregs;
  // Page-fault error code exactly 7: protection violation on a PRESENT page,
  // user-mode data write. Rejects not-present (PROT_NONE/unpopulated),
  // instruction-fetch, reserved-bit and protection-key faults, so the
  // pre-store read below can never fault inside the handler.
  const unsigned long error = (unsigned long)g[REG_ERR];
  if (error != 7ul) return 0;
  const uintptr_t pc = (uintptr_t)g[REG_RIP];
  unsigned range = s.range_count;
  for (unsigned i = 0; i < s.range_count; ++i)
    if (pc >= s.ranges[i].begin && pc < s.ranges[i].end) { range = i; break; }
  if (range == s.range_count) return 0;
  uint64_t regs[16];
  regs[0] = (uint64_t)g[REG_RAX]; regs[1] = (uint64_t)g[REG_RCX];
  regs[2] = (uint64_t)g[REG_RDX]; regs[3] = (uint64_t)g[REG_RBX];
  regs[4] = (uint64_t)g[REG_RSP]; regs[5] = (uint64_t)g[REG_RBP];
  regs[6] = (uint64_t)g[REG_RSI]; regs[7] = (uint64_t)g[REG_RDI];
  regs[8] = (uint64_t)g[REG_R8];   regs[9] = (uint64_t)g[REG_R9];
  regs[10] = (uint64_t)g[REG_R10]; regs[11] = (uint64_t)g[REG_R11];
  regs[12] = (uint64_t)g[REG_R12]; regs[13] = (uint64_t)g[REG_R13];
  regs[14] = (uint64_t)g[REG_R14]; regs[15] = (uint64_t)g[REG_R15];
  uintptr_t avail = s.ranges[range].end - pc;
  if (avail > 15) avail = 15;
  struct lwr_store store;
  if (!lwr_decode_store((const unsigned char*)pc, (size_t)avail, regs, &store)) return 0;
  if (store.length > avail) return 0;
  const uintptr_t ea = (uintptr_t)store.effective, address = (uintptr_t)info->si_addr;
  if (ea > UINTPTR_MAX - (store.width - 1)) return 0;
  // The kernel fault address lies inside the decoded store, and the whole
  // store lies inside one page: no cross-page store is ever restarted.
  if (address < ea || address - ea >= store.width) return 0;
  const uintptr_t mask = ~(s.page_size - 1), page = ea & mask;
  if (((ea + store.width - 1) & mask) != page) return 0;
  unsigned k = s.page_count;
  for (unsigned i = 0; i < s.page_count; ++i)
    if (s.pages[i] == page) { k = i; break; }
  if (k == s.page_count || s.state[k] != LWR_PAGE_ARMED) return 0;
  const unsigned n = s.claim_count;
  if (n >= LWR_MAX_CLAIMS) return 0;
  // Record the target bytes before the store commits (page is readable).
  volatile struct lwr_claim* c = &s.claims[n];
  const volatile unsigned char* target = (const volatile unsigned char*)ea;
  for (unsigned j = 0; j < 8; ++j) c->before[j] = j < store.width ? target[j] : 0;
  if (raw_mprotect(page, s.page_size, PROT_READ | PROT_WRITE) != 0) return 0;
  c->page = page;
  c->address = address;
  c->effective = ea;
  c->instruction = pc;
  c->width = store.width;
  c->length = store.length;
  c->range = range;
  c->error = error;
  s.state[k] = LWR_PAGE_CLAIMED;  // A second fault on this page is terminal.
  s.claim_count = n + 1;
  return 1;
}

// ------------------------------------------------------------ ordinary code

static void clear_session(void) {
  s.window = 0;
  s.page_count = s.range_count = 0;
  s.claim_count = 0;
  for (unsigned i = 0; i < LWR_MAX_PAGES; ++i) { s.pages[i] = 0; s.state[i] = LWR_PAGE_NONE; }
  for (unsigned i = 0; i < LWR_MAX_RANGES; ++i) s.ranges[i].begin = s.ranges[i].end = 0;
}

int lwr_open(void) {
  int rc = pthread_mutex_lock(&lifecycle_lock);
  if (rc) return rc;
  const long page = sysconf(_SC_PAGESIZE);
  if (session_held || s.open) rc = EBUSY;
  else if (lrb_owns_sigsegv() != 1) rc = EPERM;
  else if (page != 4096) rc = EINVAL;
  else {
    clear_session();
    s.page_size = (uintptr_t)page;
    atomic_signal_fence(memory_order_seq_cst);
    s.open = 1;
    session_held = 1;
  }
  pthread_mutex_unlock(&lifecycle_lock);
  return rc;
}

int lwr_close(void) {
  int rc = pthread_mutex_lock(&lifecycle_lock);
  if (rc) return rc;
  if (!s.open) rc = EINVAL;
  else if (s.window) rc = EBUSY;
  else {
    s.open = 0;
    atomic_signal_fence(memory_order_seq_cst);
    clear_session();
    session_held = 0;
  }
  pthread_mutex_unlock(&lifecycle_lock);
  return rc;
}

int lwr_register_page(const void* host_page) {
  const uintptr_t page = (uintptr_t)host_page;
  if (!s.open) return EINVAL;
  if (s.window) return EBUSY;
  if (!page || (page & (s.page_size - 1))) return EINVAL;
  for (unsigned i = 0; i < s.page_count; ++i)
    if (s.pages[i] == page) return EEXIST;
  if (s.page_count >= LWR_MAX_PAGES) return ENOSPC;
  s.pages[s.page_count] = page;
  s.state[s.page_count] = LWR_PAGE_ARMED;
  atomic_signal_fence(memory_order_seq_cst);
  ++s.page_count;
  return 0;
}

int lwr_authorize(const struct lwr_range* ranges, unsigned count) {
  if (!s.open) return EINVAL;
  if (s.window) return EBUSY;
  if (!ranges || count == 0 || count > LWR_MAX_RANGES) return EINVAL;
  for (unsigned i = 0; i < count; ++i)
    if (ranges[i].begin == 0 || ranges[i].end <= ranges[i].begin) return EINVAL;
  for (unsigned i = 0; i < count; ++i) s.ranges[i] = ranges[i];
  s.range_count = count;
  atomic_signal_fence(memory_order_seq_cst);
  s.window = 1;
  atomic_signal_fence(memory_order_seq_cst);
  return 0;
}

int lwr_revoke(void) {
  if (!s.open || !s.window) return EINVAL;
  atomic_signal_fence(memory_order_seq_cst);
  s.window = 0;
  atomic_signal_fence(memory_order_seq_cst);
  return 0;
}

int lwr_page_state(const void* host_page) {
  for (unsigned i = 0; s.open && i < s.page_count; ++i)
    if (s.pages[i] == (uintptr_t)host_page) return (int)s.state[i];
  return -1;
}

unsigned lwr_claim_count(void) { return s.open ? s.claim_count : 0; }

int lwr_get_claim(unsigned index, struct lwr_claim* out) {
  if (!s.open || !out || index >= s.claim_count) return EINVAL;
  const volatile struct lwr_claim* c = &s.claims[index];
  out->page = c->page;
  out->address = c->address;
  out->effective = c->effective;
  out->instruction = c->instruction;
  out->width = c->width;
  out->length = c->length;
  out->range = c->range;
  out->error = c->error;
  for (unsigned j = 0; j < 8; ++j) out->before[j] = c->before[j];
  return 0;
}
