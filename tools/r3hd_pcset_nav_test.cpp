// Windowless real-ImGui regression for Settings navigation. Synthetic inputs only:
// no SDL initialization, device opening, desktop events, renderer or game process.
#include <rex/r3hd_pcset_nav.h>
#include "m2_host/r3hd_pc_settings.h"
#include <imgui_internal.h>
#include <cstdio>

using r3hd_pcset::GamepadNavigation;
using r3hd_pcset::NavPad;

namespace {
struct Fixture {
  ImGuiContext* context = ImGui::CreateContext();
  GamepadNavigation navigation;
  ImGuiID category = 0, combo = 0, slider = 0, toggle = 0, save = 0;
  ImGuiID extra[12]{};
  float content_scroll = 0.0f;
  ImVec2 category_center;
  int choice = 0, value = 50, category_clicks = 0, saves = 0;
  bool enabled = false;

  Fixture() {
    auto& io = ImGui::GetIO();
    io.IniFilename = nullptr;
    io.DisplaySize = ImVec2(800, 600);
    io.DeltaTime = 1.0f / 60.0f;
    io.ConfigFlags |= ImGuiConfigFlags_NavEnableKeyboard | ImGuiConfigFlags_NavEnableGamepad;
    io.BackendFlags |= ImGuiBackendFlags_HasGamepad | ImGuiBackendFlags_RendererHasTextures;
    io.Fonts->AddFontDefault();
  }
  ~Fixture() { ImGui::DestroyContext(context); }

  void Frame(NavPad raw = {}) {
    GamepadNavigation::Feed(ImGui::GetIO(), navigation.Filter(1, raw));
    ImGui::NewFrame();
    ImGui::SetNextWindowPos(ImVec2(20, 20));
    ImGui::SetNextWindowSize(ImVec2(500, 500));
    ImGui::Begin("Settings navigation fixture", nullptr,
                 ImGuiWindowFlags_NoSavedSettings | ImGuiWindowFlags_NoMove |
                 ImGuiWindowFlags_NoResize | ImGuiWindowFlags_NoCollapse);
    ImGui::BeginChild("##settings", ImVec2(0, -80), ImGuiChildFlags_NavFlattened);
    ImGui::SeparatorText("Display");
    category = ImGui::GetID("Category");
    if (ImGui::Button("Category")) ++category_clicks;
    ImGui::SetItemDefaultFocus();
    const ImVec2 lo = ImGui::GetItemRectMin(), hi = ImGui::GetItemRectMax();
    category_center = ImVec2((lo.x + hi.x) / 2, (lo.y + hi.y) / 2);
    if (r3hd_pcset::BeginSettingRows("display", 160)) {
      r3hd_pcset::DrawSettingRow("Unavailable setting", "Next start", "", [&] {
        ImGui::BeginDisabled();
        ImGui::Button("##unavailable");
        ImGui::EndDisabled();
      });
      r3hd_pcset::DrawSettingRow("Display mode", "Applies now", "", [&] {
        combo = ImGui::GetID("##display");
        ImGui::Combo("##display", &choice, "Window\0Fullscreen\0");
      });
      r3hd_pcset::EndSettingRows();
    }
    ImGui::SeparatorText("Controls");
    if (r3hd_pcset::BeginSettingRows("controls", 160)) {
      r3hd_pcset::DrawSettingRow("Sensitivity", "Applies now", "", [&] {
        slider = ImGui::GetID("##sensitivity");
        ImGui::SliderInt("##sensitivity", &value, 0, 100);
      });
      r3hd_pcset::DrawSettingRow("Mouse camera", "Applies now", "", [&] {
        toggle = ImGui::GetID("##camera");
        ImGui::Checkbox("##camera", &enabled);
      });
      for (int i = 0; i < 12; ++i) {
        ImGui::PushID(i);
        r3hd_pcset::DrawSettingRow("Other preference", "Next start", "", [&] {
          extra[i] = ImGui::GetID("##extra");
          ImGui::Button("##extra");
        });
        ImGui::PopID();
      }
      r3hd_pcset::EndSettingRows();
    }
    content_scroll = ImGui::GetScrollY();
    ImGui::EndChild();
    ImGui::Separator();
    ImGui::TextUnformatted("Changes are saved only after Apply.");
    save = ImGui::GetID("Apply");
    if (ImGui::Button("Apply")) ++saves;
    ImGui::End();
    ImGui::Render();
  }
  void Settle() { for (int i = 0; i < 4; ++i) Frame(); }
  void Tap(uint16_t buttons) {
    NavPad p;
    p.buttons = buttons;
    Frame(p);
    Settle();
  }
  bool Focused(ImGuiID id) const { return context->NavId == id; }
  bool PopupOpen() const { return context->OpenPopupStack.Size != 0; }
};
}  // namespace

int main() {
  int checks = 0, failures = 0;
  const auto check = [&](const char* name, bool ok) {
    ++checks;
    if (!ok) { ++failures; std::printf("FAIL %s\n", name); }
  };
  constexpr uint16_t A = 0x1000, B = 0x2000, Down = 2, Right = 8;

  {
    ImGuiContext* ctx = ImGui::CreateContext();
    auto& io = ImGui::GetIO();
    io.ConfigFlags = ImGuiConfigFlags_NavEnableKeyboard;
    GamepadNavigation nav;
    nav.Update(io, true, false);  // unfocused: no SDL/device access
    check("panel enables gamepad navigation", (io.ConfigFlags & ImGuiConfigFlags_NavEnableGamepad) != 0);
    nav.Update(io, false, false);
    check("close restores prior gamepad flags without losing keyboard navigation",
          io.ConfigFlags == ImGuiConfigFlags_NavEnableKeyboard && !(io.BackendFlags & ImGuiBackendFlags_HasGamepad));
    io.ConfigFlags |= ImGuiConfigFlags_NavEnableGamepad;
    io.BackendFlags |= ImGuiBackendFlags_HasGamepad;
    nav.Update(io, true, false);
    nav.Update(io, false, false);
    check("preexisting gamepad flags survive close", (io.ConfigFlags & ImGuiConfigFlags_NavEnableGamepad) &&
          (io.BackendFlags & ImGuiBackendFlags_HasGamepad));
    ImGui::DestroyContext(ctx);
  }

  {
    GamepadNavigation nav;
    NavPad held;
    held.buttons = A | B;
    held.thumb_lx = 32767;
    auto first = nav.Filter(10, held);
    check("held A/B and stick do not arm on opening",
          first.buttons == 0 && first.thumb_lx == 0);
    auto again = nav.Filter(10, held);
    check("held inputs remain withheld", again.buttons == 0 && again.thumb_lx == 0);
    nav.Filter(10, {});
    auto fresh = nav.Filter(10, held);
    check("fresh A/B and stick pass after release", fresh.buttons == (A | B) && fresh.thumb_lx == 32767);
    auto other = nav.Filter(20, held);
    check("new pad has an independent release gate", other.buttons == 0 && other.thumb_lx == 0);
    check("second pad cannot suppress first pad", nav.Filter(10, held).buttons == (A | B));
    nav.Reset();
    check("reset re-arms opening release gate", nav.Filter(10, held).buttons == 0);
    nav.Filter(10, {});
    NavPad one;
    one.buttons = A;
    check("single fresh button survives reset and release", nav.Filter(10, one).buttons == A);
  }

  {
    Fixture f;
    f.Settle();
    check("initial default focus is category", f.Focused(f.category));
    f.Tap(Down);
    check("down skips disabled item and focuses dropdown", f.Focused(f.combo));
    check("controller navigation shows focus cursor", f.context->NavCursorVisible);
    check("controller becomes active navigation source", f.context->NavInputSource == ImGuiInputSource_Gamepad);
    f.Tap(A);
    check("A opens dropdown", f.PopupOpen());
    const int saved_choice = f.choice;
    f.Tap(Down);
    f.Tap(B);
    check("B cancels dropdown without applying its highlighted choice", !f.PopupOpen() && f.choice == saved_choice);
    check("dropdown cancel does not activate underlying buttons", f.saves == 0 && f.category_clicks == 0);
    check("dropdown cancel returns focus to its control", f.Focused(f.combo));
    f.Tap(A);
    f.Tap(Down);
    f.Tap(A);
    check("A confirms a dropdown choice", !f.PopupOpen() && f.choice == 1);
    f.Tap(Down);
    check("down moves from dropdown to slider", f.Focused(f.slider));
    f.Tap(A);
    const int before = f.value;
    f.Tap(Right);
    check("right changes active slider", f.value > before && f.value <= 100);
    f.Tap(B);
    check("B leaves slider editing without activating Apply", f.context->ActiveId == 0 && f.saves == 0);
    f.Tap(Down);
    check("down reaches toggle", f.Focused(f.toggle));
    f.Tap(A);
    check("A changes toggle", f.enabled);
    bool all_reachable = true;
    for (int i = 0; i < 12; ++i) { f.Tap(Down); all_reachable &= f.Focused(f.extra[i]); }
    check("every row remains reachable across scrolling content", all_reachable && f.content_scroll > 0.0f);
    f.Tap(Down);
    check("down crosses flattened content child into Apply footer", f.Focused(f.save));
    f.Tap(A);
    check("Apply requires explicit activation", f.saves == 1);

    auto& io = ImGui::GetIO();
    io.AddMousePosEvent(100, 100);
    io.AddMouseWheelEvent(0, 100);
    f.Settle();
    io.AddMousePosEvent(f.category_center.x, f.category_center.y);
    f.Frame();
    io.AddMouseButtonEvent(0, true);
    f.Frame();
    io.AddMouseButtonEvent(0, false);
    f.Settle();
    check("mouse works after controller navigation", f.category_clicks == 1);
    check("mouse click hides controller cursor", !f.context->NavCursorVisible);
    f.Tap(Down);
    check("controller resumes from mouse-selected control", f.Focused(f.combo) && f.context->NavCursorVisible);

    // Keyboard uses the same ImGui navigation, without remapping or desktop input.
    io.AddKeyEvent(ImGuiKey_DownArrow, true);
    f.Frame();
    io.AddKeyEvent(ImGuiKey_DownArrow, false);
    f.Settle();
    check("keyboard remains usable after controller and mouse", f.Focused(f.slider));

    NavPad stick;
    stick.thumb_ly = -15000;
    for (int i = 0; i < 4; ++i) f.Frame(stick);
    check("stick inside navigation dead zone neither presses down nor changes focus",
          !ImGui::IsKeyDown(ImGuiKey_GamepadDpadDown) && f.Focused(f.slider));
    stick.thumb_ly = -32768;
    f.Frame(stick);
    f.Settle();
    check("fresh left-stick down moves focus to toggle", f.Focused(f.toggle));
    check("left-stick navigation restores controller source and visible focus",
          f.context->NavInputSource == ImGuiInputSource_Gamepad && f.context->NavCursorVisible);
    stick.thumb_ly = 32767;
    f.Frame(stick);
    f.Settle();
    check("left-stick up moves focus back to slider", f.Focused(f.slider));
  }
  std::printf("R3HD_PCSET_NAV_TEST %s %d/%d\n", failures ? "FAIL" : "PASS", checks - failures, checks);
  return failures ? 1 : 0;
}
