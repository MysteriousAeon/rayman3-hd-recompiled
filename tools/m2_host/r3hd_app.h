#pragma once
#include <cstdlib>
#include <rex/cvar.h>
#include <rex/rex_app.h>
#include <rex/logging.h>
#include "m2_trace.h"
#include "r3hd_window_icon.h"
#include "r3hd_discord.h"
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
  }
  void OnGuestThreadExit(rex::system::XThread*) override { REXLOG_INFO("M2 guest_thread_exit"); }
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
    if (icon_.window) icon_.window->RemoveListener(&icon_);
    icon_.image.Reset();  // guest exit can shut down without an OnClosing event
    icon_.window = nullptr;
  }

 private:
  r3hd::DiscordPresence discord_;
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
