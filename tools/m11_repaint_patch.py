"""Replay after m11_runtime_patch at the same pin: no continuous UI repaint for an idle overlay (D-035).

Measured in the M11 baseline: the host swap chain was presented about 300 times per second (once per display
refresh on a 239 Hz display, plus once per guest frame) while the title produced 60 frames per second. Cause: the
application always registers the achievement toast dialog, and the overlay drawer asks for another UI paint after
every paint while any dialog exists, whether or not it has anything to show.

Change: a dialog can say that it does not need continuous repainting, and the toast says so while its queue is
empty. Every guest frame still triggers a UI-thread paint (paint mode kUIThreadOnRequest), which draws the
dialogs, so a pushed toast appears with the next guest frame and then animates continuously as before. All other
dialogs (debug overlay, console, settings, message boxes) keep the default: continuous repaint.
Nothing about guest rendering, timing or vsync changes.
"""
from m8_runtime_patch import patch_once

if __name__ == '__main__':
    patch_once('include/rex/ui/imgui_dialog.h', [
        ('  void Draw();\n\n protected:\n  ImGuiDialog(ImGuiDrawer* imgui_drawer);\n',
         '  void Draw();\n\n'
         '  // M11 (D-035): false while the dialog has nothing to show or animate. The drawer then stops asking\n'
         '  // for a UI paint after every paint; paints caused by new guest frames still draw the dialog.\n'
         '  virtual bool NeedsContinuousRepaint() const { return true; }\n\n'
         ' protected:\n  ImGuiDialog(ImGuiDrawer* imgui_drawer);\n'),
    ])
    patch_once('src/ui/imgui_drawer.cpp', [
        ('  if (!dialogs_.empty()) {\n'
         '    // Repaint (and handle input) continuously if still active. In detached mode\n',
         '  bool m11_repaint = false;\n'
         '  for (ImGuiDialog* dialog : dialogs_) {\n'
         '    m11_repaint = m11_repaint || dialog->NeedsContinuousRepaint();\n'
         '  }\n'
         '  if (m11_repaint) {\n'
         '    // Repaint (and handle input) continuously if still active. In detached mode\n'),
    ])
    patch_once('include/rex/ui/overlay/achievement_toast.h', [
        ('#include <chrono>\n', '#include <atomic>\n#include <chrono>\n'),
        ('  void Push(const rex::system::AchievementEvent& event) override;\n',
         '  void Push(const rex::system::AchievementEvent& event) override;\n\n'
         '  // M11 (D-035): idle until a toast is queued.\n'
         '  bool NeedsContinuousRepaint() const override { return m11_pending_.load(std::memory_order_relaxed); }\n'),
        ('  std::deque<PendingToast> queue_;\n',
         '  std::deque<PendingToast> queue_;\n  std::atomic<bool> m11_pending_{false};\n'),
    ])
    patch_once('src/ui/overlay/achievement_toast.cpp', [
        ('  queue_.push_back({event, std::chrono::steady_clock::now()});\n',
         '  queue_.push_back({event, std::chrono::steady_clock::now()});\n'
         '  m11_pending_.store(true, std::memory_order_relaxed);\n'),
        ('    if (queue_.empty()) {\n      return;\n    }\n    toast = queue_.front();\n',
         '    if (queue_.empty()) {\n'
         '      m11_pending_.store(false, std::memory_order_relaxed);\n'
         '      return;\n    }\n    toast = queue_.front();\n'),
    ])
