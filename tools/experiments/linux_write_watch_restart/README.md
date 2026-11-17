# Linux Write-Watch Restart (LWR)

**Status: CLOSED — bounded native PASS (2026-11-06).** Retry 1 (`7f39269`) passed on CachyOS
(Clang/GCC O0/O2) and was independently audited. Isolated, synthetic scope only. This is not
proof of POSIX async-signal-safety. Report:
[LINUX_WRITE_WATCH_RESTART_2026-11.md](../../../reports/LINUX_WRITE_WATCH_RESTART_2026-11.md).

An opt-in, isolated Linux x86-64 experiment. Real generated Rayman 3 HD stores fault on a
page that the real SDK write-watches. The single LRB signal owner unprotects that page
**without editing the saved context**. The same instruction then re-executes and completes.
Ordinary code afterwards publishes one invalidation per page through the real SDK path.

It reuses the following, unchanged in behaviour:
- the audited LRB bootstrap and owner (`../linux_runtime_bootstrap`);
- the LGE generated bodies (`../linux_guest_entry`, private extract, digest `c7e96852…`).

It does not use `rex::Runtime`, threads (except one negative mode), imports, files, GPU,
audio or input. It is not part of the Windows build or release.

## Files

| File | Role |
|---|---|
| `lwr_restart.{h,c}` | Thread-local session, registry and claims; `lwr_restart_admit` (signal context) |
| `lwr_decode.h` | Pure bounded decoder for `mov` stores (`88`/`89`, memory destination). Shared by signal context and self-tests |
| `../linux_runtime_bootstrap/lrb_owner.c` | One `#ifdef LRB_RESTART` hook. LRB and LGE never define it, so their objects stay byte-identical |
| `lwr_tests.cpp` | Real generated functions, real SDK watches, restart, drain, Windows-comparable records, traced modes |
| `lwr_probe.c`, `lwr_test_leaf.S` | Synthetic mechanism probe (no SDK, no generated code) and synthetic leaf stores |
| `lwr_gate.py`, `test_lwr_gate.py` | Windows reference, packages, native gate, evidence, audit; validator tests |

## Restart contract

The LRB handler reaches `lwr_restart_admit` only when no LRB checked access is armed. It
**admits** a fault only when all of the following hold:
1. SIGSEGV, `si_code == SEGV_ACCERR`, and the page-fault error code is exactly 7: a
   protection fault on a present page, user-mode data write. Not-present (`PROT_NONE`) faults
   are rejected before any memory read in the handler.
2. The thread has an open session and an open authorization window.
3. RIP lies inside one authorized code range: a generated function symbol from the ELF symbol
   table, or an explicitly synthetic leaf in negative and probe modes only.
4. The instruction decodes as an admitted scalar `mov` store of width 1, 2, 4 or 8.
5. `si_addr` lies inside `[EA, EA+width)`, and the whole store lies inside one page.
6. That page is registered by this thread and still ARMED. The claim array is not full.

On admission it:
- copies the pre-store target bytes;
- calls raw `syscall` `mprotect(page, 4096, PROT_READ|PROT_WRITE)`;
- records one claim and marks the page CLAIMED;
- returns 1.

The LRB handler then clears `in_handler` and returns, with no context edit. Every other fault
returns 0, and the unchanged LRB rules terminate fail-closed.

**Ordinary code** then revokes the window and verifies the claims. For each claimed page it
calls `Memory::TriggerPhysicalMemoryCallbacks(lock, page_va, 1, true, false, true)`. It never
uses the MMIO exception callback: that callback re-checks protection and silently skips an
already-writable page. It then unwatches unclaimed pages, closes the session and verifies that
every page is plain RW and unwatched again.

## Windows (development host)

```text
python tools/experiments/linux_write_watch_restart/test_lwr_gate.py
tools\devenv.bat python tools/experiments/linux_write_watch_restart/lwr_gate.py windows --repeats 5
python tools/experiments/linux_write_watch_restart/lwr_gate.py private-zip
python tools/experiments/linux_write_watch_restart/lwr_gate.py source --zip private/work/linux_write_watch_restart/lwr-cachyos-source.zip
```

The Windows build is ordinary-only. It produces the semantic reference with no watch and no
fault, and it never pretends to have produced a Linux fault.

## CachyOS procedure

See the report's **CachyOS execution** section for the exact commands. Inputs:
- the source ZIP;
- the existing, unchanged LGE private ZIP (`lge-private-generated.zip`);
- the LWR private reference ZIP.

The run uses the existing SDK checkout and install prefix. Nothing is fetched, patched or
installed.

## Not established

`rex::Runtime`/`Runtime::Setup` and the `initialize_seh()` ordering, multi-thread restart,
non-`mov` store forms (vector, `dcbz`, reservations, MMIO, RMW, string), cross-page or
unaligned-across-page stores, read watches, data providers, production drain placement,
whole-handler async-signal safety beyond the admitted path, full XSTATE, non-glibc or
non-x86-64 hosts, and a game.
