// Fixture-only branch witnesses. The fault helper has returned before any
// witness is emitted; these paths run in ordinary C++ execution.
void test_terminal_mode(Fixture& fixture, const char* mode) {
  auto& state = *fixture.state;
  const std::string_view selected_mode(mode);

  if (selected_mode == "callback-failure") {
    const uintptr_t host = reinterpret_cast<uintptr_t>(fixture.mapping.base()) +
                           state.watched_ea;
    const uint32_t before = host_word(host);
    const unsigned access_before = state.access_callbacks;
    const unsigned invalidations_before = state.invalidations;
    const unsigned guest_before = state.guest_dispatches;
    const unsigned mmio_writes_before = state.mmio_writes;
    fixture.heap.EnableAccessCallbacks(state.watched_ea,
        static_cast<uint32_t>(fixture.page), true, false);
    check(fixture.query_protection(state.watched_ea, PageAccess::kReadOnly),
          "callback failure page is protected before its one store");
    check(!fixture.handler->CheckStore(state.watched_ea, 7) &&
              state.mmio_writes == mmio_writes_before,
          "callback failure store is declined by the real MMIO consumer");

    lsc_gate::Witness witness(lsc_gate::Mode::callback,
                              std::getenv("LSC_GATE_TOKEN"), access_before,
                              invalidations_before);
    witness.facts.attempts = 1;
    witness.facts.address = host;
    state.terminal_witness = &witness;
    state.fail_next_invalidation = true;
    const enum lsc_status status = lsc_write32(
        fixture.mapping.base(), fixture.mapping.size(),
        fixture.mapping.base() + state.watched_ea, 7);
    check(status == LSC_FAULT,
          "callback failure reaches one exact protected store fault");
    lsc_fault fault{};
    check(admitted_fault(state, host, LSC_WRITE, fault) && fault.count == 1,
          "callback failure fault has exact first-attempt provenance");
    witness.facts.faults = 1;
    check(host_word(host) == before,
          "callback failure store has no memory side effect");

    bool handled = false;
    bool caught_injected_failure = false;
    try {
      dispatch_sdk_access(*fixture.handler, fault.address, Operation::kWrite,
                          handled);
    } catch (const lsc_gate::InjectedInvalidation&) {
      caught_injected_failure = true;
    }
    check(caught_injected_failure && !handled && !state.fail_next_invalidation,
          "actual injected invalidator failure is caught after clearing its arm");
    check(state.access_callbacks == access_before + 1 &&
              state.invalidations == invalidations_before + 1 &&
              state.guest_dispatches == guest_before &&
              state.mmio_writes == mmio_writes_before && host_word(host) == before,
          "callback failure counters and memory remain exact before rejection");
    check(witness.consumers(state.access_callbacks, state.invalidations),
          "callback failure consumer deltas remain exact");
    witness.facts.caught = 1;
    check(witness.emit("caught"),
          "callback failure caught-phase witness");
    check(witness.emit("terminal"),
          "callback failure terminal-phase witness");
    state.terminal_witness = nullptr;
    lsc_terminal();
    check(false, "callback failure terminal signal unexpectedly returned");
  }

  if (selected_mode == "repair-failure") {
    const uintptr_t host = reinterpret_cast<uintptr_t>(fixture.mapping.base()) +
                           state.watched_ea;
    const uint32_t before = host_word(host);
    const unsigned access_before = state.access_callbacks;
    const unsigned invalidations_before = state.invalidations;
    const unsigned guest_before = state.guest_dispatches;
    const unsigned mmio_writes_before = state.mmio_writes;
    state.decline_write_repair = true;
    fixture.heap.EnableAccessCallbacks(state.watched_ea,
        static_cast<uint32_t>(fixture.page), true, false);
    check(fixture.query_protection(state.watched_ea, PageAccess::kReadOnly),
          "repair failure page is protected before its first store");
    check(!fixture.handler->CheckStore(state.watched_ea, 7) &&
              state.mmio_writes == mmio_writes_before,
          "repair failure store is declined by the real MMIO consumer");

    lsc_gate::Witness witness(lsc_gate::Mode::repair,
                              std::getenv("LSC_GATE_TOKEN"), access_before,
                              invalidations_before);
    witness.facts.attempts = 1;
    witness.facts.address = host;
    enum lsc_status status = lsc_write32(
        fixture.mapping.base(), fixture.mapping.size(),
        fixture.mapping.base() + state.watched_ea, 7);
    check(status == LSC_FAULT,
          "repair failure captures its first exact protected store");
    lsc_fault first_fault{};
    check(admitted_fault(state, host, LSC_WRITE, first_fault) &&
              first_fault.count == 1,
          "repair failure first store has exact provenance");
    witness.facts.faults = 1;
    check(host_word(host) == before,
          "repair failure first store has no memory side effect");

    bool handled = false;
    dispatch_sdk_access(*fixture.handler, first_fault.address, Operation::kWrite,
                        handled);
    check(handled && state.decline_write_repair &&
              fixture.query_protection(state.watched_ea, PageAccess::kReadOnly),
          "SDK callback claims the first fault while the page remains protected");
    check(state.access_callbacks == access_before + 1 &&
              state.invalidations == invalidations_before &&
              state.guest_dispatches == guest_before &&
              state.mmio_writes == mmio_writes_before && host_word(host) == before,
          "false repair callback has one callback and no invalidation or store effect");
    check(witness.consumers(state.access_callbacks, state.invalidations),
          "repair failure first consumer deltas are exact");
    check(witness.emit("claimed"),
          "repair failure claimed-phase witness");

    check(!fixture.handler->CheckStore(state.watched_ea, 7) &&
              state.mmio_writes == mmio_writes_before,
          "fresh repair attempt is again declined by the real MMIO consumer");
    witness.facts.attempts = 2;
    status = lsc_write32(fixture.mapping.base(), fixture.mapping.size(),
                         fixture.mapping.base() + state.watched_ea, 7);
    check(status == LSC_FAULT,
          "exactly one fresh store faults after the unsuccessful repair");
    lsc_fault retry_fault{};
    check(admitted_fault(state, host, LSC_WRITE, retry_fault) &&
              retry_fault.count == 2 &&
              retry_fault.address == first_fault.address &&
              retry_fault.instruction == first_fault.instruction &&
              retry_fault.operation == first_fault.operation,
          "repair retry has the same address, site and operation exactly once");
    witness.facts.faults = 2;
    check(host_word(host) == before &&
              state.access_callbacks == access_before + 1 &&
              state.invalidations == invalidations_before &&
              state.guest_dispatches == guest_before &&
              state.mmio_writes == mmio_writes_before,
          "single failed retry has no duplicate effect or extra consumer callback");
    check(witness.consumers(state.access_callbacks, state.invalidations),
          "repair failure retry consumer deltas remain exact");
    check(witness.emit("retry_fault"),
          "repair failure retry-phase witness");
    check(witness.emit("terminal"),
          "repair failure terminal-phase witness");
    lsc_terminal();
    check(false, "repair failure terminal signal unexpectedly returned");
  }

  if (selected_mode == "unhandled") {
    const uint32_t page = static_cast<uint32_t>(fixture.page);
    const uint32_t live_sp = static_cast<uint32_t>(fixture.mapping.size() - page);
    const uintptr_t host = reinterpret_cast<uintptr_t>(fixture.mapping.base());
    const uint32_t read_ea = 0;
    const unsigned access_before = state.access_callbacks;
    const unsigned invalidations_before = state.invalidations;
    const unsigned guest_before = state.guest_dispatches;
    const unsigned mmio_reads_before = state.mmio_reads;
    const unsigned mmio_writes_before = state.mmio_writes;
    check(fixture.heap.BaseHeap::Protect(0, page,
                                         rex::memory::kMemoryProtectNoAccess),
          "unhandled guest page starts inaccessible");
    check(fixture.query_protection(read_ea, PageAccess::kNoAccess),
          "unhandled guest page protection is confirmed");
    auto bytes = std::span<uint8_t>(fixture.mapping.base(), fixture.mapping.size());
    lgi::GuestArena arena{bytes, 8 * page, static_cast<uint32_t>(bytes.size()),
                         true, fixture.page,
                         reinterpret_cast<uintptr_t>(lsc_read_site)};
    lsc_gate::Witness witness(lsc_gate::Mode::unhandled,
                              std::getenv("LSC_GATE_TOKEN"), access_before,
                              invalidations_before);

    unsigned ordered_checks = 0;
    const std::array<lgi::Consumer, 1> consumers{{
        [&](const lgi::AccessRequest& request, uintptr_t) {
          ++ordered_checks;
          check(ordered_checks == 1 && request.effective_address == read_ea,
                "one real SDK CheckLoad consumer runs first for the guest read");
          uint32_t mmio_value = 0xfeedfaceu;
          const bool consumed = fixture.handler->CheckLoad(
              request.effective_address, &mmio_value);
          check(!consumed && mmio_value == 0xfeedfaceu,
                "real SDK CheckLoad declines the unhandled guest address");
          return lgi::ConsumerResult::Pass();
        }}};

    PPCContext guest{};
    guest.r1.u64 = fixture.mapping.size() - 0x100u;
    guest.fpscr.InitHost();
    unsigned backend_attempts = 0;
    unsigned filters = 0;
    unsigned cleanups = 0;
    std::vector<pgeh::Scope> scopes;
    scopes.push_back({kGuestPc, kGuestPc + 4, 0, {},
        [&](auto&, uint32_t) { ++cleanups; }});
    scopes.push_back({kGuestPc, kGuestPc + 4, kGuestLabel,
        lgi::wrap_filter([&](PPCContext&, const auto&, uint32_t) {
          ++filters;
          witness.facts.filters = filters;
          return 0;
        }), {}});
    pgeh::Owner owner(guest, std::move(scopes));
    owner.declare_label(kGuestLabel);
    const uint32_t selected = pgeh::region(owner, [&] {
      owner.set_pc(kGuestPc);
      owner.before_call();
      guest.r1.u64 = live_sp;
      const auto backend = [&](const void* address) {
        ++backend_attempts;
        check(backend_attempts == 1,
              "unhandled guest path performs exactly one backend capture");
        witness.facts.attempts = backend_attempts;
        uint32_t raw = 0xfeedfaceu;
        const auto status = lsc_read32(fixture.mapping.base(),
                                       fixture.mapping.size(), address, &raw);
        check(status == LSC_FAULT && raw == 0xfeedfaceu,
              "unhandled read has one exact fault with untouched output");
        lsc_fault fault{};
        check(admitted_fault(state, host, LSC_READ, fault) && fault.count == 1,
              "unhandled read fault has exact first-attempt provenance");
        witness.facts.faults = 1;
        witness.facts.address = fault.address;
        bool consumed = false;
        dispatch_sdk_access(*fixture.handler, fault.address, Operation::kRead,
                            consumed);
        check(!consumed,
              "real SDK access callback declines before guest exception delivery");
        check(state.access_callbacks == access_before + 1 &&
                  state.invalidations == invalidations_before &&
                  state.guest_dispatches == guest_before &&
                  state.mmio_reads == mmio_reads_before &&
                  state.mmio_writes == mmio_writes_before,
              "unhandled SDK callback has no repair, MMIO effect or duplicate dispatch");
        check(witness.consumers(state.access_callbacks, state.invalidations),
              "unhandled SDK consumer deltas are exact");
        ++state.guest_dispatches;
        return lgi::BackendResult::Fault(fault.address, fault.instruction, true);
      };
      uint32_t output = 0xdecafbadu;
      try {
        (void)lgi::checked_load32(
            arena, {read_ea, kGuestPc, 4, lgi::Operation::read}, live_sp,
            consumers, backend, output);
      } catch (const pgeh::Unhandled&) {
        check(ordered_checks == 1 && backend_attempts == 1 && filters == 1 &&
                  output == 0xdecafbadu &&
                  state.guest_dispatches == guest_before + 1 &&
                  state.access_callbacks == access_before + 1 &&
                  state.invalidations == invalidations_before &&
                  state.mmio_reads == mmio_reads_before &&
                  state.mmio_writes == mmio_writes_before && cleanups == 0 &&
                  !lgi::current_delivery && !lgi::access_dispatch_active,
              "unhandled search completed once with no acceptance, retry or cleanup");
        witness.facts.filters = filters;
        check(witness.emit("filter_search"),
              "unhandled filter-search witness after rejected search");
        witness.facts.caught = 1;
        check(witness.emit("caught"),
              "unhandled exception catch witness");
        check(witness.emit("terminal"),
              "unhandled terminal-phase witness");
        lsc_terminal();
        check(false, "unhandled terminal signal unexpectedly returned");
      }
      check(false, "unhandled checked access unexpectedly returned");
    });
    (void)selected;
    check(false, "unhandled owner unexpectedly accepted or returned");
  }

  check(false, "unsupported terminal diagnostic mode");
}
