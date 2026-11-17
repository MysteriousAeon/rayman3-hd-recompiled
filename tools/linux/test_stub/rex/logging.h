// LM-1 host-test stub: lets SDK-free host tests include project headers that log through <rex/logging.h>.
// The arguments are consumed (not printed) so that -Wunused stays meaningful for the code under test.
#pragma once
template <typename... Args>
inline void rex_test_stub_log(Args&&...) {}
#define REXLOG_INFO(...) rex_test_stub_log(__VA_ARGS__)
