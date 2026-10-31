#pragma once
#include <cstdlib>
#include <rex/cvar.h>
#include <rex/rex_app.h>
#include <rex/r3hd_hostui_gate.h>
#include <rex/platform/env.h>
#include <rex/ui/keybinds.h>
#include <rex/logging.h>
#include "m2_trace.h"
#include "r3hd_window_icon.h"
#include "r3hd_discord.h"
#include "r3hd_pc_settings.h"
class R3hdApp : public rex::ReXApp {
 public:
  using rex::ReXApp::ReXApp;
  static std::unique_ptr<rex::ui::WindowedApp> Create(rex::ui::WindowedAppContext& ctx) {
    return std::unique_ptr<R3hdApp>(new R3hdApp(ctx, "r3hd", PPCImageConfig));
  }
  void OnPostInitLogging() override { M2InstallCrashHandler(); REXLOG_INFO("M2 host_start"); M9SelectLicenseMode(); }
  // D-032: this private build runs the title as its full version unless trial mode is requested.
  // Only bit 0 of the upstream license_mask setting is set (the bit the title's full-version latch
  // tests); R3HD_TRIAL leaves the runtime default 0. An explicit non-default license_mask is not
  // touched. This is a compatibility setting, not an ownership or entitlement check.
  static void M9SelectLicenseMode() {
    const bool trial = std::getenv("R3HD_TRIAL") != nullptr;
    const bool explicit_mask = rex::cvar::HasNonDefaultValue("license_mask");
    if (trial) rex::cvar::ResetToDefault("license_mask");
    else if (!explicit_mask) rex::cvar::SetFlagByName("license_mask", "1");
    REXLOG_INFO("M9 license_mode={} source={}", trial ? "trial" : "full",
                trial ? "R3HD_TRIAL" : explicit_mask ? "license_mask setting" : "build default");
  }
  void OnPostLoadXexImage() override { REXLOG_INFO("M2 xex_loaded entry=820E13F8"); }
  void OnPostSetup() override { REXLOG_INFO("M2 runtime_initialized"); }
  void OnPreLaunchModule() override { REXLOG_INFO("M2 launch_prepared"); }
  void OnPostLaunchModule(rex::system::XThread*) override {
    REXLOG_INFO("R3HD discord policy={}", std::getenv("R3HD_NONINTRUSIVE") ? "suppressed" :
                r3hd::DiscordPresence::Enabled() ? "enabled" : "off");
    discord_.Start();
    StartPcSettingsTest();
  }
  void OnGuestThreadExit(rex::system::XThread*) override { REXLOG_INFO("M2 guest_thread_exit"); }
  // D-139: the in-game PC Settings panel (r3hd_pc_settings.h). F4 is reserved in the keyboard map, so it never
  // collides with a player's binding; with -DevOverlay the SDK's own F4 overlay is registered first and wins.
  void OnConfigureFonts(ImFontAtlas* atlas) override {
    const char* windir = std::getenv("WINDIR");
    for (const char* name : {"segoeui.ttf", "tahoma.ttf", "arial.ttf"}) {
      std::string path = std::string(windir ? windir : "C:\\Windows") + "\\Fonts\\" + name;
      if (!std::filesystem::exists(path)) continue;
      ImFontConfig config;
      config.OversampleH = 2;
      config.OversampleV = 1;
      pcset_host_.font = atlas->AddFontFromFileTTF(path.c_str(), r3hd_pcset::kFontSize, &config, r3hd_pcset::kFontRanges);
      REXLOG_INFO("R3HD pcset font={}", name);
      return;
    }
    REXLOG_INFO("R3HD pcset font=default");
  }
  void OnCreateDialogs(rex::ui::ImGuiDrawer* drawer) override {
    pcset_drawer_ = drawer;
    rex::ui::RegisterBind("bind_pc_settings", "F4", "Open or close the PC Settings panel", [this] { TogglePcSettings("key"); });
  }
  void TogglePcSettings(const char* source) {
    if (pcset_) {
      pcset_->RequestClose();
      return;
    }
    if (!pcset_drawer_ || !window()) return;
    SetHostUiInputBlocked(true);  // before the panel draws or takes any event: the guest sees neutral input
    if (std::getenv("R3HD_NONINTRUSIVE")) rex::platform::env::set(r3hd_hostui::kTestSourceBlocked, "1");  // D-142
    window()->SetHostUiCursor(true);
    REXLOG_INFO("R3HD pcset source={}", source);
    pcset_host_.closed = [this] {
      pcset_ = nullptr;
      if (window()) window()->SetHostUiCursor(false);
      SetHostUiInputBlocked(false);  // held input stays withheld until released (r3hd_hostui_gate.h)
      if (std::getenv("R3HD_NONINTRUSIVE")) rex::platform::env::unset(r3hd_hostui::kTestSourceBlocked);  // D-142
    };
    pcset_ = new r3hd_pcset::Panel(pcset_drawer_, pcset_host_, r3hd_pcset::Engine::FromEnvironment(),
                                   r3hd_pcset::ParsePairs(r3hd_pcset::Narrow(r3hd_pcset::Env(L"R3HD_PCSET_SESSION"))));
  }
  // Hidden runs only: R3HD_PCSET_TEST=SECONDS,SECONDS,... toggles the panel at those times after launch (no key,
  // window, focus or cursor change; a hidden window never touches cursor state and never starts the engine).
  void StartPcSettingsTest() {
    const char* plan = std::getenv("R3HD_PCSET_TEST");
    if (!plan || !std::getenv("R3HD_NONINTRUSIVE")) return;
    std::vector<int> times;
    for (const auto& item : r3hd_pcset::Split(plan, ',')) times.push_back(std::atoi(item.c_str()));
    REXLOG_INFO("R3HD pcset test toggles={}", times.size());
    std::thread([this, times] {
      int at = 0;
      for (int t : times) {
        if (t > at) std::this_thread::sleep_for(std::chrono::seconds(t - at));
        at = t;
        app_context().CallInUIThread([this] { TogglePcSettings("test"); });
      }
    }).detach();
  }
  bool OnWindowCloseRequested() override {
    // ReXApp's first OnClosing listener hard-exits: later listeners never run.
    // Clear shell properties while the HWND still exists, before that exit.
    icon_.image.Reset();
    REXLOG_INFO("R3HD icon_cleanup=window_close");
    return true;  // retain the SDK's default close policy
  }
  bool SetupPresentation() override {
    // Distinguish the game from Settings/setup before SDL creates a taskbar button.
    const HRESULT identity = SetCurrentProcessExplicitAppUserModelID(r3hd::kGameAppId);
    REXLOG_INFO("R3HD taskbar_identity={}", SUCCEEDED(identity) ? "game" : "system_fallback");
    if (!rex::ReXApp::SetupPresentation()) return false;
    // Keep the SDK/application IDs used by paths and tests; expose a stable product title to Windows.
    if (window()) window()->SetTitle("Rayman 3 HD Recompiled");
    // The SDK has opened the real HWND, including its initial fullscreen state.
    // It keeps that HWND across fullscreen changes. Never create or show another window.
    if (window() && !game_data_root().empty()) {
      icon_.window = window();
      icon_.file = game_data_root().parent_path() / "play_icon.ico";
      window()->AddListener(&icon_);
      icon_.Apply();
    }
    return true;
  }
  void OnShutdown() override {
    discord_.Stop();
    if (pcset_) {  // the drawer goes away with the app; no input to give back any more
      pcset_host_.closed = nullptr;
      delete pcset_;
      pcset_ = nullptr;
    }
    if (icon_.window) icon_.window->RemoveListener(&icon_);
    icon_.image.Reset();  // guest exit can shut down without an OnClosing event
    icon_.window = nullptr;
  }

 private:
  r3hd::DiscordPresence discord_;
  rex::ui::ImGuiDrawer* pcset_drawer_ = nullptr;
  r3hd_pcset::Panel* pcset_ = nullptr;  // D-139: deletes itself when it closes (ImGuiDialog)
  r3hd_pcset::Host pcset_host_;
  struct IconListener : rex::ui::WindowListener {
    rex::ui::Window* window = nullptr;
    std::filesystem::path file;
    r3hd::WindowIcon image;
    void Apply() {
      const bool local = image.Attach((HWND)window->GetNativeWindowHandle(), file);
      REXLOG_INFO("R3HD window_icon={}", local ? "local_package" : "resource_fallback");
      REXLOG_INFO("R3HD taskbar_icon={}", image.taskbar_local() ? "local_package" : "system_fallback");
    }
    void OnOpened(rex::ui::UISetupEvent&) override { Apply(); }
    void OnClosing(rex::ui::UIEvent&) override { image.Reset(); }
  } icon_;
};
