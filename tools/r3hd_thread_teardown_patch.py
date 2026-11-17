"""Replay last in the chain: a guest thread still parked in its create-suspended start wait no longer blocks the
destruction of its host thread object on POSIX (LX-1, E-374; the Exit Game hang E-371).

Native evidence (LM-A N7, `lma_exit/stacks.log`): at Exit Game the main thread is in
`ReXApp::OnDestroy -> Runtime::Shutdown -> ~KernelState -> ObjectTable::Reset -> ~XThread -> ~PosixThread ->
~condition_variable -> pthread_cond_destroy`, while the guest thread of that XThread (`XThread7A42F6C0`) waits in
`PosixCondition<Thread>::ThreadStartRoutine -> condition_variable::wait`: the start wait of a thread created suspended
and never resumed. glibc's pthread_cond_destroy waits until every waiter has left the condition variable, so the
main thread blocks for ever (on Windows, closing the handle of a suspended thread never blocks).

The edit (src/core/threading_posix.cpp only, compiled on POSIX only; the Windows build is unchanged):
  * the start wait is marked in the same critical section that publishes kSuspended;
  * the destructor of PosixCondition<Thread>, while that wait is still pending, sets `start_abandoned_`, wakes the
    thread and joins it; the thread then returns without running its start routine (no handle can resume it once
    its object is destroyed, so the routine could never have run);
  * every other thread state keeps the existing destructor behaviour (nothing is cancelled or joined).
Tests: tools/linux/thread_teardown_test.py (the glibc mechanism and this protocol, under WSL or Linux) and
tools/r3hd_thread_teardown_regression.py (the patched SDK text after the chain).
"""
from m8_runtime_patch import patch_once

REL = 'src/core/threading_posix.cpp'

EDITS = [
    # 1. members, beside the other state_mutex_-protected fields
    ('  uint32_t suspend_count_;  // Protected by state_mutex_\n',
     '  uint32_t suspend_count_;  // Protected by state_mutex_\n'
     '  bool start_waiting_ = false;    // LX-1 (E-374): parked in the create-suspended start wait; state_mutex_\n'
     '  bool start_abandoned_ = false;  // LX-1: the object is being destroyed; leave without running; state_mutex_\n'),
    # 2. the destructor: release and join a thread still parked in its start wait
    ('  virtual ~PosixCondition() {\n'
     '    // Match Canary/Edge behavior.\n'
     '    // Force-cancel/join from the condition destructor can self-join/crash\n'
     '    // depending on shutdown ordering, so threads must be stopped explicitly.\n'
     '  }\n',
     '  virtual ~PosixCondition() {\n'
     '    // Match Canary/Edge behavior.\n'
     '    // Force-cancel/join from the condition destructor can self-join/crash\n'
     '    // depending on shutdown ordering, so threads must be stopped explicitly.\n'
     '    // LX-1 (E-374): a thread created suspended and never resumed still waits on state_signal_; destroying\n'
     '    // that condition variable under it blocks for ever in glibc. Release it (it returns without running its\n'
     '    // start routine) and join it. It never is the calling thread. Other states are left as they were.\n'
     '    bool abandon = false;\n'
     '    {\n'
     '      std::unique_lock<std::mutex> lock(state_mutex_);\n'
     '      if (start_waiting_) {\n'
     '        start_abandoned_ = true;\n'
     '        abandon = true;\n'
     '      }\n'
     '    }\n'
     '    if (abandon) {\n'
     '      state_signal_.notify_all();\n'
     '      pthread_join(thread_, nullptr);\n'
     '      thread_ = 0;\n'
     '    }\n'
     '  }\n'),
    # 3. mark the start wait where kSuspended is published
    ('    if (create_suspended) {\n'
     '      thread->handle_.suspend_count_ = 1;\n'
     '    }\n',
     '    if (create_suspended) {\n'
     '      thread->handle_.suspend_count_ = 1;\n'
     '      thread->handle_.start_waiting_ = true;  // LX-1 (E-374)\n'
     '    }\n'),
    # 4. the start wait also ends on abandonment; an abandoned thread leaves without running
    ('    thread->handle_.state_signal_.wait(lock,\n'
     '                                       [thread] { return thread->handle_.suspend_count_ == 0; });\n'
     '  }\n',
     '    thread->handle_.state_signal_.wait(lock, [thread] {\n'
     '      return thread->handle_.suspend_count_ == 0 || thread->handle_.start_abandoned_;\n'
     '    });\n'
     '    thread->handle_.start_waiting_ = false;\n'
     '    if (thread->handle_.start_abandoned_) {  // LX-1: the destructor joins this thread\n'
     '      current_thread_ = nullptr;\n'
     '      current_thread_condition_ = nullptr;\n'
     '      return nullptr;\n'
     '    }\n'
     '  }\n'),
]

if __name__ == '__main__':
    patch_once(REL, EDITS)
