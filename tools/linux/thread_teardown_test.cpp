// LX-1 (E-374): the Exit Game hang mechanism and its fix, reduced to the protocol of the SDK's
// PosixCondition<Thread> (src/core/threading_posix.cpp after tools/r3hd_thread_teardown_patch.py).
//
// A host thread created suspended waits on a condition variable that is a member of its thread object. Exit Game
// destroys that object without resuming the thread. glibc's pthread_cond_destroy waits for every waiter to leave,
// so the destroying thread blocks for ever (the N7 stacks). The fixed destructor marks the start wait abandoned,
// wakes the thread (which returns without running its routine) and joins it.
//
//   thread_teardown_test original   -> blocks (the runner expects a timeout)
//   thread_teardown_test fixed      -> "THREAD_TEARDOWN fixed PASS ran=0" and exit 0
//   thread_teardown_test resumed    -> a resumed thread still runs its routine once: "... ran=1"
#include <pthread.h>

#include <condition_variable>
#include <cstdio>
#include <cstring>
#include <mutex>

static bool g_fixed = false;
static int g_ran = 0;

struct Handle {
  std::mutex state_mutex_;
  std::condition_variable state_signal_;
  unsigned suspend_count_ = 0;
  bool published_ = false;
  bool start_waiting_ = false;
  bool start_abandoned_ = false;
  pthread_t thread_{};

  ~Handle() {
    if (!g_fixed) return;  // the original destructor: nothing (members are then destroyed)
    bool abandon = false;
    {
      std::unique_lock<std::mutex> lock(state_mutex_);
      if (start_waiting_) {
        start_abandoned_ = true;
        abandon = true;
      }
    }
    if (abandon) {
      state_signal_.notify_all();
      pthread_join(thread_, nullptr);
      thread_ = 0;
    }
  }
};

static void* Start(void* p) {
  auto* h = static_cast<Handle*>(p);
  {
    std::unique_lock<std::mutex> lock(h->state_mutex_);
    h->suspend_count_ = 1;
    h->start_waiting_ = g_fixed;
    h->published_ = true;
    h->state_signal_.notify_all();
  }
  {
    std::unique_lock<std::mutex> lock(h->state_mutex_);
    h->state_signal_.wait(lock, [h] { return h->suspend_count_ == 0 || h->start_abandoned_; });
    h->start_waiting_ = false;
    if (h->start_abandoned_) return nullptr;
  }
  ++g_ran;  // the start routine
  return nullptr;
}

int main(int argc, char** argv) {
  const char* mode = argc > 1 ? argv[1] : "";
  g_fixed = !std::strcmp(mode, "fixed") || !std::strcmp(mode, "resumed");
  auto* h = new Handle;
  if (pthread_create(&h->thread_, nullptr, Start, h) != 0) return 2;
  {
    std::unique_lock<std::mutex> lock(h->state_mutex_);
    h->state_signal_.wait(lock, [h] { return h->published_; });
  }
  bool resumed = !std::strcmp(mode, "resumed");
  if (resumed) {
    {
      std::unique_lock<std::mutex> lock(h->state_mutex_);
      h->suspend_count_ = 0;
    }
    h->state_signal_.notify_all();
    pthread_t t = h->thread_;
    pthread_join(t, nullptr);  // the routine has finished; nothing waits on the condition variable
    h->start_waiting_ = false;
  }
  std::printf("THREAD_TEARDOWN %s destroying\n", mode);
  std::fflush(stdout);
  delete h;  // Exit Game: ~XThread -> ~PosixThread
  std::printf("THREAD_TEARDOWN %s PASS ran=%d\n", mode, g_ran);
  return 0;
}
