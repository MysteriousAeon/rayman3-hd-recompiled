// LWR synthetic owner probe: the LRB owner (built with LRB_RESTART) plus the
// LWR admission path on anonymous pages and synthetic leaf stores. No SDK, no
// generated or game code. It isolates the signal mechanism (fault, raw
// mprotect, claim, restart without context edit) from the SDK integration
// that lwr_tests exercises with real generated functions.
//
// Usage: lwr_probe positive | lwr_probe <negative-mode>
// positive exits 0 with "LWR_PROBE PASS ..."; a negative mode prints one
// "LWR_PROBE begin mode=<m> address=0x..." line to stderr and must then die
// by SIGSEGV through the owner's terminal path.
#define _GNU_SOURCE 1
#include <errno.h>
#include <pthread.h>
#include <signal.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <sys/resource.h>
#include <unistd.h>

#include "lrb_owner.h"
#include "lwr_restart.h"

void lwr_leaf_store8(void* p, unsigned v);
void lwr_leaf_store32(void* p_minus_4, uint32_t v);
void lwr_leaf_store64(void* base, uint64_t v, uintptr_t index);
void lwr_leaf_store128(void* p);
uint32_t lwr_leaf_load32(const void* p);
extern const unsigned char lwr_leaf_store8_end[], lwr_leaf_store32_end[], lwr_leaf_store64_end[],
    lwr_leaf_store128_end[], lwr_leaf_load32_end[];

static unsigned checks;
static void require(int ok, const char* what) {
  ++checks;
  if (!ok) {
    fprintf(stderr, "LWR_PROBE FAIL: %s\n", what);
    exit(2);
  }
}

enum { kPage = 4096, kPages = 4 };
static unsigned char* g_map;

static struct lwr_range leaf(void (*b)(void), const unsigned char* e) {
  struct lwr_range r = {(uintptr_t)b, (uintptr_t)e};
  return r;
}

static void protect(unsigned page, int prot) {
  require(mprotect(g_map + page * kPage, kPage, prot) == 0, "test mprotect");
}

static void begin(const char* mode, const void* address) {
  fprintf(stderr, "LWR_PROBE begin mode=%s address=%p\n", mode, address);
  fflush(stderr);
}

static void setup(void) {
  const struct rlimit no_core = {0, 0};
  require(setrlimit(RLIMIT_CORE, &no_core) == 0, "no core dumps");
  require(lrb_install() == 0 && lrb_attach() == 0 && lrb_owns_sigsegv() == 1, "LRB owner installed and attached");
  g_map = mmap(NULL, kPages * kPage, PROT_READ | PROT_WRITE, MAP_PRIVATE | MAP_ANONYMOUS, -1, 0);
  require(g_map != MAP_FAILED, "anonymous pages");
  for (unsigned i = 0; i < kPages * kPage; ++i) g_map[i] = (unsigned char)(i * 7 + 3);
}

static void teardown(void) {
  require(munmap(g_map, kPages * kPage) == 0, "unmap");
  require(lrb_detach() == 0 && lrb_uninstall() == 0 && lrb_owns_sigsegv() == 0, "owner removed");
}

static void positive(void) {
  require(lwr_open() == 0, "open session");
  require(lwr_open() == EBUSY, "second open refused");
  protect(1, PROT_READ);
  protect(2, PROT_READ);
  require(lwr_register_page(g_map + kPage) == 0 && lwr_register_page(g_map + 2 * kPage) == 0, "register");
  require(lwr_register_page(g_map + kPage) == EEXIST && lwr_register_page(g_map + 1) == EINVAL,
          "duplicate/unaligned registration refused");
  const struct lwr_range ranges[3] = {leaf((void (*)(void))lwr_leaf_store8, lwr_leaf_store8_end),
                                      leaf((void (*)(void))lwr_leaf_store32, lwr_leaf_store32_end),
                                      leaf((void (*)(void))lwr_leaf_store64, lwr_leaf_store64_end)};
  require(lwr_authorize(ranges, 3) == 0, "authorize leaf ranges");
  require(lwr_register_page(g_map + 3 * kPage) == EBUSY && lwr_close() == EBUSY, "no change while authorized");
  unsigned char* p1 = g_map + kPage + 0x10;
  const unsigned char old1[4] = {p1[0], p1[1], p1[2], p1[3]};
  lwr_leaf_store32(p1 - 4, 0xA1B2C3D4u);  // Faults once, page unprotected, store re-executes.
  require(memcmp(p1, &(uint32_t){0xA1B2C3D4u}, 4) == 0, "restarted 32-bit store committed");
  lwr_leaf_store8(g_map + kPage + 0xFFF, 0x5Au);  // Same page: already writable, no fault.
  require(g_map[kPage + 0xFFF] == 0x5A, "repeated store after restart");
  unsigned char* p2 = g_map + 2 * kPage + 0xFF8;  // Last 8 bytes of page 2 (boundary-adjacent).
  lwr_leaf_store64(g_map, 0x0102030405060708ull, (uintptr_t)(p2 - g_map));
  require(memcmp(p2, &(uint64_t){0x0102030405060708ull}, 8) == 0, "restarted 64-bit store committed");
  require(lwr_revoke() == 0, "revoke");
  require(lwr_claim_count() == 2, "exactly one claim per written page");
  struct lwr_claim c;
  require(lwr_get_claim(0, &c) == 0 && c.page == (uintptr_t)(g_map + kPage) && c.address == (uintptr_t)p1 &&
              c.effective == (uintptr_t)p1 && c.instruction == (uintptr_t)lwr_leaf_store32 && c.width == 4 &&
              c.length == 3 && c.range == 1 && c.error == 7 && memcmp(c.before, old1, 4) == 0,
          "claim 0 identity (site, address, width, pre-store bytes)");
  require(lwr_get_claim(1, &c) == 0 && c.page == (uintptr_t)(g_map + 2 * kPage) && c.address == (uintptr_t)p2 &&
              c.effective == (uintptr_t)p2 && c.instruction == (uintptr_t)lwr_leaf_store64 && c.width == 8 &&
              c.length == 4 && c.range == 2,
          "claim 1 identity");
  require(lwr_page_state(g_map + kPage) == LWR_PAGE_CLAIMED && lwr_page_state(g_map + 2 * kPage) == LWR_PAGE_CLAIMED &&
              lwr_page_state(g_map) == -1,
          "page states");
  require(g_map[0] == 3 && g_map[3 * kPage] == (unsigned char)(3 * kPage * 7 + 3), "unrelated pages untouched");
  require(lwr_close() == 0 && lwr_claim_count() == 0 && lwr_page_state(g_map + kPage) == -1, "close clears");
  require(lwr_revoke() == EINVAL, "revoke after close refused");
}

struct foreign {
  pthread_mutex_t lock;
  pthread_cond_t cond;
  int ready;
};
static struct foreign g_foreign = {PTHREAD_MUTEX_INITIALIZER, PTHREAD_COND_INITIALIZER, 0};

static void* foreign_session(void* arg) {
  (void)arg;
  const struct lwr_range r = leaf((void (*)(void))lwr_leaf_store32, lwr_leaf_store32_end);
  require(lwr_open() == 0 && lwr_register_page(g_map + kPage) == 0 && lwr_authorize(&r, 1) == 0,
          "foreign thread holds the session");
  pthread_mutex_lock(&g_foreign.lock);
  g_foreign.ready = 1;
  pthread_cond_signal(&g_foreign.cond);
  pthread_mutex_unlock(&g_foreign.lock);
  for (;;) pause();
  return NULL;
}

static void negative(const char* mode) {
  const struct lwr_range r32 = leaf((void (*)(void))lwr_leaf_store32, lwr_leaf_store32_end);
  unsigned char* p = g_map + kPage + 0x20;
  protect(1, PROT_READ);
  if (strcmp(mode, "foreign-thread") == 0) {
    pthread_t t;
    require(pthread_create(&t, NULL, foreign_session, NULL) == 0, "start foreign thread");
    pthread_mutex_lock(&g_foreign.lock);
    while (!g_foreign.ready) pthread_cond_wait(&g_foreign.cond, &g_foreign.lock);
    pthread_mutex_unlock(&g_foreign.lock);
    require(lwr_open() == EBUSY, "session belongs to the other thread");
    begin(mode, p);
    lwr_leaf_store32(p - 4, 1);
    return;
  }
  require(lwr_open() == 0, "open session");
  if (strcmp(mode, "unregistered") == 0) {
    require(lwr_authorize(&r32, 1) == 0, "authorize");
    begin(mode, p);
    lwr_leaf_store32(p - 4, 1);
    return;
  }
  require(lwr_register_page(g_map + kPage) == 0, "register");
  if (strcmp(mode, "unauthorized") == 0) {
    begin(mode, p);
    lwr_leaf_store32(p - 4, 1);
    return;
  }
  if (strcmp(mode, "after-close") == 0) {
    require(lwr_authorize(&r32, 1) == 0 && lwr_revoke() == 0 && lwr_close() == 0, "session released");
    begin(mode, p);
    lwr_leaf_store32(p - 4, 1);
    return;
  }
  if (strcmp(mode, "signal-origin") == 0) {
    require(lwr_authorize(&r32, 1) == 0, "authorize");
    begin(mode, p);
    raise(SIGSEGV);
    return;
  }
  if (strcmp(mode, "consumed") == 0) {
    require(lwr_authorize(&r32, 1) == 0, "authorize");
    lwr_leaf_store32(p - 4, 1);
    require(lwr_revoke() == 0 && lwr_claim_count() == 1, "first fault admitted");
    protect(1, PROT_READ);  // Stands for a later re-watch of the same page.
    require(lwr_authorize(&r32, 1) == 0, "fresh window, page not re-armed");
    begin(mode, p);
    lwr_leaf_store32(p - 4, 2);
    return;
  }
  if (strcmp(mode, "wrong-site") == 0) {
    const struct lwr_range r8 = leaf((void (*)(void))lwr_leaf_store8, lwr_leaf_store8_end);
    require(lwr_authorize(&r8, 1) == 0, "authorize the 8-bit leaf only");
    begin(mode, p);
    lwr_leaf_store32(p - 4, 1);
    return;
  }
  if (strcmp(mode, "host-store") == 0) {
    require(lwr_authorize(&r32, 1) == 0, "authorize");
    begin(mode, p);
    *(volatile unsigned char*)p = 1;  // Compiled host code, not an authorized site.
    return;
  }
  if (strcmp(mode, "read") == 0) {
    const struct lwr_range rl = leaf((void (*)(void))lwr_leaf_load32, lwr_leaf_load32_end);
    protect(1, PROT_NONE);
    require(lwr_authorize(&rl, 1) == 0, "authorize the load leaf");
    begin(mode, p);
    (void)lwr_leaf_load32(p);
    return;
  }
  if (strcmp(mode, "cross-page") == 0) {
    unsigned char* split = g_map + 2 * kPage - 2;  // Bytes 2 in page 1 (watched), 2 in page 2.
    require(lwr_authorize(&r32, 1) == 0, "authorize");
    begin(mode, split);
    lwr_leaf_store32(split - 4, 1);
    return;
  }
  if (strcmp(mode, "wide") == 0) {
    const struct lwr_range rw = leaf((void (*)(void))lwr_leaf_store128, lwr_leaf_store128_end);
    require(lwr_authorize(&rw, 1) == 0, "authorize the 128-bit leaf");
    begin(mode, p);
    lwr_leaf_store128(p);
    return;
  }
  require(0, "unknown mode");
}

int main(int argc, char** argv) {
  require(argc == 2, "one mode");
  setup();
  if (strcmp(argv[1], "positive") == 0) {
    positive();
    teardown();
    printf("LWR_PROBE PASS claims=2 checks=%u\n", checks);
    return 0;
  }
  negative(argv[1]);
  fprintf(stderr, "LWR_PROBE FAIL: negative mode returned\n");
  return 3;
}
