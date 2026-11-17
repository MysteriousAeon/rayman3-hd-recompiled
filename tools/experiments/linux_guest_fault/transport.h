// Isolated Linux x86-64 fault transport fixture. No production/runtime API.
#pragma once
#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

enum lgf_status {
  LGF_LOAD_OK = 0,
  LGF_LOAD_FAULT = 1,
  LGF_LOAD_REJECTED = 2,
  LGF_LOAD_MMIO_CONSUMED = 3,
  LGF_LOAD_WATCH_CONSUMED = 4,
  LGF_LOAD_NOT_ATTACHED = 5,
};
struct lgf_fault_info {
  int signal_number;
  int signal_code;
  uintptr_t address;
  uintptr_t instruction;
  unsigned count;
  int on_altstack;
};

// Call once before creating worker threads. Installs only when the current
// SIGSEGV disposition is SIG_DFL; refuses to replace another owner's handler.
int lgf_process_install(void);
// Every participating thread gets its own guarded alternate stack and TLS slot.
int lgf_thread_attach(void);
int lgf_thread_detach(void);
// Caller must join/quiesce every participating thread and detach all stacks
// before uninstall; the fixture has no global attachment tracker.
// Restores SIGSEGV to SIG_DFL.
int lgf_process_uninstall(void);

// The fixture's stand-in prior memory/MMIO handler. Its result is checked
// before arming fault capture, just as an existing consumer must get first say.
enum lgf_prior_result { LGF_PRIOR_PASS, LGF_PRIOR_MMIO, LGF_PRIOR_WATCH };
typedef enum lgf_prior_result (*lgf_prior_handler)(uintptr_t address,
                                                   uint32_t *value,
                                                   void *opaque);
void lgf_set_prior_handler(lgf_prior_handler handler, void *opaque);

// Handles only an aligned 4-byte read within the supplied guest arena. A captured
// hardware fault returns LGF_LOAD_FAULT; guest dispatch belongs to the caller.
enum lgf_status lgf_checked_load(const void *arena, size_t arena_size,
                                 const void *address, uint32_t *value);
int lgf_last_fault(struct lgf_fault_info *out);

// Exact assembly leaf: on a protected load it returns 1 without changing out.
int lgf_load32(const void *address, uint32_t *out);
extern const unsigned char lgf_load_site[];
extern const unsigned char lgf_load_recover[];

#ifdef LGF_TEST
// Negative-path controls are present only in the isolated subprocess fixture.
enum lgf_status lgf_test_wrong_site(const void *arena, size_t arena_size,
                                   const void *address, uint32_t *value);
void lgf_test_reentrant_mode(int enabled);
int lgf_wrong_load32(const void *address, uint32_t *out);
#endif

#ifdef __cplusplus
}
#endif
