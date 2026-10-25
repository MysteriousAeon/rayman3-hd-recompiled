// Native icon ownership test only: no game, renderer, sound, input or visible window.
#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#include "m2_host/r3hd_window_icon.h"
#include <cstdio>

int wmain(int argc, wchar_t** argv) {
  if (argc != 2) return 2;
  wchar_t desktop_name[80];
  swprintf_s(desktop_name, L"R3HDIconTest_%lu", GetCurrentProcessId());
  HDESK desktop = CreateDesktopW(desktop_name, nullptr, nullptr, 0, GENERIC_ALL, nullptr);
  if (!desktop || !SetThreadDesktop(desktop)) return 3;
  WNDCLASSW cls{};
  cls.lpfnWndProc = DefWindowProcW;
  cls.hInstance = GetModuleHandleW(nullptr);
  cls.lpszClassName = L"R3HDIconTest";
  cls.hIcon = LoadIconW(nullptr, MAKEINTRESOURCEW(32512));
  if (!RegisterClassW(&cls)) return 4;
  int checks = 0, failures = 0;
  auto check = [&](bool ok) { ++checks; if (!ok) { ++failures; std::printf("FAIL check %d\n", checks); } };
  CoInitializeEx(nullptr, COINIT_APARTMENTTHREADED);
  check(SUCCEEDED(SetCurrentProcessExplicitAppUserModelID(r3hd::kGameAppId)));
  PWSTR identity = nullptr;
  check(SUCCEEDED(GetCurrentProcessExplicitAppUserModelID(&identity)) && identity &&
        wcscmp(identity, r3hd::kGameAppId) == 0);
  CoTaskMemFree(identity);
  const std::filesystem::path file = argv[1];
  const bool installed = std::filesystem::is_regular_file(file.parent_path().parent_path() / "app/r3hd_launcher.exe");
  DWORD before = 0;
  for (int i = 0; i < 50; ++i) {
    HWND window = CreateWindowExW(WS_EX_NOACTIVATE, cls.lpszClassName, L"Icon test",
                                 WS_OVERLAPPEDWINDOW, 0, 0, 320, 240, nullptr, nullptr, cls.hInstance, nullptr);
    check(window != nullptr && !IsWindowVisible(window));
    HICON fallback = (HICON)SendMessageW(window, WM_GETICON, ICON_BIG, 0);
    r3hd::WindowIcon icon;
    check(!icon.Attach(window, L"Z:\\R3HD_missing_icon.ico"));
    check((HICON)SendMessageW(window, WM_GETICON, ICON_BIG, 0) == fallback);
    if (installed) {
      IPropertyStore* store = nullptr;
      check(SUCCEEDED(SHGetPropertyStoreForWindow(window, IID_PPV_ARGS(&store))));
      if (store) {
        PROPVARIANT value{};
        value.vt = VT_LPWSTR;
        value.pwszVal = const_cast<wchar_t*>(L"Previous.Identity");
        check(SUCCEEDED(store->SetValue(r3hd::TaskbarIcon::Key(3), value)));
        store->Release();
      }
    }
    check(icon.Attach(window, argv[1]));
    check(icon.taskbar_local() == installed);
    if (installed) {
      IPropertyStore* store = nullptr;
      check(SUCCEEDED(SHGetPropertyStoreForWindow(window, IID_PPV_ARGS(&store))));
      if (store) {
        const auto home = file.parent_path().parent_path();
        const std::wstring expected[] = {
          L"\"" + (home / "app" / "r3hd_launcher.exe").wstring() + L"\" --play --home \"" + home.wstring() + L"\"",
          file.wstring() + L",0", L"Rayman 3 HD Recompiled", r3hd::kGameAppId};
        for (unsigned n = 0; n < 4; ++n) {
          PROPVARIANT value{};
          check(SUCCEEDED(store->GetValue(r3hd::TaskbarIcon::Key(n), &value)) &&
                value.vt == VT_LPWSTR && value.pwszVal && expected[n] == value.pwszVal);
          PropVariantClear(&value);
        }
        store->Release();
      }
    }
    HICON large = (HICON)SendMessageW(window, WM_GETICON, ICON_BIG, 0);
    HICON small_icon = (HICON)SendMessageW(window, WM_GETICON, ICON_SMALL, 0);
    check(large && small_icon && large != small_icon);
    ICONINFO info{};
    check(GetIconInfo(large, &info) != 0);
    if (info.hbmColor) DeleteObject(info.hbmColor);
    if (info.hbmMask) DeleteObject(info.hbmMask);
    // Borderless/windowed style changes on the same hidden HWND retain both icons.
    SetWindowLongPtrW(window, GWL_STYLE, WS_POPUP);
    check((HICON)SendMessageW(window, WM_GETICON, ICON_BIG, 0) == large);
    SetWindowLongPtrW(window, GWL_STYLE, WS_OVERLAPPEDWINDOW);
    check((HICON)SendMessageW(window, WM_GETICON, ICON_SMALL, 0) == small_icon);
    if (installed && i == 49) {
      IPropertyStore* store = nullptr;
      check(SUCCEEDED(SHGetPropertyStoreForWindow(window, IID_PPV_ARGS(&store))));
      if (store) {
        PROPVARIANT value{};
        value.vt = VT_LPWSTR;
        value.pwszVal = const_cast<wchar_t*>(L"OtherOwner.Identity");
        check(SUCCEEDED(store->SetValue(r3hd::TaskbarIcon::Key(3), value)));
        store->Release();
      }
    }
    icon.Reset();
    if (installed) {
      IPropertyStore* store = nullptr;
      check(SUCCEEDED(SHGetPropertyStoreForWindow(window, IID_PPV_ARGS(&store))));
      if (store) {
        for (unsigned n = 0; n < 4; ++n) {
          PROPVARIANT value{};
          const bool read = SUCCEEDED(store->GetValue(r3hd::TaskbarIcon::Key(n), &value));
          check(read && (n == 3 ? value.vt == VT_LPWSTR && value.pwszVal &&
                wcscmp(value.pwszVal, i == 49 ? L"OtherOwner.Identity" : L"Previous.Identity") == 0
                : value.vt == VT_EMPTY));
          PropVariantClear(&value);
        }
        store->Release();
      }
    }
    check((HICON)SendMessageW(window, WM_GETICON, ICON_BIG, 0) == fallback);
    check(!SendMessageW(window, WM_GETICON, ICON_SMALL, 0));
    check(icon.Attach(window, argv[1]));
    // Also exercise cleanup after native destruction and repeated cleanup.
    DestroyWindow(window);
    icon.Reset();
    icon.Reset();
    // Warm up Win32 class/cursor caches before checking repeated ownership.
    if (i == 0) before = GetGuiResources(GetCurrentProcess(), GR_USEROBJECTS);
  }
  check(GetGuiResources(GetCurrentProcess(), GR_USEROBJECTS) == before);
  UnregisterClassW(cls.lpszClassName, cls.hInstance);
  CoUninitialize();
  // The process exits on this private desktop; it was never switched onto a display.
  std::printf("PRESENTATION_ICON %s %d/%d\n", failures ? "FAIL" : "PASS", checks - failures, checks);
  return failures ? 1 : 0;
}
