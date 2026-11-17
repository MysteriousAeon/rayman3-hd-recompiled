#define _GNU_SOURCE 1
#include "transport.h"

#include <errno.h>
#include <signal.h>
#include <pthread.h>
#include <stdint.h>
#include <stdlib.h>
#include <sys/mman.h>
#include <unistd.h>
#include <ucontext.h>

#if !defined(__linux__) || !defined(__x86_64__)
#error This isolated transport fixture supports Linux x86-64 only.
#endif

struct thread_slot {
  volatile sig_atomic_t armed;
  volatile sig_atomic_t in_handler;
  uintptr_t intended;
  uintptr_t arena;
  uint64_t arena_size;
  struct lgf_fault_info fault;
  lgf_prior_handler prior;
  void *prior_opaque;
  void *mapping;
  size_t mapping_size;
  stack_t old_stack;
  int attached;
#ifdef LGF_TEST
  volatile sig_atomic_t reentrant_test;
#endif
};
// The fixture is linked as a normal executable. This model is intentionally
// initial-exec so handler access cannot call a dynamic TLS resolver.
static _Thread_local struct thread_slot slot
    __attribute__((tls_model("initial-exec")));
static struct sigaction previous_segv;
static sigset_t fatal_segv_set;
static int process_installed;

static void die_with_signal(int sig) {
  static const struct sigaction default_action = { .sa_handler = SIG_DFL };
  (void)sigaction(sig, &default_action, 0);
  // SIGSEGV is masked automatically while its handler runs. Unblock it so the
  // default disposition is observed before leaving the signal frame.
  (void)sigprocmask(SIG_UNBLOCK, &fatal_segv_set, 0);
  (void)raise(sig);
  _Exit(128 + sig);
}

static int in_range(uintptr_t base, uint64_t size, uintptr_t address,
                    uint64_t width) {
  if (!size || size > (UINT64_C(1) << 32) || !width || width > size ||
      size - 1 > UINTPTR_MAX - base || address < base) return 0;
  return (uint64_t)(address - base) <= size - width;
}

static void fault_handler(int sig, siginfo_t *info, void *opaque) {
  if (sig != SIGSEGV || !slot.attached || slot.in_handler)
    die_with_signal(sig);
#ifdef LGF_TEST
  if (slot.reentrant_test) {
    // A deliberate second synchronous fault on the already guarded signal
    // stack. Linux must fail closed; this mode runs only in a child process.
    uint32_t sink = 0;
    (void)lgf_wrong_load32((const void *)(uintptr_t)0, &sink);
  }
#endif
  if (!slot.armed || !info || info->si_code != SEGV_ACCERR ||
      (uintptr_t)info->si_addr != slot.intended ||
      !in_range(slot.arena, slot.arena_size, (uintptr_t)info->si_addr, 4))
    die_with_signal(sig);

  ucontext_t *uc = (ucontext_t *)opaque;
  if (!uc || (uintptr_t)uc->uc_mcontext.gregs[REG_RIP] !=
                 (uintptr_t)lgf_load_site ||
      (uintptr_t)uc->uc_mcontext.gregs[REG_RDI] != slot.intended ||
      (uc->uc_mcontext.gregs[REG_ERR] & (2 | 16)) != 0)
    die_with_signal(sig);

  slot.in_handler = 1;
  slot.fault.signal_number = sig;
  slot.fault.signal_code = info->si_code;
  slot.fault.address = (uintptr_t)info->si_addr;
  slot.fault.instruction = (uintptr_t)uc->uc_mcontext.gregs[REG_RIP];
  slot.fault.on_altstack = (uintptr_t)&uc >= (uintptr_t)slot.mapping &&
      (uintptr_t)&uc - (uintptr_t)slot.mapping < slot.mapping_size;
  ++slot.fault.count;
  // Change exactly RIP. Leave the kernel-owned FP/XSTATE frame untouched;
  // rt_sigreturn restores GPRs, flags, signal mask, stack and FP/vector state.
  uc->uc_mcontext.gregs[REG_RIP] = (greg_t)(uintptr_t)lgf_load_recover;
  slot.armed = 0;
  slot.in_handler = 0;
}

int lgf_process_install(void) {
  if (process_installed) return 0;
  struct sigaction current;
  if (sigaction(SIGSEGV, 0, &current) != 0) return errno ? errno : EINVAL;
  if (current.sa_handler != SIG_DFL) return EBUSY;
  struct sigaction action = {0};
  action.sa_sigaction = fault_handler;
  sigemptyset(&action.sa_mask);
  sigaddset(&action.sa_mask, SIGSEGV);
  sigaddset(&action.sa_mask, SIGBUS);
  sigemptyset(&fatal_segv_set);
  sigaddset(&fatal_segv_set, SIGSEGV);
  action.sa_flags = SA_SIGINFO | SA_ONSTACK;
  if (sigaction(SIGSEGV, &action, &previous_segv) != 0)
    return errno ? errno : EINVAL;
  process_installed = 1;
  return 0;
}

int lgf_thread_attach(void) {
  if (!process_installed) return EINVAL;
  if (slot.attached) return EALREADY;
  stack_t current;
  if (sigaltstack(0, &current) != 0) return errno ? errno : EINVAL;
  if (!(current.ss_flags & SS_DISABLE)) return EBUSY;
  long page = sysconf(_SC_PAGESIZE);
  long dynamic_min = sysconf(_SC_MINSIGSTKSZ);
  if (page <= 0 || dynamic_min <= 0) return EINVAL;
  size_t usable = 1024u * 1024u;
  if ((size_t)dynamic_min > usable) usable = (size_t)dynamic_min;
  usable = (usable + (size_t)page - 1) & ~((size_t)page - 1);
  size_t total = usable + (size_t)page;
  void *mapping = mmap(0, total, PROT_READ | PROT_WRITE,
                       MAP_PRIVATE | MAP_ANONYMOUS, -1, 0);
  if (mapping == MAP_FAILED) return errno ? errno : ENOMEM;
  if (mprotect(mapping, (size_t)page, PROT_NONE) != 0) {
    int saved = errno; (void)munmap(mapping, total); return saved;
  }
  stack_t stack = {0};
  stack.ss_sp = (char *)mapping + page;
  stack.ss_size = usable;
  if (sigaltstack(&stack, &slot.old_stack) != 0) {
    int saved = errno; (void)munmap(mapping, total); return saved;
  }
  slot.mapping = mapping;
  slot.mapping_size = total;
  slot.attached = 1;
  slot.armed = 0;
  slot.in_handler = 0;
  slot.fault.count = 0;
  return 0;
}

int lgf_thread_detach(void) {
  if (!slot.attached) return EINVAL;
  if (slot.armed || slot.in_handler) return EBUSY;
  stack_t disabled = {0};
  disabled.ss_flags = SS_DISABLE;
  if (sigaltstack(&disabled, 0) != 0) return errno ? errno : EINVAL;
  if (sigaltstack(&slot.old_stack, 0) != 0) return errno ? errno : EINVAL;
  int rc = munmap(slot.mapping, slot.mapping_size) == 0 ? 0 : (errno ? errno : EINVAL);
  slot.attached = 0;
  slot.mapping = 0;
  slot.mapping_size = 0;
  return rc;
}

int lgf_process_uninstall(void) {
  if (!process_installed) return 0;
  if (slot.attached) return EBUSY;
  struct sigaction current;
  if (sigaction(SIGSEGV, 0, &current) != 0) return errno ? errno : EINVAL;
  if (current.sa_sigaction != fault_handler) return EBUSY;
  // Installation was accepted only over SIG_DFL, so restore that exact policy.
  if (sigaction(SIGSEGV, &previous_segv, 0) != 0) return errno ? errno : EINVAL;
  process_installed = 0;
  return 0;
}

void lgf_set_prior_handler(lgf_prior_handler handler, void *opaque) {
  slot.prior = handler;
  slot.prior_opaque = opaque;
}

static int checked_begin(uintptr_t arena, size_t arena_size,
                         uintptr_t address) {
  if (!slot.attached || !process_installed) return LGF_LOAD_NOT_ATTACHED;
  if (slot.armed || slot.in_handler || (address & 3) ||
      !in_range(arena, arena_size, address, 4))
    return LGF_LOAD_REJECTED;
  return LGF_LOAD_OK;
}

enum lgf_status lgf_checked_load(const void *arena, size_t arena_size,
                                 const void *address, uint32_t *value) {
  if (!address || !value) return LGF_LOAD_REJECTED;
  uintptr_t base = (uintptr_t)arena, addr = (uintptr_t)address;
  int begin = checked_begin(base, arena_size, addr);
  if (begin != LGF_LOAD_OK) return (enum lgf_status)begin;
  if (slot.prior) {
    enum lgf_prior_result prior = slot.prior(addr, value, slot.prior_opaque);
    if (prior == LGF_PRIOR_MMIO) return LGF_LOAD_MMIO_CONSUMED;
    if (prior == LGF_PRIOR_WATCH) return LGF_LOAD_WATCH_CONSUMED;
    if (prior != LGF_PRIOR_PASS) return LGF_LOAD_REJECTED;
  }
  sigset_t set, old;
  sigemptyset(&set); sigaddset(&set, SIGSEGV); sigaddset(&set, SIGBUS);
  if (pthread_sigmask(SIG_BLOCK, &set, &old) != 0) return LGF_LOAD_REJECTED;
  if (sigismember(&old, SIGSEGV) == 1 || sigismember(&old, SIGBUS) == 1) {
    (void)pthread_sigmask(SIG_SETMASK, &old, 0);
    return LGF_LOAD_REJECTED;
  }
  slot.intended = addr;
  slot.arena = base;
  slot.arena_size = arena_size;
  slot.fault.signal_number = 0;
  slot.fault.signal_code = 0;
  slot.fault.address = 0;
  slot.fault.instruction = 0;
  slot.fault.on_altstack = 0;
  slot.armed = 1;
  if (pthread_sigmask(SIG_SETMASK, &old, 0) != 0) {
    slot.armed = 0;
    return LGF_LOAD_REJECTED;
  }
  int failed = lgf_load32(address, value);
  if (pthread_sigmask(SIG_BLOCK, &set, &old) != 0) return LGF_LOAD_REJECTED;
  slot.armed = 0;
  if (pthread_sigmask(SIG_SETMASK, &old, 0) != 0) return LGF_LOAD_REJECTED;
  return failed ? LGF_LOAD_FAULT : LGF_LOAD_OK;
}

int lgf_last_fault(struct lgf_fault_info *out) {
  if (!out || !slot.attached) return 0;
  *out = slot.fault;
  return out->signal_number != 0;
}

#ifdef LGF_TEST
enum lgf_status lgf_test_wrong_site(const void *arena, size_t arena_size,
                                   const void *address, uint32_t *value) {
  if (!address || !value || checked_begin((uintptr_t)arena, arena_size,
                                          (uintptr_t)address) != LGF_LOAD_OK)
    return LGF_LOAD_REJECTED;
  sigset_t set, old;
  sigemptyset(&set); sigaddset(&set, SIGSEGV); sigaddset(&set, SIGBUS);
  if (pthread_sigmask(SIG_BLOCK, &set, &old) != 0) return LGF_LOAD_REJECTED;
  if (sigismember(&old, SIGSEGV) == 1 || sigismember(&old, SIGBUS) == 1) {
    (void)pthread_sigmask(SIG_SETMASK, &old, 0);
    return LGF_LOAD_REJECTED;
  }
  slot.intended = (uintptr_t)address;
  slot.arena = (uintptr_t)arena;
  slot.arena_size = arena_size;
  slot.armed = 1;
  if (pthread_sigmask(SIG_SETMASK, &old, 0) != 0) return LGF_LOAD_REJECTED;
  return lgf_wrong_load32(address, value);
}
void lgf_test_reentrant_mode(int enabled) {
  slot.reentrant_test = enabled ? 1 : 0;
}
#endif
