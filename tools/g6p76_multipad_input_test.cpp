// G6-P76: guest-facing behaviour of several controllers, through the real rex::input::InputSystem and SlotAssignment
// exported by the development rexruntime.dll (the code XamInputGetState / SetState / GetCapabilities call). The pads
// are a mock driver with the SDL driver's device contract: devices in arrival order, a fresh DeviceId per connection
// (never reused), a removed pad erased from the list, one vibration call per request and OnHostClosing. The keyboard is
// a synthetic device, as the MnK driver reports itself. No SDL, no window, no game, no physical device; nothing leaves
// this process.
//
// Limits (documented in reports/post_release/G6P76_MULTI_CONTROLLER.md): the real SDLInputDriver is not exercised here
// (it initialises SDL only through a game window, and its SDL copy lives inside rexruntime.dll); its event handling,
// focus behaviour and SDL-side vibration are covered by G6-P75's tests and by g6p76_multipad_sdl_test.cpp. The real
// MnK driver is not used; its keys are covered by m10 / m32 / G6-P75.
//
// Ends with G6P76_MULTIPAD_INPUT_TEST PASS n/n. Exit 1 on a failed check.
//   g6p76_multipad_input_test.exe                  SlotAssignment, as CreateDefaultInputSystem installs it
//   g6p76_multipad_input_test.exe control-shared   negative control: the SDK's other policy (every device on user 0);
//                                                  the slot and routing checks must fail
#include <rex/input/device_assignment.h>
#include <rex/input/input_driver.h>
#include <rex/input/input_system.h>

#include <cstdio>
#include <cstring>
#include <string>
#include <vector>

using namespace rex;
using namespace rex::input;

namespace {

int g_pass = 0, g_fail = 0;
bool g_shared = false;  // negative control
void check(const char* name, bool ok) {
  std::printf("%s %s\n", ok ? "PASS" : "FAIL", name);
  (ok ? g_pass : g_fail)++;
}

struct MockPad {
  DeviceId id;
  std::string name, guid;
  X_INPUT_STATE state{};
  int vib_calls = 0;
  uint16_t left = 0, right = 0;
};

// The SDL driver's contract (sdl_input_driver.cpp): arrival order, never-rewound ids, erase on removal.
class PadDriver final : public InputDriver {
 public:
  PadDriver() : InputDriver(nullptr, 0) {}
  std::vector<MockPad> pads;
  uint64_t next_id = 1;
  int host_closing = 0;
  std::vector<std::pair<uint64_t, int>> removed_vibs;  // vibration calls a removed pad had received (for the record)

  MockPad& Add(const char* name, const char* guid = "03000000de280000ff11000000000000") {
    MockPad p;
    p.id = static_cast<DeviceId>(next_id++);
    p.name = name, p.guid = guid;
    pads.push_back(p);
    return pads.back();
  }
  void Remove(DeviceId id) {
    for (size_t i = 0; i < pads.size(); ++i)
      if (pads[i].id == id) {
        pads.erase(pads.begin() + static_cast<ptrdiff_t>(i));
        return;
      }
  }
  MockPad* Find(DeviceId id) {
    for (auto& p : pads)
      if (p.id == id) return &p;
    return nullptr;
  }

  X_STATUS Setup() override { return X_STATUS_SUCCESS; }
  void EnumerateDevices(std::vector<DeviceInfo>& out) override {
    for (auto& p : pads) {
      DeviceInfo d;
      d.id = p.id, d.name = p.name, d.guid = p.guid, d.synthetic = false;
      out.push_back(d);
    }
  }
  X_RESULT GetDeviceState(DeviceId id, X_INPUT_STATE* out) override {
    auto* p = Find(id);
    if (!p) return X_ERROR_DEVICE_NOT_CONNECTED;
    if (out) std::memcpy(out, &p->state, sizeof(*out));
    return X_ERROR_SUCCESS;
  }
  X_RESULT GetDeviceCapabilities(DeviceId id, uint32_t, X_INPUT_CAPABILITIES* out) override {
    auto* p = Find(id);
    if (!p) return X_ERROR_DEVICE_NOT_CONNECTED;
    if (out) {
      *out = {};
      out->type = 1, out->sub_type = 1;
      out->flags = static_cast<uint16_t>(static_cast<uint64_t>(id));  // lets the test see which pad answered
    }
    return X_ERROR_SUCCESS;
  }
  X_RESULT SetDeviceVibration(DeviceId id, X_INPUT_VIBRATION* v) override {
    auto* p = Find(id);
    if (!p) return X_ERROR_DEVICE_NOT_CONNECTED;
    ++p->vib_calls;
    p->left = v->left_motor_speed, p->right = v->right_motor_speed;
    return X_ERROR_SUCCESS;
  }
  X_RESULT GetDeviceKeystroke(DeviceId, uint32_t, X_INPUT_KEYSTROKE*) override { return X_ERROR_EMPTY; }
  void OnHostClosing() override { ++host_closing; }
};

// The keyboard as the MnK driver presents it: one synthetic device, always connected, accepts vibration.
class KeyboardDriver final : public InputDriver {
 public:
  KeyboardDriver() : InputDriver(nullptr, 0) {}
  X_INPUT_STATE state{};
  int vib_calls = 0, host_closing = 0;
  static constexpr DeviceId kId = static_cast<DeviceId>(0x4B424400);
  X_STATUS Setup() override { return X_STATUS_SUCCESS; }
  void EnumerateDevices(std::vector<DeviceInfo>& out) override {
    DeviceInfo d;
    d.id = kId, d.name = "keyboard", d.synthetic = true;
    out.push_back(d);
  }
  X_RESULT GetDeviceState(DeviceId, X_INPUT_STATE* out) override {
    if (out) std::memcpy(out, &state, sizeof(*out));
    return X_ERROR_SUCCESS;
  }
  X_RESULT GetDeviceCapabilities(DeviceId, uint32_t, X_INPUT_CAPABILITIES* out) override {
    if (out) {
      *out = {};
      out->type = 1, out->sub_type = 1, out->flags = 0x4B44;
    }
    return X_ERROR_SUCCESS;
  }
  X_RESULT SetDeviceVibration(DeviceId, X_INPUT_VIBRATION*) override {
    ++vib_calls;
    return X_ERROR_SUCCESS;
  }
  X_RESULT GetDeviceKeystroke(DeviceId, uint32_t, X_INPUT_KEYSTROKE*) override { return X_ERROR_EMPTY; }
  void OnHostClosing() override { ++host_closing; }
};

struct Rig {
  InputSystem input{nullptr};
  PadDriver* pads;
  KeyboardDriver* kbd;
  explicit Rig(bool keyboard = true) {
    auto p = std::make_unique<PadDriver>();
    pads = p.get();
    input.AddDriver(std::move(p));  // the SDL driver is added before MnK (CreateDefaultInputSystem)
    if (keyboard) {
      auto k = std::make_unique<KeyboardDriver>();
      kbd = k.get();
      input.AddDriver(std::move(k));
    } else {
      kbd = nullptr;
    }
    if (g_shared) {
      input.SetDeviceAssignment(std::make_unique<SharedAssignment>());
    } else {
      input.SetDeviceAssignment(std::make_unique<SlotAssignment>());  // as CreateDefaultInputSystem
    }
  }
  // Guest-facing XamInputGetState for one user (flags = gamepad).
  X_RESULT Get(uint32_t user, X_INPUT_STATE& s) {
    s = {};
    return input.GetState(user, &s);
  }
  uint16_t Buttons(uint32_t user) {
    X_INPUT_STATE s;
    return Get(user, s) == X_ERROR_SUCCESS ? static_cast<uint16_t>(s.gamepad.buttons) : 0xFFFF;
  }
  bool Connected(uint32_t user) {
    X_INPUT_STATE s;
    return Get(user, s) == X_ERROR_SUCCESS;
  }
  X_RESULT Vibrate(uint32_t user, uint16_t l, uint16_t r) {
    X_INPUT_VIBRATION v{};
    v.left_motor_speed = l, v.right_motor_speed = r;
    return input.SetState(user, &v);
  }
  uint16_t CapsFlags(uint32_t user) {
    X_INPUT_CAPABILITIES c{};
    return input.GetCapabilities(user, 1, &c) == X_ERROR_SUCCESS ? static_cast<uint16_t>(c.flags) : 0xFFFF;
  }
};

constexpr uint16_t A = X_INPUT_GAMEPAD_A, B = X_INPUT_GAMEPAD_B, X = X_INPUT_GAMEPAD_X,
                   START = X_INPUT_GAMEPAD_START;

}  // namespace

int main(int argc, char** argv) {
  g_shared = argc > 1 && !std::strcmp(argv[1], "control-shared");
  // 1. One controller (baseline) and the keyboard on user 0.
  {
    Rig r;
    auto& a = r.pads->Add("pad A");
    a.state.gamepad.buttons = A;
    a.state.gamepad.thumb_lx = 20000;
    X_INPUT_STATE s;
    check("one pad: user 0 connected with the pad's A", r.Get(0, s) == X_ERROR_SUCCESS && s.gamepad.buttons == A &&
                                                            s.gamepad.thumb_lx == 20000);
    check("one pad: users 1-3 not connected", !r.Connected(1) && !r.Connected(2) && !r.Connected(3));
    r.kbd->state.gamepad.buttons = START;
    check("keyboard + pad: user 0 is the OR of both (A|START)", r.Buttons(0) == (A | START));
    r.pads->pads[0].state.gamepad.buttons = 0;
    check("keyboard alone keeps acting on user 0", r.Buttons(0) == START);
  }

  // 2. Two independent controllers: slot ownership, no cross-merge.
  {
    Rig r;
    r.pads->Add("pad A");
    r.pads->Add("pad B");
    auto* a = &r.pads->pads[0];
    auto* b = &r.pads->pads[1];
    a->state.gamepad.buttons = A;
    check("two pads, A pressed on pad 1: user 0 has A, user 1 is connected and empty",
          r.Buttons(0) == A && r.Buttons(1) == 0);
    a->state.gamepad.buttons = 0;
    b->state.gamepad.buttons = X;
    check("two pads, X pressed on pad 2: user 1 has X, user 0 has nothing", r.Buttons(1) == X && r.Buttons(0) == 0);
    a->state.gamepad.buttons = A;
    b->state.gamepad.buttons = X | START;
    check("simultaneous buttons stay on their own user (0: A, 1: X|START)",
          r.Buttons(0) == A && r.Buttons(1) == (X | START));
    check("users 2-3 still not connected", !r.Connected(2) && !r.Connected(3));
    // Opposing sticks on two pads.
    a->state.gamepad.thumb_lx = 30000;
    b->state.gamepad.thumb_lx = -30000;
    a->state.gamepad.thumb_ly = -12000;
    b->state.gamepad.thumb_ly = 25000;
    X_INPUT_STATE s0, s1;
    r.Get(0, s0), r.Get(1, s1);
    check("opposing sticks on two pads: each user keeps its own pad's stick (no merge across pads)",
          s0.gamepad.thumb_lx == 30000 && s0.gamepad.thumb_ly == -12000 && s1.gamepad.thumb_lx == -30000 &&
              s1.gamepad.thumb_ly == 25000);
    // Opposing stick between pad 1 and the keyboard on user 0: the SDK merge keeps the larger magnitude.
    r.kbd->state.gamepad.thumb_lx = -32768;
    r.Get(0, s0);
    check("pad +30000 vs keyboard -32768 on user 0: larger magnitude (-32768)", s0.gamepad.thumb_lx == -32768);
    r.kbd->state.gamepad.thumb_lx = -30000;
    r.Get(0, s0);
    check("equal magnitude on user 0: the pad (lower ordinal, merged first) wins", s0.gamepad.thumb_lx == 30000);
    r.kbd->state.gamepad.thumb_lx = 0;
    r.kbd->state.gamepad.left_trigger = 200;
    a->state.gamepad.left_trigger = 40;
    r.Get(0, s0);
    check("trigger on user 0: maximum of pad and keyboard", s0.gamepad.left_trigger == 200);
  }

  // 3. Removal, primary removal, reconnection.
  {
    Rig r;
    r.pads->Add("pad A");
    r.pads->Add("pad B");
    const DeviceId ida = r.pads->pads[0].id, idb = r.pads->pads[1].id;
    r.pads->pads[0].state.gamepad.buttons = A;  // held while removed
    r.pads->pads[1].state.gamepad.buttons = X;
    r.Buttons(0), r.Buttons(1);
    r.pads->Remove(ida);
    check("pad 1 removed while A held: user 0 stays connected (keyboard) and A is gone",
          r.Connected(0) && r.Buttons(0) == 0);
    check("pad 1 removed: pad 2 is not promoted, user 1 still has X", r.Buttons(1) == X);
    {
      Rig nk(false);  // keyboard disabled (a configuration the SDK allows; tool mode)
      nk.pads->Add("pad A");
      nk.pads->Add("pad B");
      nk.pads->pads[1].state.gamepad.buttons = B;
      nk.Buttons(0);
      nk.pads->Remove(nk.pads->pads[0].id);
      check("no keyboard, pad 1 removed: user 0 reports not connected, user 1 keeps B",
            !nk.Connected(0) && nk.Buttons(1) == B);
    }
    auto& c = r.pads->Add("pad A again");
    c.state.gamepad.buttons = B;
    check("reconnected pad: a new DeviceId", c.id != ida && c.id != idb);
    check("reconnected pad takes the lowest free slot: user 0 (B), pad 2 stays user 1 (X)",
          r.Buttons(0) == B && r.Buttons(1) == X);
    r.pads->Remove(idb);
    check("pad 2 removed: user 1 not connected, user 0 unchanged", !r.Connected(1) && r.Buttons(0) == B);
    auto& d = r.pads->Add("pad D");
    d.state.gamepad.buttons = START;
    check("a pad connected later takes slot 1 again", r.Buttons(1) == START && r.Buttons(0) == B);
    // Removal of both pads: only the keyboard remains.
    while (!r.pads->pads.empty()) r.pads->Remove(r.pads->pads.front().id);
    check("all pads removed: user 0 keyboard only (connected, empty), users 1-3 not connected",
          r.Connected(0) && r.Buttons(0) == 0 && !r.Connected(1) && !r.Connected(2) && !r.Connected(3));
  }

  // 4. Five pads: the fifth has no guest user (kMaxGuestUsers = 4) and contributes nothing.
  {
    Rig r;
    for (int i = 0; i < 5; ++i) r.pads->Add("pad");
    r.pads->pads[4].state.gamepad.buttons = START;
    check("fifth pad: no guest user carries its START",
          r.Buttons(0) == 0 && r.Buttons(1) == 0 && r.Buttons(2) == 0 && r.Buttons(3) == 0);
    r.pads->Remove(r.pads->pads[1].id);
    r.pads->Add("pad F").state.gamepad.buttons = A;
    check("slot 1 freed: the next pad takes it, the fifth pad still has no user",
          r.Buttons(1) == A && r.Buttons(0) == 0 && r.Buttons(2) == 0 && r.Buttons(3) == 0);
  }

  // 5. Vibration routing.
  {
    Rig r;
    r.pads->Add("pad A");
    r.pads->Add("pad B");
    check("SetState(user 0): success", r.Vibrate(0, 0xC000, 0x4000) == X_ERROR_SUCCESS);
    auto& a = r.pads->pads[0];
    auto& b = r.pads->pads[1];
    check("user 0 vibration reaches pad 1 only", a.vib_calls == 1 && a.left == 0xC000 && a.right == 0x4000 &&
                                                     b.vib_calls == 0);
    check("user 1 vibration reaches pad 2 only",
          r.Vibrate(1, 0x1000, 0x2000) == X_ERROR_SUCCESS && b.vib_calls == 1 && b.left == 0x1000 && a.vib_calls == 1);
    check("user 2 vibration: not connected, no pad called",
          r.Vibrate(2, 0xFFFF, 0xFFFF) == X_ERROR_DEVICE_NOT_CONNECTED && a.vib_calls == 1 && b.vib_calls == 1);
    const DeviceId ida = a.id;
    r.pads->Remove(ida);  // removed while its motors were requested on
    auto& b2 = r.pads->pads[0];
    const int kb = r.kbd->vib_calls;
    check("pad 1 removed during vibration: user 0 request still succeeds (keyboard), pad 2 untouched",
          r.Vibrate(0, 0, 0) == X_ERROR_SUCCESS && b2.vib_calls == 1 && r.kbd->vib_calls == kb + 1);
    r.input.OnHostClosing();
    check("OnHostClosing reaches the pad driver and the keyboard once each",
          r.pads->host_closing == 1 && r.kbd->host_closing == 1);
  }

  // 6. One controller represented twice (physical + virtual, e.g. a remapper's virtual pad beside the device).
  {
    Rig r;
    r.pads->Add("DualSense Wireless Controller", "050000004c050000e60c000000006800");
    r.pads->Add("Xbox 360 Controller", "030000005e0400008e02000000007801");
    r.pads->pads[0].state.gamepad.buttons = START;  // one physical press, seen by both representations
    r.pads->pads[1].state.gamepad.buttons = START;
    check("duplicate representation: no deduplication, the same press reaches users 0 and 1",
          r.Buttons(0) == START && r.Buttons(1) == START);
    check("duplicate representation: user 0's state is not doubled (buttons are a set; one device on user 0)",
          r.Buttons(0) == START);
    r.Vibrate(0, 0x8000, 0);
    check("duplicate representation: user 0 vibration reaches only the user-0 representation",
          r.pads->pads[0].vib_calls == 1 && r.pads->pads[1].vib_calls == 0);
    // Two representations with identical metadata cannot be told apart from two identical pads.
    Rig same;
    same.pads->Add("Xbox 360 Controller", "030000005e0400008e02000000007801");
    same.pads->Add("Xbox 360 Controller", "030000005e0400008e02000000007801");
    same.pads->pads[1].state.gamepad.buttons = A;
    check("identical name and GUID: still two devices on two users (no heuristic merge)",
          same.Buttons(0) == 0 && same.Buttons(1) == A);
  }

  // 7. Capabilities follow the device in hand on user 0.
  {
    Rig r;
    r.pads->Add("pad A");
    const uint16_t pad_flags = static_cast<uint16_t>(static_cast<uint64_t>(r.pads->pads[0].id));
    check("capabilities of user 0: the pad (lowest ordinal) before any input", r.CapsFlags(0) == pad_flags);
    r.kbd->state.gamepad.buttons = A;
    r.Buttons(0);
    check("capabilities of user 0 after keyboard input: the keyboard", r.CapsFlags(0) == 0x4B44);
    r.kbd->state.gamepad.buttons = 0;
    r.pads->pads[0].state.gamepad.buttons = X;
    r.Buttons(0);
    check("capabilities of user 0 after pad input: the pad again", r.CapsFlags(0) == pad_flags);
    check("capabilities of user 1 with one pad: not connected", r.CapsFlags(1) == 0xFFFF);
  }

  std::printf("G6P76_MULTIPAD_INPUT_TEST %s %d/%d mode=%s\n", g_fail ? "FAIL" : "PASS", g_pass, g_pass + g_fail,
              g_shared ? "control-shared" : "slot");
  return g_fail ? 1 : 0;
}
