// D-138 host test of tools/r3hd_mouse.h (no SDK, no window, no device, no game). Built and run by
// tools/build_r3hd_release_tests.bat; prints R3HD_MOUSE_TEST PASS n/n.
#include "r3hd_mouse.h"

#include <cmath>
#include <cstdio>

namespace {
int checks = 0, failures = 0;
void Check(bool ok, const char* what) {
  ++checks;
  if (!ok) {
    ++failures;
    std::printf("FAIL %s\n", what);
  }
}

using r3hd_mouse::Buttons;
using r3hd_mouse::Camera;
using r3hd_mouse::CameraTuning;
constexpr double kFrame = 1000.0 / 60.0;
const CameraTuning kTuning{};

// Polls the camera n times without new motion; returns the polls with the stick right (+) / left (-), signed sum.
int Run(Camera& c, int n, double sens = 1.0, int* rx_last = nullptr) {
  int sum = 0;
  for (int i = 0; i < n; ++i) {
    int32_t rx = 0, ry = 0;
    c.Poll(true, kFrame, sens, kTuning, rx, ry);
    sum += rx > 0 ? 1 : rx < 0 ? -1 : 0;
    if (rx_last) *rx_last = rx;
  }
  return sum;
}

void ButtonsTests() {
  Buttons b;
  b.Down(r3hd_mouse::kLeft, true);
  Check(b.Poll(true) == 1, "held left: pressed");
  Check(b.Poll(true) == 1, "held left: still pressed on the next poll (charge / hold)");
  b.Up(r3hd_mouse::kLeft);
  Check(b.Poll(true) == 0, "released: not pressed");

  b.Down(r3hd_mouse::kRight, true);
  b.Up(r3hd_mouse::kRight);
  Check(b.Poll(true) == 2, "click shorter than a poll: reaches exactly one poll");
  Check(b.Poll(true) == 0, "click shorter than a poll: not repeated");

  b.Down(r3hd_mouse::kLeft, false);
  Check(b.Poll(true) == 0, "press while not live (menu, overlay, unfocused): never arms");
  Check(b.held(r3hd_mouse::kLeft), "... but its hold is tracked");
  b.Up(r3hd_mouse::kLeft);
  b.Down(r3hd_mouse::kLeft, true);
  Check(b.Poll(true) == 1, "a fresh press after it acts");
  b.Up(r3hd_mouse::kLeft);
  b.Poll(true);

  b.Down(r3hd_mouse::kLeft, true);
  Check(b.Poll(true) == 1, "hold before a context loss");
  Check(b.Poll(false) == 0, "context lost while held: not pressed");
  Check(b.Poll(true) == 0, "context back, still held: needs a fresh press (no carried attack)");
  b.Up(r3hd_mouse::kLeft);
  Check(b.Poll(true) == 0, "release while disarmed: nothing");
  b.Down(r3hd_mouse::kLeft, true);
  Check(b.Poll(true) == 1, "fresh press re-arms");
  b.Up(r3hd_mouse::kLeft);
  b.Poll(true);

  b.Down(r3hd_mouse::kMiddle, true);
  b.Disarm();
  Check(b.Poll(true) == 0, "Disarm drops a press not yet polled");
  b.Up(r3hd_mouse::kMiddle);

  b.Down(r3hd_mouse::kLeft, true);
  b.Down(r3hd_mouse::kRight, true);
  Check(b.Poll(true) == 3, "two buttons at once");
  b.Up(r3hd_mouse::kLeft);
  Check(b.Poll(true) == 2, "releasing one keeps the other");
  b.Clear();
  Check(b.Poll(true) == 0 && !b.held(r3hd_mouse::kRight), "Clear (focus loss) forgets everything");

  b.Down(r3hd_mouse::kX1, true);
  b.Down(r3hd_mouse::kX2, true);
  Check(b.Poll(true) == (1 << 3 | 1 << 4), "side buttons");
  b.Up(r3hd_mouse::kX1);
  b.Up(r3hd_mouse::kX2);
  b.Down(r3hd_mouse::Button(7), true);
  Check(b.Poll(true) == 0, "an unknown button is ignored");

  b.Down(r3hd_mouse::kLeft, true, 4);   // held since the old context
  b.Down(r3hd_mouse::kRight, true, 6);  // pressed after the swap that began context 6, before the poll
  b.DisarmOlder(6);
  Check(b.Poll(true) == 2, "context change: an older press needs a fresh one, a press in the new context acts");
  b.Up(r3hd_mouse::kLeft);
  b.Up(r3hd_mouse::kRight);
  b.Poll(true);

  b.Down(r3hd_mouse::kLeft, true);
  b.Down(r3hd_mouse::kLeft, true);  // a repeated down (no up between) stays one press
  Check(b.Poll(true) == 1 && b.Poll(true) == 1, "repeated down: still one held button");
  b.Up(r3hd_mouse::kLeft);
  Check(b.Poll(true) == 0, "one release ends it");
}

void ContextTests() {
  const uint32_t c0 = r3hd_mouse::Context();
  Check(!r3hd_mouse::Gameplay(c0), "no gameplay before the first swap");
  Check(!r3hd_mouse::PublishGameplay(false), "same fact: no change");
  Check(r3hd_mouse::PublishGameplay(true), "gameplay begins: a change");
  const uint32_t c1 = r3hd_mouse::Context();
  Check(r3hd_mouse::Gameplay(c1) && c1 != c0, "gameplay, new context value");
  Check(!r3hd_mouse::PublishGameplay(true), "still gameplay: no change");
  r3hd_mouse::PublishGameplay(false);
  r3hd_mouse::PublishGameplay(true);
  const uint32_t c3 = r3hd_mouse::Context();
  Check(r3hd_mouse::Gameplay(c3) && c3 != c1, "a pause and resume between two polls is still seen as a change");
}

void CameraTests() {
  Camera c;
  int32_t rx = 0, ry = 0;
  c.Add(100.0f, 0.0f);
  c.Poll(false, kFrame, 1.0, kTuning, rx, ry);
  Check(rx == 0 && ry == 0 && Run(c, 5) == 0, "not live: nothing, and the motion is dropped");

  c.Drop();
  c.Add(50.0f, 0.0f);  // 50 ms of full stick at sensitivity 1
  int on = Run(c, 10);
  Check(on == 3, "50 counts -> three polls of full stick (50 ms)");
  c.Add(-50.0f, 0.0f);
  Check(Run(c, 10) == -3, "the other way: left");

  c.Drop();
  c.Add(50.0f, 0.0f);
  rx = ry = 0;
  c.Poll(true, kFrame, 1.0, kTuning, rx, ry);
  Check(rx == 32767 && ry == 0, "full deflection, mouse right = stick right");
  c.Add(-20.0f, 0.0f);
  rx = 0;
  c.Poll(true, kFrame, 1.0, kTuning, rx, ry);
  Check(rx == -32767, "a reversal turns at once (nothing owed the old way survives)");
  Check(Run(c, 10) == 0, "... and owes only the new motion (20 ms: no further poll)");

  c.Drop();
  c.Add(5000.0f, 0.0f);
  on = Run(c, 40);
  Check(on <= 10 && on >= 8, "a flick is bounded: at most 150 ms of stick after the mouse stops");

  c.Drop();
  int slow = 0;
  for (int i = 0; i < 180; ++i) {  // one count per poll for 3 s: 180 ms owed in all
    c.Add(1.0f, 0.0f);
    slow += Run(c, 1);
  }
  Check(slow >= 10 && slow <= 12, "slow motion accumulates into short pulses (rotation follows the distance)");

  c.Drop();
  c.Add(3.0f, 0.0f);
  Check(Run(c, 30) == 0, "a remainder too small for one poll is dropped after idle time");
  c.Add(6.0f, 0.0f);
  Check(Run(c, 2) == 0, "... and does not add to later motion");

  c.Drop();
  c.Add(50.0f, 0.0f);
  Check(Run(c, 10, 2.0) == 6, "sensitivity 2 doubles the stick time");
  c.Add(50.0f, 0.0f);
  on = Run(c, 10, 0.5);
  Check(on == 1 || on == 2, "sensitivity 0.5 halves it (25 ms: one or two polls)");

  c.Drop();
  c.Add(0.0f, 20.0f);
  int down = 0;
  for (int i = 0; i < 10; ++i) {
    rx = ry = 0;
    c.Poll(true, kFrame, 1.0, kTuning, rx, ry);
    down += ry < 0;
  }
  Check(down == 0, "vertical: a small motion (10 ms) does not move the camera height");
  c.Drop();
  c.Add(0.0f, 240.0f);  // 120 ms vertical
  down = 0;
  int up = 0;
  for (int i = 0; i < 12; ++i) {
    rx = ry = 0;
    c.Poll(true, kFrame, 1.0, kTuning, rx, ry);
    down += ry < 0;
    up += ry > 0;
  }
  Check(down >= 7 && down <= 8 && up == 0 && rx == 0, "vertical: mouse down = stick down, for the owed time");
  c.Drop();
  c.Add(0.0f, -240.0f);
  rx = ry = 0;
  c.Poll(true, kFrame, 1.0, kTuning, rx, ry);
  Check(ry == 32767, "vertical: mouse up = stick up");

  c.Drop();
  c.Add(1.0e9f, 0.0f);
  rx = 0;
  c.Poll(true, 1.0e6, 1.0, kTuning, rx, ry);
  Check(rx == 32767 && c.backlog_x_ms() <= 150.0, "huge motion and a stalled poll stay bounded");

  c.Drop();
  c.Add(std::nanf(""), 0.0f);
  c.Add(50.0f, 0.0f);
  Check(Run(c, 10) == 3, "a non-finite motion value is ignored (the camera keeps working)");

  c.Drop();
  rx = 20000;  // the arrow keys or another source already set the axis; the caller clamps
  c.Add(20.0f, 0.0f);
  c.Poll(true, kFrame, 1.0, kTuning, rx, ry);
  Check(rx == 20000 + 32767, "the mouse adds to the keyboard's axis before the driver's clamp");

  Check(std::fabs(r3hd_mouse::SensitivityFromPercent(50) - 1.0) < 1e-12, "50 % = sensitivity 1");
  Check(std::fabs(r3hd_mouse::SensitivityFromPercent(100) - 4.0) < 1e-12, "100 % = 4");
  Check(std::fabs(r3hd_mouse::SensitivityFromPercent(75) - 2.0) < 1e-12, "75 % = 2");
  Check(std::fabs(r3hd_mouse::SensitivityFromPercent(1) - std::pow(2.0, -49.0 / 25.0)) < 1e-12, "1 % = 2^-1.96");
  Check(r3hd_mouse::SensitivityFromPercent(0) == r3hd_mouse::SensitivityFromPercent(1) &&
            r3hd_mouse::SensitivityFromPercent(200) == 4.0,
        "out-of-range percentages clamp");
}
// D-145: the title's Look Mode response as measured (E-327): calibrated rate full * (m - 0.29) / 0.5 above 0.40,
// saturated from 0.80; uncalibrated (no full deflection seen in that direction) twice that above 0.30; a held stick
// turns at once, a release halves the speed each frame.
struct TitleAxis {
  double full;
  bool cal[2] = {};
  double v = 0.0;
  double Step(int32_t stick) {
    const double m = std::fabs(double(stick)) / 32767.0;
    const int d = stick > 0 ? 1 : -1;
    double r = 0.0;
    if (stick != 0) {
      if (m >= 1.0) cal[d > 0 ? 0 : 1] = true;
      const bool c = cal[d > 0 ? 0 : 1];
      const double n = (c ? 1.0 : 2.0) * (m - 0.29) / 0.5;
      r = (m <= (c ? 0.40 : 0.30)) ? 0.0 : full * std::clamp(n, 0.0, 1.0);
    }
    double nv = v * 0.5;
    if (r > 0.0) nv = d * std::max(r, (v * d > 0) ? std::fabs(nv) : 0.0);
    v = nv;
    return v;
  }
};

struct LookRig {
  r3hd_mouse::LookStick look;
  TitleAxis tx{2.71}, ty{2.93};
  r3hd_mouse::LookTuning t{};
  double turned_x = 0.0, turned_y = 0.0;
  int partial_before_full = 0, dead_band = 0, frames = 0;
  // One frame: counts in (and optional keys), the title turns.
  void Frame(float dx, float dy, int32_t key_x = 0, int32_t key_y = 0, bool live = true) {
    look.Add(dx, dy);
    int32_t lx = key_x, ly = key_y;
    const bool cx_before[2] = {tx.cal[0], tx.cal[1]}, cy_before[2] = {ty.cal[0], ty.cal[1]};
    look.Poll(live, 1.0, t, lx, ly);
    auto audit = [&](int32_t s, const bool* cal) {
      const double m = std::fabs(double(s)) / 32767.0;
      if (s != 0 && m < 1.0 && !cal[s > 0 ? 0 : 1]) ++partial_before_full;
      if (s != 0 && m < 0.45) ++dead_band;
    };
    if (key_x == 0) audit(lx, cx_before);
    if (key_y == 0) audit(ly, cy_before);
    turned_x += tx.Step(lx);
    turned_y += ty.Step(ly);
    ++frames;
  }
  void Idle(int n) {
    for (int i = 0; i < n; ++i) Frame(0.0f, 0.0f);
  }
};

void LookTests() {
  using r3hd_mouse::LookStick;
  {  // not live / no motion
    LookRig r;
    r.Idle(30);
    Check(r.turned_x == 0.0 && r.turned_y == 0.0, "look: no motion, no turn");
    r.look.Add(500.0f, 0.0f);
    int32_t lx = 0, ly = 0;
    r.look.Poll(false, 1.0, r.t, lx, ly);
    Check(lx == 0 && ly == 0, "look: not live gives nothing");
    r.Idle(10);
    Check(r.turned_x == 0.0, "look: motion while not live is dropped (no turn when it comes back)");
  }
  {  // calibration guard, per direction
    LookRig r;
    r.look.SetLevel(1);
    for (int i = 0; i < 40; ++i) r.Frame(4.0f, 0.0f);  // slow right: 0.2 deg per frame wanted
    r.Idle(30);
    Check(r.partial_before_full == 0, "look: no partial deflection in a direction before a full one was sent there");
    Check(r.look.calibrated(0, 1) && !r.look.calibrated(0, -1), "look: right calibrated by its first full frame, left not");
    Check(r.turned_x < 0.0 || r.turned_x > 0.0, "look: slow motion on an uncalibrated direction still turns");
    const double before = r.turned_x;
    for (int i = 0; i < 40; ++i) r.Frame(-4.0f, 0.0f);
    r.Idle(30);
    Check(r.partial_before_full == 0 && r.turned_x < before, "look: left also starts with full frames only");
    r.look.SetLevel(1);
    r.look.SetLevel(1);
    Check(r.look.calibrated(0, 1), "look: the same level keeps the guard's state");
    r.look.SetLevel(2);
    Check(!r.look.calibrated(0, 1) && !r.look.calibrated(0, -1), "look: a level change re-arms the guard");
  }
  {  // accuracy once calibrated, at several speeds, both axes
    for (float counts : {2.0f, 6.0f, 12.0f, 24.0f, 40.0f}) {
      LookRig r;
      r.tx.cal[0] = r.tx.cal[1] = r.ty.cal[0] = r.ty.cal[1] = true;
      r.Frame(200.0f, -200.0f);  // one quick move right / up (10 deg) sends a full frame: the guard knows + x and + y
      r.Idle(40);
      Check(r.look.calibrated(0, 1) && r.look.calibrated(1, 1), "look: a quick move calibrated the guard");
      const double x0 = r.turned_x, y0 = r.turned_y;
      for (int i = 0; i < 60; ++i) r.Frame(counts, -counts);  // right and up
      r.Idle(40);
      const double want = 60.0 * counts * r.t.deg_per_count;
      const double gx = r.turned_x - x0, gy = r.turned_y - y0;
      char what[160];
      std::snprintf(what, sizeof what, "look: %g counts/frame turns as wanted (x %.2f y %.2f of %.2f deg, within 8 %%)",
                    counts, gx, gy, want);
      Check(std::fabs(gx - want) <= 0.08 * want + 0.9 && std::fabs(gy - want) <= 0.08 * want + 0.9, what);
      Check(r.dead_band == 0, "look: no nonzero deflection below 0.45 (the title's dead band)");
    }
  }
  {  // stops: nothing turns after the motion ends and its backlog is spent
    LookRig r;
    r.tx.cal[0] = r.tx.cal[1] = true;
    r.Frame(2000.0f, 0.0f);  // a flick far beyond the bound
    r.Idle(60);
    const double after = r.turned_x;
    r.Idle(60);
    Check(r.turned_x == after, "look: a flick stops (no turn 1 s later)");
    Check(after <= (r.t.max_backlog_frames + 2.0) * 2.71 + 1e-6, "look: a flick turns at most the bounded backlog");
  }
  {  // reversal and sign
    LookRig r;
    r.tx.cal[0] = r.tx.cal[1] = true;
    r.Frame(80.0f, 0.0f);
    r.Frame(-80.0f, 0.0f);
    r.Idle(30);
    for (int i = 0; i < 20; ++i) r.Frame(-10.0f, 0.0f);
    int32_t lx = 0, ly = 0;
    r.look.Add(-10.0f, 120.0f);
    r.look.Poll(true, 1.0, r.t, lx, ly);
    Check(lx < 0, "look: mouse left = stick left");
    Check(ly < 0, "look: mouse down = stick down (the title tilts the view down with it, E-331)");
  }
  {  // keys win on their axis
    LookRig r;
    r.Frame(200.0f, 0.0f, 32767, 0);
    int32_t lx = 32767, ly = 0;
    r.look.Add(300.0f, 0.0f);
    r.look.Poll(true, 1.0, r.t, lx, ly);
    Check(lx == 32767, "look: a held key keeps its axis (the mouse adds nothing there)");
    Check(r.look.owed(0) == 0.0, "look: and the mouse motion on that axis is dropped");
    Check(r.look.calibrated(0, 1), "look: a full key deflection in Look Mode calibrates its direction");
    int32_t lx2 = 0, ly2 = 0;
    r.look.Add(0.0f, 0.0f);
    r.look.Poll(true, 1.0, r.t, lx2, ly2);
    Check(lx2 == 0, "look: after the key, the dropped mouse motion does not come back");
  }
  Check(r3hd_mouse::PublishLook(true) && r3hd_mouse::LookMode() && !r3hd_mouse::PublishLook(true),
        "look: the published fact and its change");
  r3hd_mouse::PublishLook(false);
  r3hd_mouse::PublishLevel("menu_20");
  const uint32_t l1 = r3hd_mouse::Level();
  r3hd_mouse::PublishLevel("wood_10");
  Check(l1 != r3hd_mouse::Level(), "look: two levels, two identities");
}
}  // namespace

int main() {
  ButtonsTests();
  ContextTests();
  CameraTests();
  LookTests();
  std::printf("R3HD_MOUSE_TEST %s %d/%d\n", failures ? "FAIL" : "PASS", checks - failures, checks);
  std::fflush(stdout);
  return failures ? 1 : 0;
}
