#define _GNU_SOURCE 1
#include "lrb_owner.h"
#include <errno.h>
#include <pthread.h>
#include <signal.h>
#include <stdint.h>
#include <stdlib.h>
#include <sys/mman.h>
#include <ucontext.h>
#include <unistd.h>

#if !defined(__linux__) || !defined(__x86_64__)
#error The LRB signal owner requires Linux x86-64.
#endif

int lrb_load_leaf(const void*, uint32_t*);
int lrb_store_leaf(void*, uint32_t);
#ifdef LRB_TEST
int lrb_wrong_leaf(const void*);
#endif
#ifdef LRB_RESTART
// LWR opt-in build only (../linux_write_watch_restart/lwr_restart.c).
int lwr_restart_admit(int sig, const void* info, const void* context);
#endif

// Signal-context state. Only volatile sig_atomic_t flags and plain words are
// touched by the handler; no locks, allocation, libc formatting or C++ code.
struct slot {
  volatile sig_atomic_t attached, armed, in_handler;
  uintptr_t base, intended;
  size_t size;
  enum lrb_operation operation;
  struct lrb_fault fault;
  void* mapping;
  size_t mapping_size;
  stack_t old_stack;
};
static _Thread_local struct slot slot __attribute__((tls_model("initial-exec")));
static pthread_mutex_t lifecycle_lock = PTHREAD_MUTEX_INITIALIZER;
static unsigned attached_count;
static int installed;
static struct sigaction previous;
static sigset_t fatal_set;

static int contains(uintptr_t base, size_t size, uintptr_t addr) {
  return size >= 4 && size - 1 <= UINTPTR_MAX - base && addr >= base &&
         addr - base <= size - 4;
}

static void terminate_signal(int sig) {
  static const struct sigaction action = { .sa_handler = SIG_DFL };
  (void)sigaction(sig, &action, NULL);
  (void)sigprocmask(SIG_UNBLOCK, &fatal_set, NULL);
  (void)raise(sig);
  _Exit(128 + sig);
}

void lrb_terminal(void) { terminate_signal(SIGSEGV); }

static void handler(int sig, siginfo_t* info, void* raw_context) {
  if (sig != SIGSEGV || !slot.attached || slot.in_handler)
    terminate_signal(sig);
  slot.in_handler = 1;
  ucontext_t* context = (ucontext_t*)raw_context;
#ifdef LRB_RESTART
  // LWR: outside an armed checked access, a verified store to a registered
  // write-watched page is unprotected and returns WITHOUT any context edit,
  // so the faulting instruction re-executes. Anything else falls through to
  // the unchanged fail-closed rules below.
  if (!slot.armed && lwr_restart_admit(sig, info, context)) {
    slot.in_handler = 0;
    return;
  }
#endif
  if (!slot.armed || !info || !context || info->si_code != SEGV_ACCERR ||
      (uintptr_t)info->si_addr != slot.intended ||
      !contains(slot.base, slot.size, slot.intended) || (slot.intended & 3))
    terminate_signal(sig);
  uintptr_t pc = (uintptr_t)context->uc_mcontext.gregs[REG_RIP];
  uintptr_t arg = (uintptr_t)context->uc_mcontext.gregs[REG_RDI];
  unsigned long error = (unsigned long)context->uc_mcontext.gregs[REG_ERR];
  int is_write = (error & 2u) != 0;
  if (arg != slot.intended || (error & 16u) ||
      (slot.operation == LRB_READ && (is_write || pc != (uintptr_t)lrb_read_site)) ||
      (slot.operation == LRB_WRITE && (!is_write || pc != (uintptr_t)lrb_write_site)) ||
      (slot.operation != LRB_READ && slot.operation != LRB_WRITE))
    terminate_signal(sig);
  slot.fault.signal_number = sig;
  slot.fault.signal_code = info->si_code;
  slot.fault.address = (uintptr_t)info->si_addr;
  slot.fault.instruction = pc;
  slot.fault.operation = slot.operation;
  ++slot.fault.count;
  slot.fault.on_altstack = (uintptr_t)&context >= (uintptr_t)slot.mapping &&
      (uintptr_t)&context - (uintptr_t)slot.mapping < slot.mapping_size;
  // Redirect to the recovery label: the access is NOT re-executed.
  context->uc_mcontext.gregs[REG_RIP] = (greg_t)(uintptr_t)
      (slot.operation == LRB_READ ? lrb_read_recover : lrb_write_recover);
  slot.armed = 0;  // A second fault before re-arming is terminal.
  slot.in_handler = 0;
}

int lrb_owns_sigsegv(void) {
  struct sigaction current;
  if (sigaction(SIGSEGV, NULL, &current)) return -1;
  return (current.sa_flags & SA_SIGINFO) && current.sa_sigaction == handler &&
         (current.sa_flags & SA_ONSTACK) ? 1 : 0;
}

int lrb_install(void) {
  int rc = pthread_mutex_lock(&lifecycle_lock);
  if (rc) return rc;
  if (installed) { pthread_mutex_unlock(&lifecycle_lock); return EALREADY; }
  struct sigaction current, action = {0};
  if (sigaction(SIGSEGV, NULL, &current)) { rc = errno; goto done; }
  if ((current.sa_flags & SA_SIGINFO) || current.sa_handler != SIG_DFL) { rc = EBUSY; goto done; }
  sigemptyset(&fatal_set);
  sigaddset(&fatal_set, SIGSEGV);
  action.sa_sigaction = handler;
  sigemptyset(&action.sa_mask);
  sigaddset(&action.sa_mask, SIGSEGV);
  sigaddset(&action.sa_mask, SIGBUS);
  action.sa_flags = SA_SIGINFO | SA_ONSTACK;
  if (sigaction(SIGSEGV, &action, &previous)) { rc = errno; goto done; }
  installed = 1;
done:
  pthread_mutex_unlock(&lifecycle_lock);
  return rc;
}

int lrb_uninstall(void) {
  int rc = pthread_mutex_lock(&lifecycle_lock);
  if (rc) return rc;
  if (!installed) { rc = EINVAL; goto done; }
  if (attached_count) { rc = EBUSY; goto done; }
  struct sigaction current;
  if (sigaction(SIGSEGV, NULL, &current)) { rc = errno; goto done; }
  if (!(current.sa_flags & SA_SIGINFO) || current.sa_sigaction != handler) {
    rc = EBUSY; goto done;
  }
  if (sigaction(SIGSEGV, &previous, NULL)) { rc = errno; goto done; }
  installed = 0;
done:
  pthread_mutex_unlock(&lifecycle_lock);
  return rc;
}

int lrb_installed(void) {
  if (pthread_mutex_lock(&lifecycle_lock)) return -1;
  const int value = installed;
  pthread_mutex_unlock(&lifecycle_lock);
  return value;
}

int lrb_attach(void) {
  int rc = pthread_mutex_lock(&lifecycle_lock);
  if (rc) return rc;
  if (!installed) { rc = EINVAL; goto done; }
  if (slot.attached) { rc = EALREADY; goto done; }
  stack_t current;
  if (sigaltstack(NULL, &current)) { rc = errno; goto done; }
  if (!(current.ss_flags & SS_DISABLE)) { rc = EBUSY; goto done; }
  long page = sysconf(_SC_PAGESIZE), minimum = sysconf(_SC_MINSIGSTKSZ);
  if (page <= 0 || minimum <= 0 || ((size_t)page & ((size_t)page - 1))) {
    rc = EINVAL; goto done;
  }
  size_t usable = 1024u * 1024u;
  if ((size_t)minimum > usable) usable = (size_t)minimum;
  if (usable > SIZE_MAX - 2 * (size_t)page) { rc = EOVERFLOW; goto done; }
  usable = (usable + (size_t)page - 1) & ~((size_t)page - 1);
  size_t total = usable + (size_t)page;
  void* map = mmap(NULL, total, PROT_READ | PROT_WRITE,
                   MAP_PRIVATE | MAP_ANONYMOUS, -1, 0);
  if (map == MAP_FAILED) { rc = errno; goto done; }
  if (mprotect(map, (size_t)page, PROT_NONE)) {  // Guard page below the stack.
    rc = errno; (void)munmap(map, total); goto done;
  }
  stack_t next = {0};
  next.ss_sp = (char*)map + page;
  next.ss_size = usable;
  if (sigaltstack(&next, &slot.old_stack)) {
    rc = errno; (void)munmap(map, total); goto done;
  }
  slot.mapping = map;
  slot.mapping_size = total;
  slot.armed = slot.in_handler = 0;
  slot.fault.count = 0;
  slot.fault.signal_number = 0;
  slot.attached = 1;
  ++attached_count;
done:
  pthread_mutex_unlock(&lifecycle_lock);
  return rc;
}

int lrb_detach(void) {
  int rc = pthread_mutex_lock(&lifecycle_lock);
  if (rc) return rc;
  if (!slot.attached) { rc = EINVAL; goto done; }
  if (slot.armed || slot.in_handler) { rc = EBUSY; goto done; }
  stack_t current;
  if (sigaltstack(NULL, &current)) { rc = errno; goto done; }
  if ((current.ss_flags & (SS_ONSTACK | SS_DISABLE)) || current.ss_size > slot.mapping_size ||
      current.ss_sp != (char*)slot.mapping + (slot.mapping_size - current.ss_size)) {
    rc = EBUSY; goto done;
  }
  if (sigaltstack(&slot.old_stack, NULL)) { rc = errno; goto done; }
  void* mapping = slot.mapping;
  size_t mapping_size = slot.mapping_size;
  slot.attached = 0;
  slot.mapping = NULL;
  slot.mapping_size = 0;
  --attached_count;
  if (munmap(mapping, mapping_size)) rc = errno;
done:
  pthread_mutex_unlock(&lifecycle_lock);
  return rc;
}

static enum lrb_status access32(void* arena, size_t size, void* address,
                                uint32_t* out, uint32_t value, enum lrb_operation op,
                                int wrong_site) {
  if (!slot.attached) return LRB_NOT_ATTACHED;
  uintptr_t base = (uintptr_t)arena, addr = (uintptr_t)address;
  if (slot.armed || slot.in_handler || !address || (op == LRB_READ && !out) ||
      (addr & 3) || !contains(base, size, addr)) return LRB_REJECTED;
  sigset_t set, old;
  sigemptyset(&set); sigaddset(&set, SIGSEGV); sigaddset(&set, SIGBUS);
  if (pthread_sigmask(SIG_BLOCK, &set, &old)) return LRB_REJECTED;
  if (sigismember(&old, SIGSEGV) != 0 || sigismember(&old, SIGBUS) != 0) {
    (void)pthread_sigmask(SIG_SETMASK, &old, NULL);
    return LRB_REJECTED;
  }
  slot.base = base; slot.size = size; slot.intended = addr; slot.operation = op;
  slot.fault.signal_number = 0;
  slot.armed = 1;
  if (pthread_sigmask(SIG_SETMASK, &old, NULL)) { slot.armed = 0; return LRB_REJECTED; }
  int failed;
#ifdef LRB_TEST
  if (wrong_site) failed = lrb_wrong_leaf(address);
  else
#else
  (void)wrong_site;
#endif
    failed = op == LRB_READ ? lrb_load_leaf(address, out) : lrb_store_leaf(address, value);
  if (pthread_sigmask(SIG_BLOCK, &set, &old)) return LRB_REJECTED;
  slot.armed = 0;
  if (pthread_sigmask(SIG_SETMASK, &old, NULL)) return LRB_REJECTED;
  return failed ? LRB_FAULT : LRB_OK;
}

enum lrb_status lrb_read32(const void* base, size_t size, const void* address, uint32_t* out) {
  return access32((void*)base, size, (void*)address, out, 0, LRB_READ, 0);
}
enum lrb_status lrb_write32(void* base, size_t size, void* address, uint32_t value) {
  return access32(base, size, address, NULL, value, LRB_WRITE, 0);
}
#ifdef LRB_TEST
void lrb_test_wrong_site(const void* base, size_t size, const void* address) {
  uint32_t value = 0;
  (void)access32((void*)base, size, (void*)address, &value, 0, LRB_READ, 1);
}
#endif
int lrb_last_fault(struct lrb_fault* out) {
  if (!out || !slot.attached || !slot.fault.signal_number) return 0;
  *out = slot.fault;
  return 1;
}
