// D-139 acceptance test of the in-game PC Settings input gate and model, window-less: the pure gates
// (tools/r3hd_hostui_gate.h), the panel's model / value helpers (tools/m2_host/r3hd_pc_settings.h) and the REAL
// keyboard / mouse driver of the built runtime with the panel opening and closing (its is_active() callback, the
// one SetHostUiInputBlocked drives). No app, window, SDL initialisation, device, cursor, focus change or OS input.
// Built and run by tools/build_hostui_test.bat (tools/r3hd_pcset_regression.py); prints R3HD_HOSTUI_TEST PASS n/n.
#include <rex/cvar.h>
#include <rex/input/mnk/mnk_input_driver.h>
#include <rex/ui/keybinds.h>
#include <rex/ui/ui_event.h>
#include <rex/r3hd_hostui_gate.h>
#include "m2_host/r3hd_pc_settings.h"
#include <cstdio>
#include <cstdlib>

using namespace rex;
using namespace rex::input;

namespace {
struct Pad {
  uint16_t buttons = 0;
  uint8_t left_trigger = 0, right_trigger = 0;
  int16_t thumb_lx = 0, thumb_ly = 0, thumb_rx = 0, thumb_ry = 0;
};
}  // namespace

int main() {
  int checks = 0, failures = 0;
  auto check = [&](const char* label, bool ok) {
    ++checks;
    failures += !ok;
    if (!ok) std::printf("FAIL %s\n", label);
  };

  // --- PadGate: nothing changes without a panel ---------------------------------------------------------------
  {
    r3hd_hostui::PadGate g;
    Pad p{0x1001, 200, 10, 30000, -500, 9000, 0};
    Pad q = p;
    g.Apply(true, q);
    check("pad: no panel, every value unchanged", q.buttons == p.buttons && q.left_trigger == 200 &&
                                                       q.thumb_lx == 30000 && q.thumb_ly == -500 && q.thumb_rx == 9000);
    check("pad: no panel, nothing held", !g.Holding());
  }
  // --- PadGate: panel open, then closed with A, LT, the left stick held and a drifting right stick -----------------
  {
    r3hd_hostui::PadGate g;
    Pad p{0x1000 /*A*/, 255, 0, 32767, 0, 300, -200};
    Pad q = p;
    g.Apply(false, q);
    check("pad: panel open, neutral", q.buttons == 0 && q.left_trigger == 0 && q.thumb_lx == 0 && q.thumb_rx == 0);
    check("pad: panel open, holding", g.Holding());
    check("pad: panel open, not yet withholding (keystrokes are blocked by is_active itself)", !g.Withholding());
    q = p;
    g.Apply(true, q);
    check("pad: closed with A held: no A", q.buttons == 0);
    check("pad: withholding after the close", g.Withholding());
    check("pad: closed with LT held: no LT", q.left_trigger == 0);
    check("pad: closed with the stick held: no movement", q.thumb_lx == 0 && q.thumb_ly == 0);
    check("pad: a resting (drifting) stick is never withheld", q.thumb_rx == 300 && q.thumb_ry == -200);
    p.buttons = 0x1000 | 0x2000;  // B pressed fresh while A still held
    q = p;
    g.Apply(true, q);
    check("pad: a fresh button passes beside a withheld one", q.buttons == 0x2000);
    p.buttons = 0;
    q = p;
    g.Apply(true, q);
    p.buttons = 0x1000;
    q = p;
    g.Apply(true, q);
    check("pad: A released and pressed again: A", q.buttons == 0x1000);
    p.left_trigger = 20;  // inside the release zone: released
    q = p;
    g.Apply(true, q);
    check("pad: LT back in its zone passes its (small) value", q.left_trigger == 20);
    p.left_trigger = 255;
    q = p;
    g.Apply(true, q);
    check("pad: LT pressed again: full", q.left_trigger == 255);
    p.thumb_lx = 5000;  // inside the left zone: released
    q = p;
    g.Apply(true, q);
    check("pad: stick back in its zone passes", q.thumb_lx == 5000);
    p.thumb_lx = 32767;
    q = p;
    g.Apply(true, q);
    check("pad: stick pushed again: full", q.thumb_lx == 32767);
    check("pad: nothing withheld any more", !g.Holding());
  }
  // --- KeyGate -------------------------------------------------------------------------------------------------
  {
    r3hd_hostui::KeyGate g;
    bool down[256] = {}, out[256] = {};
    down[0x27] = true;
    check("keys: no panel: Sync reports nothing", !g.Sync(true, down));
    g.Mask(down, out);
    check("keys: no panel: held key visible", out[0x27]);
    check("keys: panel opens", !g.Sync(false, down) && !g.active());
    check("keys: panel closes: reactivation reported once", g.Sync(true, down) && !g.Sync(true, down));
    g.Mask(down, out);
    check("keys: a key held through the panel is withheld", !out[0x27]);
    down[0x20] = true;
    g.Mask(down, out);
    check("keys: a fresh key passes", out[0x20] && !out[0x27]);
    g.Released(0x27);
    g.Mask(down, out);
    check("keys: after its key-up the key is free (still up until pressed)", out[0x27]);
  }
  // --- panel model and value helpers --------------------------------------------------------------------------
  {
    const std::string text =
        "R3HD_LAUNCHER_MODEL\t5\nSETTINGS\tok\thdplus\thdplus\tHD+ (Recommended)\t\nREVISION\tabc123\n"
        "GROUP\tdisplay\tDisplay\nSETTING\tdisplay\tdisplay\tpreference\tplatform\tDisplay mode\th\t\twindowed\twindowed\tfullscreen\n"
        "VALUE\tdisplay\twindowed\tWindow\nVALUE\tdisplay\tfullscreen\tFullscreen\n"
        "SETTING\tmouse_sensitivity\tmouse\tpreference\tenhancement\tMouse Sensitivity\t\t\t50\t50\t70\n"
        "REQUIRES\tmouse_sensitivity\tmouse_camera\ton\nSLIDER\tmouse_sensitivity\t1\t100\tpercent\n"
        "LANG\tui_language\ttr\nUISTRING\tDisplay mode\tEkran modu\nEND\n";
    auto m = r3hd_pcset::ParseModel(text);
    check("model: parsed", m.ok && m.settings.size() == 2 && m.revision == "abc123" && m.language == "tr");
    check("model: current and values", m.settings[0].current == "fullscreen" && m.settings[0].values.size() == 2);
    check("model: slider and requirement", m.settings[1].slider && m.settings[1].max == 100 &&
                                               m.settings[1].needs.size() == 1 && m.settings[1].current == "70");
    check("model: strings", m.strings["Display mode"] == "Ekran modu" && m.preset_label == "HD+ (Recommended)");
    check("model: a truncated model is refused", !r3hd_pcset::ParseModel("R3HD_LAUNCHER_MODEL\t5\nSETTINGS\tok\n").ok);
    auto s = r3hd_pcset::ParsePairs("display=fullscreen;render_scale=2;bad;=x");
    check("session pairs", s.size() == 2 && s["render_scale"] == "2");
    check("sensitivity 50 % = 1.0, 75 % = 2.0, 25 % = 0.5",
          r3hd_pcset::SensitivityScale(50) == 1.0 && std::abs(r3hd_pcset::SensitivityScale(75) - 2.0) < 1e-9 &&
              std::abs(r3hd_pcset::SensitivityScale(25) - 0.5) < 1e-9);
    bool round = true;
    for (int p = 1; p <= 100; ++p) round &= r3hd_pcset::SensitivityPercent(r3hd_pcset::SensitivityScale(p)) == p;
    check("sensitivity percent round-trips 1..100", round);
    check("live settings", r3hd_pcset::IsLive("display") && r3hd_pcset::IsLive("mouse_buttons") &&
                               !r3hd_pcset::IsLive("render_scale") && !r3hd_pcset::IsLive("window_size"));
    check("quoting", r3hd_pcset::Quote(L"C:\\a b\\") == L"\"C:\\a b\\\\\"" && r3hd_pcset::Quote(L"x\"y") == L"\"x\\\"y\"");
  }

  // --- the REAL keyboard / mouse driver with the panel opening and closing ----------------------------------------
  auto flag = [&](const char* name, const char* value) {
    if (!cvar::SetFlagByName(name, value)) {
      std::printf("FAIL unknown setting %s\n", name);
      std::exit(2);
    }
  };
  flag("mnk_mode", "true");
  flag("mnk_mouse", "false");
  flag("mnk_mouse_buttons", "true");
  flag("mnk_modifier_keys", "true");
  flag("keybind_a", "Space");
  flag("keybind_b", "None");
  flag("keybind_x", "E,LMB");
  flag("keybind_start", "Return");
  flag("keybind_lstick_right", "Right");
  bool names = true;
  for (const char* name : {"Space", "E", "Return", "Right"}) names &= ui::ParseVirtualKey(name) != ui::VirtualKey::kNone;
  check("driver: every key name used here is a real key (a typo would make a check pass vacuously)", names);
  mnk::MnkInputDriver driver(nullptr, 0);
  driver.SetTestEnabled(true);
  driver.Setup();
  bool active = true;  // what SetHostUiInputBlocked(false / true) gives the drivers
  driver.set_is_active_callback([&] { return active; });
  ui::UISetupEvent focus(nullptr, false);
  driver.OnGotFocus(focus);
  driver.TestSetGameplay(true);
  std::vector<DeviceInfo> devices;
  driver.EnumerateDevices(devices);
  if (devices.size() != 1) return 2;
  const auto id = devices[0].id;
  X_INPUT_STATE s{};
  auto poll = [&] {
    s = {};
    driver.GetDeviceState(id, &s);
    return unsigned(uint16_t(s.gamepad.buttons));
  };
  auto key = [&](const char* name, bool down, bool repeat = false) {
    ui::KeyEvent e(nullptr, ui::ParseVirtualKey(name), 1, repeat || !down, false, false, false, false);
    if (down) driver.OnKeyDown(e); else driver.OnKeyUp(e);
  };
  auto button = [&](ui::MouseEvent::Button b, bool down) {
    ui::MouseEvent e(nullptr, b, 0, 0);
    if (down) driver.OnMouseDown(e); else driver.OnMouseUp(e);
  };
  constexpr unsigned A = X_INPUT_GAMEPAD_A, X = X_INPUT_GAMEPAD_X, START = X_INPUT_GAMEPAD_START;

  key("Right", true);
  poll();
  check("driver: walking right before the panel", s.gamepad.thumb_lx > 0);
  active = false;  // F4: the panel opens
  poll();
  check("driver: panel open: neutral while Right is held", s.gamepad.thumb_lx == 0 && s.gamepad.buttons == 0);
  key("Right", false);
  key("Space", true);
  key("Space", false);
  key("Return", true);
  key("Return", false);
  check("driver: taps made in the panel (navigation, confirm) never reach the guest", poll() == 0);
  active = true;  // the panel closes
  check("driver: after closing, no carried tap", poll() == 0 && s.gamepad.thumb_lx == 0);
  key("Space", true);
  key("Space", false);
  check("driver: a fresh tap after closing is the guest's (A)", poll() == A);

  key("Right", true);
  active = false;
  poll();
  active = true;  // closed while Right is still held
  poll();
  check("driver: a key held through the panel is withheld", s.gamepad.thumb_lx == 0);
  key("Right", true, true);  // auto-repeat of the held key
  poll();
  check("driver: its auto-repeat does not free it", s.gamepad.thumb_lx == 0);
  key("Right", false);
  poll();
  key("Right", true);
  poll();
  check("driver: released and pressed again: walking", s.gamepad.thumb_lx > 0);
  key("Right", false);
  poll();

  active = false;
  key("Return", true);  // the panel's own confirm / close key, held while it closes
  active = true;
  key("E", true);  // a fresh attack before the next poll: the held Enter must not ride along as Start
  check("driver: closing key held: no Start, the fresh key acts", poll() == X);
  key("E", false);
  check("driver: still no Start while Enter is held", poll() == 0);
  key("Return", false);
  key("Return", true);
  key("Return", false);
  check("driver: Enter again after its release: Start", poll() == START);

  active = false;
  button(ui::MouseEvent::Button::kLeft, true);  // a click on the panel
  active = true;
  check("driver: a panel click held while it closes gives no attack", poll() == 0);
  button(ui::MouseEvent::Button::kLeft, false);
  poll();
  button(ui::MouseEvent::Button::kLeft, true);
  check("driver: the next click attacks (D-138 rule unchanged)", poll() == X);
  button(ui::MouseEvent::Button::kLeft, false);
  poll();

  active = false;
  poll();
  ui::UISetupEvent lost(nullptr, false);
  driver.OnLostFocus(lost);  // Alt+Tab while the panel is open
  key("Right", true);
  driver.OnGotFocus(focus);
  active = true;
  poll();
  key("Right", true);
  poll();
  check("driver: focus change while open: a key pressed after refocus acts normally", s.gamepad.thumb_lx > 0);
  key("Right", false);
  check("driver: and stops on release", (poll(), s.gamepad.thumb_lx == 0));

  // --- B10 layout (E-319): the panel's own row / footer helpers, the real font and the engine's EN / TR models ----
  // R3HD_PCSET_LAYOUT_DIR holds layout_model_en.txt / layout_model_tr.txt (launcher-model of an HD+ home, which
  // shows all 16 settings). Headless ImGui: metrics only, nothing is rendered or shown.
  {
    const char* dir = std::getenv("R3HD_PCSET_LAYOUT_DIR");
    const char* windir = std::getenv("WINDIR");
    ImGuiContext* ctx = ImGui::CreateContext();
    ImGuiIO& io = ImGui::GetIO();
    io.IniFilename = nullptr;
    io.BackendFlags |= ImGuiBackendFlags_RendererHasTextures;
    ImFontConfig config;
    config.OversampleH = 2;
    config.OversampleV = 1;
    const std::string font_path = std::string(windir ? windir : "C:\\Windows") + "\\Fonts\\segoeui.ttf";
    ImFont* font = io.Fonts->AddFontFromFileTTF(font_path.c_str(), r3hd_pcset::kFontSize, &config,
                                                r3hd_pcset::kFontRanges);
    check("layout: the panel's font (Segoe UI) loads", font != nullptr);
    float old_overflow = 0.0f;
    for (const char* lang : {"en", "tr"}) {
      std::string text;
      if (dir) {
        if (FILE* f = std::fopen((std::string(dir) + "\\layout_model_" + lang + ".txt").c_str(), "rb")) {
          char buf[4096];
          for (size_t n; (n = std::fread(buf, 1, sizeof buf, f)) > 0;) text.append(buf, n);
          std::fclose(f);
        }
      }
      const auto m = r3hd_pcset::ParseModel(text);
      std::printf("layout %s: model ok=%d settings=%zu strings=%zu\n", lang, m.ok, m.settings.size(), m.strings.size());
      check("layout: the engine's model for the language", m.ok && m.settings.size() >= 10 && m.language == lang);
      if (!m.ok || !font) continue;
      auto T = [&](const std::string& k) {
        auto it = m.strings.find(k);
        return it != m.strings.end() && !it->second.empty() ? it->second : k;
      };
      // The panel's longest note for every row: the next-start note with "This session: <longest value>".
      std::vector<std::string> notes;
      for (const auto& s : m.settings) {
        std::string value = s.slider ? "100 %" : "";
        for (const auto& v : s.values) value = T(v.label).size() > value.size() ? T(v.label) : value;
        std::string note = T("Applies the next time the game starts.") + "  " +
                           T("This session: {value}");
        note.replace(note.find("{value}"), 7, value);
        for (const char* other : {"Set by the profile; change it in the Settings app.",
                                  "Can be changed in the Settings app."})
          if (T(other).size() > note.size()) note = T(other);
        notes.push_back(note);
      }
      // Representative windows (physical) at 100 / 125 / 150 % display scaling; the drawer lays out in logical px.
      const float physical[][2] = {{3840, 2160}, {2560, 1440}, {1920, 1080}, {1280, 720}, {1024, 768}, {800, 600}, {640, 480}};
      bool rows_ok = true, controls_ok = true, footer_ok = true, scroll_ok = true, wrapped_any = false;
      for (float scale : {1.0f, 1.25f, 1.5f}) {
        for (const auto& p : physical) {
          const ImVec2 view(std::floor(p[0] / scale), std::floor(p[1] / scale));
          std::vector<r3hd_pcset::RowBoxes> rows;
          ImVec2 win_min, win_max, close_min, close_max;
          float scroll_x = 0.0f, column = 0.0f;
          for (int frame = 0; frame < 4; ++frame) {  // tables and scrollbars settle over the first frames
            rows.clear();
            io.DisplaySize = view;
            io.DeltaTime = 1.0f / 60.0f;
            ImGui::NewFrame();
            ImGui::PushFont(font, r3hd_pcset::kFontSize);
            ImGui::SetNextWindowPos(ImVec2(view.x * 0.5f, view.y * 0.5f), ImGuiCond_Always, ImVec2(0.5f, 0.5f));
            ImGui::SetNextWindowSize(r3hd_pcset::PanelSize(view), ImGuiCond_Always);
            ImGui::Begin("###layout", nullptr, ImGuiWindowFlags_NoCollapse | ImGuiWindowFlags_NoResize |
                                                   ImGuiWindowFlags_NoMove | ImGuiWindowFlags_NoSavedSettings);
            const std::vector<std::string> buttons{T("Apply"), T("Discard changes"), T("Close")};
            const std::string status = T("The settings were changed in the Settings app while this panel was open. "
                                         "They were reloaded: check them and apply again.");
            const float footer = r3hd_pcset::FooterHeight(status, buttons, ImGui::GetContentRegionAvail().x);
            ImGui::BeginChild("##settings", ImVec2(0.0f, -footer), ImGuiChildFlags_None);
            float widest = 0.0f;
            for (const auto& s : m.settings) widest = std::max(widest, ImGui::CalcTextSize(T(s.label).c_str()).x);
            column = r3hd_pcset::LabelColumnWidth(ImGui::GetContentRegionAvail().x, widest);
            old_overflow = std::max(old_overflow, widest - 260.0f);
            for (const auto& [group, name] : m.groups) {
              ImGui::SeparatorText(T(name).c_str());
              if (!r3hd_pcset::BeginSettingRows(group.c_str(), column)) continue;
              for (size_t i = 0; i < m.settings.size(); ++i) {
                const auto& s = m.settings[i];
                if (s.group != group) continue;
                ImGui::PushID(s.key.c_str());
                rows.push_back(r3hd_pcset::DrawSettingRow(T(s.label), notes[i], T(s.help), [&] {
                  if (ImGui::BeginCombo("##v", s.values.empty() ? "100 %" : T(s.values.back().label).c_str()))
                    ImGui::EndCombo();
                }));
                ImGui::PopID();
              }
              r3hd_pcset::EndSettingRows();
            }
            scroll_x = ImGui::GetScrollMaxX();
            ImGui::EndChild();
            ImGui::Separator();
            ImGui::PushTextWrapPos(0.0f);
            ImGui::TextUnformatted(status.c_str());
            ImGui::PopTextWrapPos();
            r3hd_pcset::ButtonFlow flow{ImGui::GetContentRegionAvail().x};
            for (const auto& b : buttons) {
              flow.Next(b);
              ImGui::Button(b.c_str());
            }
            close_min = ImGui::GetItemRectMin();
            close_max = ImGui::GetItemRectMax();
            win_min = ImGui::GetWindowPos();
            win_max = ImVec2(win_min.x + ImGui::GetWindowWidth(), win_min.y + ImGui::GetWindowHeight());
            ImGui::End();
            ImGui::PopFont();
            ImGui::Render();
          }
          const float pad = ImGui::GetStyle().WindowPadding.x;
          for (size_t i = 0; i < rows.size(); ++i) {
            const auto& r = rows[i];
            wrapped_any |= r.label.max.y - r.label.min.y > ImGui::GetTextLineHeight() * 1.5f;
            const bool ok = r.label.max.x < r.control.min.x && r.label.max.x < r.note.min.x &&
                            r.note.min.y >= r.control.max.y && r.label.min.x >= win_min.x + pad - 1.0f &&
                            (i + 1 == rows.size() || rows[i + 1].label.min.y >= std::max(r.label.max.y, r.note.max.y));
            const bool control = r.control.max.x <= win_max.x - pad + 1.0f && r.note.max.x <= win_max.x - pad + 1.0f &&
                                 r.control.max.x - r.control.min.x >= 100.0f;
            if (!ok || !control)
              std::printf("layout %s %.0fx%.0f @%.0f%% row %zu: label %.0f..%.0f,%.0f..%.0f control %.0f..%.0f note "
                          "%.0f..%.0f,%.0f..%.0f\n", lang, p[0], p[1], scale * 100.0f, i, r.label.min.x, r.label.max.x,
                          r.label.min.y, r.label.max.y, r.control.min.x, r.control.max.x, r.note.min.x, r.note.max.x,
                          r.note.min.y, r.note.max.y);
            rows_ok &= ok;
            controls_ok &= control;
          }
          const bool footer_fits = close_max.y <= win_max.y - ImGui::GetStyle().WindowPadding.y + 1.0f &&
                                   close_max.x <= win_max.x - pad + 1.0f;
          if (!footer_fits)
            std::printf("layout %s %.0fx%.0f @%.0f%%: Close %.0f,%.0f window %.0f,%.0f\n", lang, p[0], p[1],
                        scale * 100.0f, close_max.x, close_max.y, win_max.x, win_max.y);
          footer_ok &= footer_fits;
          scroll_ok &= scroll_x == 0.0f;
          if (p[0] == 1920 && scale == 1.0f)
            std::printf("layout %s 1920x1080 @100%%: label column %.0f of %.0f, rows %zu\n", lang, column,
                        win_max.x - win_min.x, rows.size());
        }
      }
      check("layout: labels never reach the control or the note, rows never overlap", rows_ok);
      check("layout: controls and notes stay inside the panel, at least 100 px wide", controls_ok);
      check("layout: the status line and every footer button stay inside the panel", footer_ok);
      check("layout: no horizontal scrolling", scroll_ok);
      check("layout: a long label wraps inside its column (not shortened)", wrapped_any);
    }
    std::printf("layout: widest label exceeds the former fixed 260 px column by %.0f px\n", old_overflow);
    check("layout: the models do contain labels the former fixed column could not hold", old_overflow > 0.0f);
    ImGui::DestroyContext(ctx);
  }

  std::printf("R3HD_HOSTUI_TEST %s %d/%d\n", failures ? "FAIL" : "PASS", checks - failures, checks);
  std::fflush(stdout);
  return failures ? 1 : 0;
}
