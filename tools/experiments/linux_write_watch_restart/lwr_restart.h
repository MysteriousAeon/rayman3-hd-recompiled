// Linux Write-Watch Restart (LWR): opt-in restart admission for the single
// LRB SIGSEGV owner. Linux/glibc x86-64 only; isolated experiment, never part
// of the Windows release or of production runtime initialization.
//
// The LRB owner (lrb_owner.c, built with -DLRB_RESTART) calls
// lwr_restart_admit() for a fault that is not an armed LRB checked access. It
// admits exactly one kind of fault: a kernel SEGV_ACCERR user-mode write, by a
// decoded scalar `mov` store (lwr_decode.h) whose instruction lies inside an
// authorized code range, whose bytes lie entirely inside one page that this
// thread registered as SDK write-watched and that is still unclaimed. It then
// makes that page writable (raw mprotect syscall), records one claim in
// preallocated thread-local storage and returns 1. The LRB handler returns
// without editing the context, so the faulting instruction re-executes.
// Every other case returns 0 and the LRB owner terminates fail-closed.
//
// Ordinary code later drains the claims into the real SDK invalidation path
// (Memory::TriggerPhysicalMemoryCallbacks); nothing SDK-related runs in
// signal context.
#pragma once
#include <stddef.h>
#include <stdint.h>
#ifdef __cplusplus
extern "C" {
#endif

enum { LWR_MAX_PAGES = 8, LWR_MAX_RANGES = 8, LWR_MAX_CLAIMS = 8 };
enum lwr_page_state { LWR_PAGE_NONE = 0, LWR_PAGE_ARMED = 1, LWR_PAGE_CLAIMED = 2 };

struct lwr_range {
  uintptr_t begin, end;  // Host code [begin, end).
};

struct lwr_claim {
  uintptr_t page;         // Registered host page made writable.
  uintptr_t address;      // Kernel si_addr.
  uintptr_t effective;    // Decoded effective address of the store.
  uintptr_t instruction;  // Saved RIP (unchanged on return).
  unsigned width, length; // Store bytes, instruction bytes.
  unsigned range;         // Index of the authorized range holding RIP.
  unsigned long error;    // Saved page-fault error code.
  unsigned char before[8];  // Target bytes at fault time (store not yet committed).
};

// Ordinary code only. All return 0 on success or a positive errno value.
// Exactly one thread per process may hold an open session.
int lwr_open(void);       // Requires the LRB owner to own SIGSEGV; empty registry.
int lwr_close(void);      // Refused while authorized; clears the registry.
int lwr_register_page(const void* host_page);  // Page-aligned; becomes ARMED.
int lwr_authorize(const struct lwr_range* ranges, unsigned count);  // Opens the window.
int lwr_revoke(void);     // Closes the window.
int lwr_page_state(const void* host_page);   // enum lwr_page_state, or -1 if unregistered.
unsigned lwr_claim_count(void);
int lwr_get_claim(unsigned index, struct lwr_claim* out);

// Signal context only (called by the LRB owner). `info` and `context` are the
// kernel siginfo_t* and ucontext_t*; neither is modified.
int lwr_restart_admit(int sig, const void* info, const void* context);

#ifdef __cplusplus
}
#endif
