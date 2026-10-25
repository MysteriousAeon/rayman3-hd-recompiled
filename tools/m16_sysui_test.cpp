// M16 (D-044) regression for the system-UI input gate (tools/m16_sysui.h): the transition function that decides
// whether the title sees the pad while a host dialog stands in for a console system UI, and when a press asks
// that dialog to close. Pure logic; no runtime is started.
#include <rex/m16_sysui.h>
#include <cstdio>
using m16sysui::Action;
int main() {
  int checks = 0, failures = 0;
  auto check = [&](bool ok, const char* what) {
    ++checks;
    if (!ok) { ++failures; std::printf("FAIL: %s\n", what); }
  };
  const uint16_t A = 0x1000, B = 0x2000, START = 0x0010, BACK = 0x0020, X = 0x4000, UP = 0x0001;

  {  // closed, never opened: everything passes
    m16sysui::State s;
    check(Step(s, 0) == Action::kPass, "idle neutral passes");
    check(Step(s, A) == Action::kPass, "idle A passes");
    check(Step(s, B | UP) == Action::kPass, "idle B+up passes");
    check(!s.open && !s.armed && !s.closing && !s.drain, "idle state unchanged");
  }
  {  // the confirming A is still held when the dialog opens: hidden, and it does not close the dialog
    m16sysui::State s;
    Open(s);
    check(s.open && !s.armed && !s.drain, "open state");
    check(Step(s, A) == Action::kHide, "held A hidden");
    check(Step(s, A) == Action::kHide, "held A hidden again");
    check(!s.armed && !s.closing, "held A does not arm or close");
    check(Step(s, 0) == Action::kHide, "release hidden");
    check(s.armed, "release arms");
    check(Step(s, UP) == Action::kHide, "direction hidden");
    check(Step(s, X) == Action::kHide, "X hidden, not a close button");
    check(!s.closing, "no close yet");
    check(Step(s, B) == Action::kHideAndClose, "B closes");
    check(s.closing, "closing latched");
    check(Step(s, B) == Action::kHide, "B held: one close request only");
    check(Step(s, 0) == Action::kHide, "still hidden until the dialog reports closed");
    Closed(s);
    check(!s.open && s.drain && !s.armed && !s.closing, "closed state drains");
    check(Step(s, 0) == Action::kPass, "neutral after close passes and ends the drain");
    check(!s.drain, "drain ended");
    check(Step(s, B) == Action::kPass, "next B belongs to the title");
  }
  {  // the closing press is still down when the dialog has gone: it must not reach the title
    m16sysui::State s;
    Open(s);
    Step(s, 0);
    check(Step(s, B) == Action::kHideAndClose, "B closes (2)");
    Closed(s);
    check(Step(s, B) == Action::kHide, "closing B hidden after close");
    check(Step(s, B | UP) == Action::kHide, "still held: hidden");
    check(s.drain, "drain persists while held");
    check(Step(s, 0) == Action::kPass, "release passes");
    check(Step(s, A) == Action::kPass, "then A passes");
  }
  {  // every close button closes; closing by other means (F7, mouse) drains too
    for (uint16_t button : {A, B, START, BACK}) {
      m16sysui::State s;
      Open(s);
      Step(s, 0);
      check(Step(s, button) == Action::kHideAndClose, "close button closes");
    }
    m16sysui::State s;
    Open(s);
    Step(s, 0);
    Closed(s);  // closed by the dialog itself
    check(Step(s, UP) == Action::kHide, "direction held across a dialog-side close is hidden");
    check(Step(s, 0) == Action::kPass, "released");
  }
  {  // reopening resets the arming
    m16sysui::State s;
    Open(s);
    Step(s, 0);
    Step(s, B);
    Closed(s);
    Open(s);
    check(!s.drain && !s.armed, "reopen clears drain and arming");
    check(Step(s, B) == Action::kHide, "B held across reopen does not close");
    check(Step(s, 0) == Action::kHide, "arm");
    check(Step(s, START) == Action::kHideAndClose, "Start closes");
  }
  {  // the shared gate: Filter reports hiding and fires the close request exactly once
    auto& g = m16sysui::gate();
    int closes = 0;
    {
      std::lock_guard<std::mutex> lock(g.mutex);
      m16sysui::Open(g.state);
      g.request_close = [&closes] { ++closes; };
    }
    check(m16sysui::IsOpen(), "gate open");
    check(m16sysui::Filter(A), "gate hides held A");
    check(m16sysui::Filter(0), "gate hides neutral");
    check(m16sysui::Filter(B), "gate hides B");
    check(m16sysui::Filter(B), "gate hides B again");
    check(closes == 1, "one close request");
    {
      std::lock_guard<std::mutex> lock(g.mutex);
      m16sysui::Closed(g.state);
    }
    check(!m16sysui::IsOpen(), "gate closed");
    check(m16sysui::Filter(B), "gate drains");
    check(!m16sysui::Filter(0), "gate passes after release");
    check(!m16sysui::Filter(A), "gate passes A");
    check(closes == 1, "still one close request");
  }
  std::printf("M16_SYSUI_TEST %s checks=%d failures=%d\n", failures ? "FAIL" : "PASS", checks, failures);
  return failures ? 1 : 0;
}
