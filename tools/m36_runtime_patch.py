"""Replay after the M33 patch at the same pin: a mod plan may grow the subtitle table (M36, D-073).

`tools/m33_mod_overlay.h` (installed by m33_runtime_patch.py) gained a plan record `grow <file> <size>`: one file named
in its kGrowNames (VS.sub) may be longer for the guest than on disk, by at most kMaxGrowBytes, with every byte past
the host file's end defined by the plan's ranges. Two sites, both gated by m33mods::Enabled() (R3HD_MODS_PLAN) and a
no-op unless the active plan has a `grow` record for that very file:

  * HostPathFile::ReadSync: after the host read and before the M26 / M33 overlays, m33mods::ExtendRead completes a
    read that reaches past the file's end up to the guest size (zeros, which the M33 overlay then replaces by the
    plan's tail bytes). host_path_file.cpp is rebuilt from the pin by m20_runtime_patch.py on every replay, then
    m26, m33 and this script patch it in order.
  * HostPathEntry::Create / update(): the entry's size (what NtQueryFullAttributesFile, NtQueryInformationFile and
    NtQueryDirectoryFile report) is m33mods::GuestSize. host_path_entry.cpp is patched by this script only.

Host-only: no generated code, no guest patch, no guest allocation, no file written.
"""
from m8_runtime_patch import patch_once

if __name__ == '__main__':
    patch_once('src/filesystem/devices/host_path_file.cpp', [
        ('  if (file_handle_->Read(byte_offset, buffer.data(), buffer.size(), out_bytes_read)) {\n'
         '    // M26 (D-058)',
         '  bool host_read = file_handle_->Read(byte_offset, buffer.data(), buffer.size(), out_bytes_read);\n'
         '  // M36 (D-073): off unless the active plan grows this file (VS.sub only): a read past the file\'s end is\n'
         '  // completed up to the size the guest was told, and the M33 overlay below fills it with the plan\'s bytes.\n'
         '  if (m33mods::Enabled()) {\n'
         '    host_read = m33mods::ExtendRead(static_cast<HostPathEntry*>(entry())->host_path(), byte_offset,\n'
         '                                    buffer.data(), buffer.size(), host_read, out_bytes_read, &M33Log);\n'
         '  }\n'
         '  if (host_read) {\n'
         '    // M26 (D-058)'),
    ])
    patch_once('src/filesystem/devices/host_path_entry.cpp', [
        ('#include <rex/string.h>\n\nnamespace rex::filesystem {\n',
         '#include <rex/string.h>\n#include <rex/m33_mod_overlay.h>\n\nnamespace rex::filesystem {\n\n'
         '// M36 (D-073): a mod plan may grow one file for the guest, see tools/m33_mod_overlay.h.\n'
         'static void M36Log(const char* line) {\n  REXLOG_INFO("{}", line);\n}\n'),
        ('    entry->size_ = file_info.total_size;\n'
         '    entry->allocation_size_ = rex::round_up(file_info.total_size, device->bytes_per_sector());\n',
         '    entry->size_ = file_info.total_size;\n'
         '    // M36 (D-073): the size the guest sees; unchanged unless the active plan grows this file.\n'
         '    if (m33mods::Enabled()) entry->size_ = m33mods::GuestSize(full_path, entry->size_, &M36Log);\n'
         '    entry->allocation_size_ = rex::round_up(entry->size_, device->bytes_per_sector());\n'),
        ('    size_ = file_info.total_size;\n'
         '    allocation_size_ = rex::round_up(file_info.total_size, device()->bytes_per_sector());\n',
         '    size_ = file_info.total_size;\n'
         '    // M36 (D-073): as in Create.\n'
         '    if (m33mods::Enabled()) size_ = m33mods::GuestSize(host_path_, size_, &M36Log);\n'
         '    allocation_size_ = rex::round_up(size_, device()->bytes_per_sector());\n'),
    ])
