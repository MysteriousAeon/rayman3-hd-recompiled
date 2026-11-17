// D-220: DXGI API probe of the display V-Sync swap-chain rules, on a window that is never shown (no game, no
// input, no focus, no visible window). Uses r3hd_display_vsync.h for every flag and Present argument, so it checks
// the exact values the D3D12 presenter patch uses:
//   * both modes: create a 3-buffer FLIP_DISCARD swap chain with SwapChainFlags(mode, tearing), present 120 frames
//     with Choose(mode, tearing), ResizeBuffers with the same flags, present 60 more, destroy and recreate;
//   * On: SetMaximumFrameLatency(1) and the waitable object; every wait is bounded (kLatencyWaitTimeoutMs) and
//     counted; the object still works after ResizeBuffers;
//   * negative controls: ResizeBuffers that drops FRAME_LATENCY_WAITABLE_OBJECT is rejected; Present(1,
//     ALLOW_TEARING) is rejected (why On never passes the tearing flag).
// A hidden window is not composed, so this proves API acceptance and lifecycle, not what a display shows.
// Exit 0 PASS, 1 FAIL, 77 SKIP (no hardware Direct3D 12 device).
#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#include <windows.h>
#include <d3d12.h>
#include <dxgi1_6.h>
#include <wrl/client.h>

#include <chrono>
#include <cstdio>

#include "r3hd_display_vsync.h"

using Microsoft::WRL::ComPtr;
static int g_checks = 0, g_fails = 0;
static void Check(bool ok, const char* what, HRESULT hr = S_OK) {
  ++g_checks;
  if (!ok) {
    ++g_fails;
    std::printf("FAIL %s hr=%08X\n", what, unsigned(hr));
  }
}

static_assert(r3hdvsync::kPresentRestart == DXGI_PRESENT_RESTART);
static_assert(r3hdvsync::kPresentAllowTearing == DXGI_PRESENT_ALLOW_TEARING);
static_assert(r3hdvsync::kSwapChainAllowTearing == DXGI_SWAP_CHAIN_FLAG_ALLOW_TEARING);
static_assert(r3hdvsync::kSwapChainLatencyWaitable == DXGI_SWAP_CHAIN_FLAG_FRAME_LATENCY_WAITABLE_OBJECT);

struct Counts {
  int presents = 0, failed = 0, timeouts = 0;
  long long wait_us_max = 0;
};

static void PresentFrames(IDXGISwapChain3* sc, HANDLE waitable, bool vsync, bool tearing, int n, Counts& c) {
  const r3hdvsync::PresentArgs a = r3hdvsync::Choose(vsync, tearing);
  for (int i = 0; i < n; ++i) {
    if (waitable) {
      auto t0 = std::chrono::steady_clock::now();
      if (WaitForSingleObjectEx(waitable, r3hdvsync::kLatencyWaitTimeoutMs, TRUE) == WAIT_TIMEOUT) ++c.timeouts;
      long long us = std::chrono::duration_cast<std::chrono::microseconds>(std::chrono::steady_clock::now() - t0).count();
      if (us > c.wait_us_max) c.wait_us_max = us;
    }
    HRESULT hr = sc->Present(a.sync_interval, a.flags);
    ++c.presents;
    if (FAILED(hr)) ++c.failed;
  }
}

int main() {
  ComPtr<IDXGIFactory4> factory;
  if (FAILED(CreateDXGIFactory2(0, IID_PPV_ARGS(&factory)))) return std::printf("SKIP no DXGI factory\n"), 77;
  ComPtr<ID3D12Device> device;
  if (FAILED(D3D12CreateDevice(nullptr, D3D_FEATURE_LEVEL_11_0, IID_PPV_ARGS(&device))))
    return std::printf("R3HD_DISPLAY_VSYNC_DXGI_PROBE SKIP no Direct3D 12 device\n"), 77;
  D3D12_COMMAND_QUEUE_DESC qd = {};
  qd.Type = D3D12_COMMAND_LIST_TYPE_DIRECT;
  ComPtr<ID3D12CommandQueue> queue;
  Check(SUCCEEDED(device->CreateCommandQueue(&qd, IID_PPV_ARGS(&queue))), "command queue");
  // As the presenter's AwaitSwapChainUsageCompletion: the queue must be idle before ResizeBuffers or destruction.
  ComPtr<ID3D12Fence> fence;
  Check(SUCCEEDED(device->CreateFence(0, D3D12_FENCE_FLAG_NONE, IID_PPV_ARGS(&fence))), "fence");
  HANDLE fence_event = CreateEventW(nullptr, FALSE, FALSE, nullptr);
  UINT64 fence_value = 0;
  auto flush = [&] {
    queue->Signal(fence.Get(), ++fence_value);
    if (fence->GetCompletedValue() < fence_value) {
      fence->SetEventOnCompletion(fence_value, fence_event);
      WaitForSingleObject(fence_event, 5000);
    }
  };
  BOOL tearing_feature = FALSE;
  ComPtr<IDXGIFactory5> f5;
  bool tearing = SUCCEEDED(factory.As(&f5)) &&
                 SUCCEEDED(f5->CheckFeatureSupport(DXGI_FEATURE_PRESENT_ALLOW_TEARING, &tearing_feature,
                                                   sizeof(tearing_feature))) &&
                 tearing_feature;

  // A window that is never shown: no WS_VISIBLE, no ShowWindow, no activation.
  WNDCLASSEXW wc = {sizeof(wc)};
  wc.lpfnWndProc = DefWindowProcW;
  wc.hInstance = GetModuleHandleW(nullptr);
  wc.lpszClassName = L"R3HDVSyncProbe";
  RegisterClassExW(&wc);
  HWND hwnd = CreateWindowExW(WS_EX_NOACTIVATE | WS_EX_TOOLWINDOW, wc.lpszClassName, L"", WS_POPUP, 0, 0, 640, 360,
                              nullptr, nullptr, wc.hInstance, nullptr);
  Check(hwnd && !IsWindowVisible(hwnd), "hidden window");
  factory->MakeWindowAssociation(hwnd, DXGI_MWA_NO_ALT_ENTER);

  for (bool vsync : {false, true}) {
    for (int round = 0; round < 2; ++round) {  // create, use, resize, destroy; then recreate (as a reconnection)
      DXGI_SWAP_CHAIN_DESC1 d = {};
      d.Width = 640;
      d.Height = 360;
      d.Format = DXGI_FORMAT_B8G8R8A8_UNORM;
      d.SampleDesc.Count = 1;
      d.BufferUsage = DXGI_USAGE_RENDER_TARGET_OUTPUT;
      d.BufferCount = 3;
      d.SwapEffect = DXGI_SWAP_EFFECT_FLIP_DISCARD;
      d.AlphaMode = DXGI_ALPHA_MODE_IGNORE;
      d.Flags = r3hdvsync::SwapChainFlags(vsync, tearing);
      ComPtr<IDXGISwapChain1> sc1;
      HRESULT hr = factory->CreateSwapChainForHwnd(queue.Get(), hwnd, &d, nullptr, nullptr, &sc1);
      Check(SUCCEEDED(hr), vsync ? "on: create" : "off: create", hr);
      if (FAILED(hr)) continue;
      ComPtr<IDXGISwapChain3> sc;
      sc1.As(&sc);
      HANDLE waitable = nullptr;
      if (vsync) {
        hr = sc->SetMaximumFrameLatency(r3hdvsync::kMaxFrameLatency);
        Check(SUCCEEDED(hr), "on: SetMaximumFrameLatency(1)", hr);
        UINT latency = 0;
        sc->GetMaximumFrameLatency(&latency);
        Check(latency == r3hdvsync::kMaxFrameLatency, "on: maximum latency reads back 1");
        waitable = sc->GetFrameLatencyWaitableObject();
        Check(waitable != nullptr, "on: waitable object");
      } else {
        Check((d.Flags & DXGI_SWAP_CHAIN_FLAG_FRAME_LATENCY_WAITABLE_OBJECT) == 0, "off: no latency object requested");
      }
      Counts c;
      PresentFrames(sc.Get(), waitable, vsync, tearing, 120, c);
      flush();
      if (vsync && round == 0) {
        // Negative controls: both are invalid calls that the implementation must never make.
        HRESULT bad = sc->ResizeBuffers(0, 800, 450, DXGI_FORMAT_UNKNOWN, r3hdvsync::SwapChainFlags(false, tearing));
        Check(FAILED(bad), "on: ResizeBuffers without the waitable flag is rejected", bad);
        if (tearing) {
          // No latency wait first: a rejected present would never return the count it took.
          HRESULT badp = sc->Present(1, DXGI_PRESENT_ALLOW_TEARING);
          Check(badp == DXGI_ERROR_INVALID_CALL, "on: Present(1, ALLOW_TEARING) is rejected", badp);
        }
      }
      flush();
      hr = sc->ResizeBuffers(0, 800, 450, DXGI_FORMAT_UNKNOWN, r3hdvsync::SwapChainFlags(vsync, tearing));
      Check(SUCCEEDED(hr), vsync ? "on: ResizeBuffers with the creation flags" : "off: ResizeBuffers (pinned flags)", hr);
      PresentFrames(sc.Get(), waitable, vsync, tearing, 60, c);
      Check(c.failed == 0, vsync ? "on: every present accepted" : "off: every present accepted");
      Check(c.timeouts <= 2, vsync ? "on: latency waits return (bounded, no stall)" : "off: no waits");
      std::printf("%s round=%d tearing_supported=%d flags=0x%X sync_interval=%u present_flags=0x%X presents=%d "
                  "failed=%d wait_timeouts=%d wait_max_us=%lld\n",
                  vsync ? "on " : "off", round, tearing ? 1 : 0, d.Flags, r3hdvsync::Choose(vsync, tearing).sync_interval,
                  r3hdvsync::Choose(vsync, tearing).flags, c.presents, c.failed, c.timeouts, c.wait_us_max);
      flush();
      if (waitable) CloseHandle(waitable);
      sc.Reset();
      sc1.Reset();
    }
  }
  CloseHandle(fence_event);
  DestroyWindow(hwnd);
  std::printf("R3HD_DISPLAY_VSYNC_DXGI_PROBE %s %d checks\n", g_fails ? "FAIL" : "PASS", g_checks);
  return g_fails ? 1 : 0;
}
