// Linux Runtime Bootstrap (LRB): exclusive POSIX SIGSEGV owner and checked
// 32-bit access transport. Linux/glibc x86-64 only. Opt-in experiment; not a
// production runtime interface and never used by the Windows release.
//
// Promoted from the audited linux_sdk_composition transport (6f81aa7/5e914a8)
// with unchanged admission rules: one armed access per thread, exact fault
// address, exact site label, exact read/write direction, SEGV_ACCERR only.
// Everything else terminates through the default SIGSEGV disposition.
#pragma once
#include <stddef.h>
#include <stdint.h>
#ifdef __cplusplus
extern "C" {
#endif
enum lrb_status { LRB_OK, LRB_FAULT, LRB_REJECTED, LRB_NOT_ATTACHED };
enum lrb_operation { LRB_READ, LRB_WRITE };
struct lrb_fault {
  int signal_number, signal_code;
  uintptr_t address, instruction;
  enum lrb_operation operation;
  unsigned count;  // Admitted faults on this thread since attach.
  int on_altstack;
};
// Process-exclusive lifecycle: no concurrent sigaction users. Install accepts
// only SIG_DFL (the SDK thunk must already be removed); no chaining.
int lrb_install(void);
int lrb_uninstall(void);  // Refuses while any thread is attached.
int lrb_installed(void);  // Ordinary-code query of the owner flag.
int lrb_attach(void);     // Guarded per-thread altstack, initial-exec TLS slot.
int lrb_detach(void);     // Only outside an access; restores the previous stack.
// The arena [base, base+size) bounds the admissible address; it is not a heap.
enum lrb_status lrb_read32(const void* base, size_t size, const void* address, uint32_t* out);
enum lrb_status lrb_write32(void* base, size_t size, void* address, uint32_t value);
int lrb_last_fault(struct lrb_fault* out);
extern const unsigned char lrb_read_site[], lrb_read_recover[];
extern const unsigned char lrb_write_site[], lrb_write_recover[];
// Ordinary-code fail-closed policy: default SIGSEGV disposition, raise, never returns.
void lrb_terminal(void);
// Ordinary-code query: 1 when the live SIGSEGV action is exactly this owner.
int lrb_owns_sigsegv(void);
#ifdef LRB_TEST
// Negative test only: arms an exact read, then faults from a non-admitted
// instruction. The owner must terminate in signal context.
void lrb_test_wrong_site(const void* base, size_t size, const void* address);
#endif
#ifdef __cplusplus
}
#endif
