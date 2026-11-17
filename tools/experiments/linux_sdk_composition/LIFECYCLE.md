# Isolated POSIX lifecycle fixture

**VERIFIED supplied-record/text audit at `6f81aa7`:** four Clang/GCC O0/O2
configurations pass the recorded lifecycle matrix and ordinary-rejection
sanitizers; object/final-ELF admission paths were reviewed on Windows. Root did
not execute Linux. This is a Linux x86-64 fixture, not a production signal manager
or general-purpose chaining implementation. See the report for the overall
CONDITIONAL PASS and the separate SDK fatal-reason gate.

The caller must exclusively control signal registration and quiesce all threads
that could enter, attach, detach, create callbacks or alter the signal action at
initialization and teardown. The mutex and attached-thread counter serialize
fixture lifecycle calls and make uninstall refuse while any participating thread
is attached. They do not prevent unrelated code from replacing the process action
or a later attach following teardown. Install accepts only `SIG_DFL`, saves its
complete action, and teardown checks that the fixture still owns the action before
restoring it. A replaced owner is left untouched. Teardown follows thread joins,
all detaches and all consumer/callback quiescence.

Each attached thread owns a guarded alternate stack and initial-exec TLS slot.
The handler admits only a synchronous `SEGV_ACCERR` at the exact read or write
leaf, expected address, operation and x86 page-fault access bits, and a complete
aligned four-byte arena range. It redirects only the saved instruction pointer
and returns through the original signal frame. No callback, lock, allocation,
filter, C++ throw or protection query runs on the normal admitted-return path
with an intact owned alternate stack/canary. Terminal
rejection resets SIGSEGV to default, unblocks it and re-raises; a fallback exit
code does not pass the subprocess signal judge. The store leaf is solely for
bounded watch repair and a fresh explicit operation, not guest-write record
delivery. No arbitrary interrupted instruction, SIGBUS, executable fault,
mapping race, dynamic TLS resolver or general prior-handler chain is supported.
The return-path finding assumes an intact alternate stack/canary: compiler-added
stack-check failure calls and terminal PLT loader state are not generally
certified async-signal-safe. The nested-fault case demonstrates masked kernel
termination; it does not prove successful nested handler invocation. Two workers
prove concurrent attachment/distinct slots, not forced overlap of signal handlers.

From the transfer root, on native CachyOS x86-64 with Clang, GCC, Python 3 and
binutils:

```sh
python3 tools/experiments/linux_sdk_composition/run_lifecycle.py --cc clang --cc gcc --repeats 20 --bench --out private/work/linux_sdk_composition/lifecycle
python3 tools/experiments/linux_sdk_composition/run_lifecycle.py --cc clang --cc gcc --repeats 2 --sanitize --out private/work/linux_sdk_composition/lifecycle_sanitizers
```

The runner builds only this fixture, checks process timeouts and exact SIGSEGV
termination, and records source/object/ELF hashes, compiler versions, commands,
subprocess outcomes and `objdump`/`readelf` output. Review final executable and
object handler call paths, exact read/write recovery sites, initial-exec TLS and
relocations on every compiler/optimization; machine-code dumps are evidence for
human review, not an automatic proof. The sanitizer mode exercises only ordinary
invalid-order and unattached-access rejection: ASan owns signal handling, and no
sanitizer result establishes kernel signal-frame recovery. The matrix does not
exercise SDK memory consumers or prove game compatibility.

Optional unsanitized O2 `--bench` batches measure 1,000 install/uninstall pairs,
100 guarded-stack attach/detach pairs, 10,000 successful checked reads and 1,000
protected read capture/return operations per repetition. Monotonic elapsed time
includes validation and complete named operations, with no subtraction; it does
not include SDK consumers or guest delivery. Twenty recorded batches per compiler
were audited; medians and environment limits appear in the milestone report.
