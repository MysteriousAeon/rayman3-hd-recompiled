// Isolated Linux x86-64 executable ABI. No production runtime interface.
#pragma once
#include <stddef.h>
#include <stdint.h>
#ifdef __cplusplus
extern "C" {
#endif
enum lsc_status { LSC_OK, LSC_FAULT, LSC_REJECTED, LSC_NOT_ATTACHED };
enum lsc_operation { LSC_READ, LSC_WRITE };
struct lsc_fault {
  int signal_number, signal_code;
  uintptr_t address, instruction;
  enum lsc_operation operation;
  unsigned count;
  int on_altstack;
};
// Process-exclusive initialization/teardown: no concurrent sigaction users.
// Accept only SIG_DFL. No arbitrary prior-handler chaining.
int lsc_install(void);
int lsc_uninstall(void); // Refuse while ANY participating thread is attached.
int lsc_attach(void);    // Guarded per-thread altstack, initial-exec TLS.
int lsc_detach(void);    // Only outside access/handler; restore previous stack.
enum lsc_status lsc_read32(const void* arena, size_t size, const void* address, uint32_t* out);
// Store support is watch-only in composition, never guest-write exception delivery.
enum lsc_status lsc_write32(void* arena, size_t size, void* address, uint32_t value);
int lsc_last_fault(struct lsc_fault* out);
extern const unsigned char lsc_read_site[], lsc_read_recover[];
extern const unsigned char lsc_write_site[], lsc_write_recover[];
// Ordinary-code fail-closed policy after consumers decline or throw.
// Terminates with SIGSEGV default disposition; does not return.
void lsc_terminal(void);
#ifdef LSC_TEST
void lsc_test_reentrant(int enabled);
void lsc_test_wrong_site(const void* arena, size_t size, const void* address);
#endif
#ifdef __cplusplus
}
#endif
