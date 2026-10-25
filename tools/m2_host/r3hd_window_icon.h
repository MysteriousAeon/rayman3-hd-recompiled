// Host-only presentation. The installer creates this ICO from the owner's package.
// No artwork is linked into the executable. Call Attach/Reset on the window's UI thread.
#pragma once
#include <windows.h>
#include <shobjidl.h>
#include <shellapi.h>
#include <filesystem>
#include <string>

#pragma comment(lib, "shell32.lib")
#pragma comment(lib, "ole32.lib")

namespace r3hd {
inline constexpr wchar_t kGameAppId[] = L"Rayman3HDRecompiled.Game";

// The shell's taskbar group icon is separate from WM_SETICON. Supply documented
// relaunch properties for installed homes, without changing the executable or ICO.
class TaskbarIcon {
 public:
  TaskbarIcon() = default;
  TaskbarIcon(const TaskbarIcon&) = delete;
  TaskbarIcon& operator=(const TaskbarIcon&) = delete;
  ~TaskbarIcon() { Reset(); }
  bool Attach(HWND window, const std::filesystem::path& icon) {
    Reset();
    const auto home = icon.parent_path().parent_path();
    const auto launcher = home / "app" / "r3hd_launcher.exe";
    std::error_code error;
    if (!std::filesystem::is_regular_file(launcher, error)) return false;
    if (FAILED(SHGetPropertyStoreForWindow(window, IID_PPV_ARGS(&store_)))) return false;
    values_[0] = L"\"" + launcher.wstring() + L"\" --play --home \"" + home.wstring() + L"\"";
    values_[1] = icon.wstring() + L",0";
    values_[2] = L"Rayman 3 HD Recompiled";
    values_[3] = kGameAppId;
    // Set ID last: Windows consumes the relaunch properties when grouping the window.
    for (unsigned i = 0; i < 4; ++i) {
      if (FAILED(store_->GetValue(Key(i), &previous_[i]))) { Reset(); return false; }
      PROPVARIANT value{};
      value.vt = VT_LPWSTR;
      value.pwszVal = values_[i].data();
      if (FAILED(store_->SetValue(Key(i), value))) { Reset(); return false; }
      ++assigned_;
    }
    return true;
  }
  void Reset() {
    if (!store_) return;
    for (unsigned i = assigned_; i-- > 0;) {
      PROPVARIANT current{};
      if (SUCCEEDED(store_->GetValue(Key(i), &current)) && current.vt == VT_LPWSTR &&
          current.pwszVal && values_[i] == current.pwszVal)
        store_->SetValue(Key(i), previous_[i]);
      PropVariantClear(&current);
    }
    for (auto& previous : previous_) PropVariantClear(&previous);
    store_->Release();
    store_ = nullptr;
    assigned_ = 0;
  }
  static PROPERTYKEY Key(unsigned i) {
    // System.AppUserModel.{RelaunchCommand,RelaunchIconResource,RelaunchDisplayNameResource,ID}
    return {{0x9f4c2855, 0x9f79, 0x4b39, {0xa8, 0xd0, 0xe1, 0xd4, 0x2d, 0xe1, 0xd5, 0xf3}}, 2 + i};
  }
 private:
  IPropertyStore* store_ = nullptr;
  PROPVARIANT previous_[4]{};
  std::wstring values_[4];
  unsigned assigned_ = 0;
};

class WindowIcon {
 public:
  WindowIcon() = default;
  WindowIcon(const WindowIcon&) = delete;
  WindowIcon& operator=(const WindowIcon&) = delete;
  ~WindowIcon() { Reset(); }

  bool Attach(HWND window, const std::filesystem::path& file) {
    Reset();
    if (!window || !IsWindow(window) || file.empty()) return false;
    // Without LR_SHARED: we own both handles until they are detached from the HWND.
    large_ = Load(file, SM_CXICON, SM_CYICON);
    small_ = Load(file, SM_CXSMICON, SM_CYSMICON);
    if (!large_ || !small_) { Reset(); return false; }
    window_ = window;
    previous_large_ = (HICON)SendMessageW(window_, WM_SETICON, ICON_BIG, (LPARAM)large_);
    previous_small_ = (HICON)SendMessageW(window_, WM_SETICON, ICON_SMALL, (LPARAM)small_);
    taskbar_local_ = taskbar_.Attach(window_, file);
    return true;
  }

  bool taskbar_local() const { return taskbar_local_; }

  void Reset() {
    taskbar_.Reset();
    taskbar_local_ = false;
    if (window_ && IsWindow(window_)) {
      // Do not overwrite an icon another window component has since assigned.
      if ((HICON)SendMessageW(window_, WM_GETICON, ICON_BIG, 0) == large_)
        SendMessageW(window_, WM_SETICON, ICON_BIG, (LPARAM)previous_large_);
      if ((HICON)SendMessageW(window_, WM_GETICON, ICON_SMALL, 0) == small_)
        SendMessageW(window_, WM_SETICON, ICON_SMALL, (LPARAM)previous_small_);
    }
    window_ = nullptr;
    if (large_) DestroyIcon(large_);
    if (small_) DestroyIcon(small_);
    large_ = small_ = previous_large_ = previous_small_ = nullptr;
  }

 private:
  static HICON Load(const std::filesystem::path& file, int x, int y) {
    return (HICON)LoadImageW(nullptr, file.c_str(), IMAGE_ICON,
                           GetSystemMetrics(x), GetSystemMetrics(y), LR_LOADFROMFILE);
  }
  HWND window_ = nullptr;
  HICON large_ = nullptr, small_ = nullptr;
  HICON previous_large_ = nullptr, previous_small_ = nullptr;
  TaskbarIcon taskbar_;
  bool taskbar_local_ = false;
};
}  // namespace r3hd
