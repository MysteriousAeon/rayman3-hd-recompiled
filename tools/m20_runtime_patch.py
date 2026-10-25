"""Replay after M17 at the same pin: staged replacement of saved-game content (M20, D-049).

The pinned content manager serves `XamContentCreate*` with CREATE_ALWAYS by deleting the content directory and
its header file before the title writes the new file, so a process that dies between the create and the close
has lost the previous save. With this patch a CREATE_ALWAYS create mounts a private staging directory
(`<xuid>/<title>/.staging/<pid>.<seq>/content`) as the content root; `XamContentClose` flushes the staged files
and renames them over the live ones (`tools/m20_save_commit.h`). The guest sees what it saw before: an empty
root after the create, disposition "created", success from the close. The data file is renamed first, the
content manager's header file last. A commit whose data cannot be replaced leaves the previous save and header
in place and the close returns ERROR_ACCESS_DENIED; so does a close with nothing written over content that has
files. Tested against the end of the process; nothing is claimed about power loss (D-049).

`R3HD_SAVE_COMMIT=legacy` selects the pinned sequence (comparison only). `R3HD_SAVE_FAULT=<point>[:n]` is the
test-only fault injection of `tools/m20_save_check.py`; `tools/play.ps1` clears both.

Host-only: no guest memory is written, no generated code changes, no other file of the profile is touched.
"""
from m3_runtime_patch import patch
from m8_runtime_patch import patch_once
from m16_runtime_patch import install

if __name__ == '__main__':
    install('m20_save_commit.h')

    # content_manager.h / .cpp and host_path_file.cpp are patched by this script only: always from the pin.
    patch('include/rex/system/xam/content_manager.h', [
        ('  uint32_t GetPackageLicense() const { return license_; }\n',
         '  uint32_t GetPackageLicense() const { return license_; }\n'
         '\n'
         '  // M20 (D-049): the staging directory behind this package (an m20save::Stage), when it has one.\n'
         '  std::shared_ptr<void> m20_stage;\n'),
        ('  X_RESULT CloseContent(const std::string_view root_name);\n',
         '  X_RESULT CloseContent(const std::string_view root_name);\n'
         '  // M20 (D-049): CREATE_ALWAYS without deleting the existing content first; committed by CloseContent.\n'
         '  X_RESULT CreateContentStaged(const std::string_view root_name, uint64_t xuid,\n'
         '                               const XCONTENT_AGGREGATE_DATA& data);\n'
         '  static bool M20StagedCommitEnabled();\n'
         '  static void M20FaultExitAfterCreate();\n'),
    ])

    patch('src/system/xam/content_manager.cpp', [
        ('#include <rex/system/xobject.h>\n',
         '#include <rex/system/xobject.h>\n#include <rex/logging.h>\n#include <rex/m20_save_commit.h>\n'),
        ('ContentPackage::~ContentPackage() {\n'
         '  auto fs = kernel_state_->file_system();\n'
         '  fs->UnregisterSymbolicLink(root_name_ + ":");\n'
         '  fs->UnregisterDevice(device_path_);\n'
         '}\n',
         'ContentPackage::~ContentPackage() {\n'
         '  auto fs = kernel_state_->file_system();\n'
         '  fs->UnregisterSymbolicLink(root_name_ + ":");\n'
         '  fs->UnregisterDevice(device_path_);\n'
         '  if (m20_stage) {\n'
         '    // M20 (D-049): unmounted without a close; the staged content is dropped, the live one stays.\n'
         '    m20save::Abort(*static_cast<m20save::Stage*>(m20_stage.get()));\n'
         '  }\n'
         '}\n'
         '\n'
         '// M20 (D-049): staged replacement of saved-game content, see tools/m20_save_commit.h.\n'
         'static void M20Log(const char* line) {\n'
         '  REXLOG_INFO("{}", line);\n'
         '  if (std::strstr(line, "fault=")) {\n'
         '    rex::FlushLogging();  // test-only: the line must be on disk before the process ends\n'
         '  }\n'
         '}\n'
         '\n'
         'bool ContentManager::M20StagedCommitEnabled() {\n'
         '  return m20save::Enabled();\n'
         '}\n'
         '\n'
         'void ContentManager::M20FaultExitAfterCreate() {\n'
         '  m20save::state().log = &M20Log;\n'
         '  m20save::FaultExit(m20save::Fault::kExitAfterCreate);\n'
         '}\n'
         '\n'
         'X_RESULT ContentManager::CreateContentStaged(const std::string_view root_name, uint64_t xuid,\n'
         '                                             const XCONTENT_AGGREGATE_DATA& data) {\n'
         '  m20save::state().log = &M20Log;\n'
         '  {\n'
         '    auto global_lock = global_critical_region_.Acquire();\n'
         '    if (open_packages_.count(string::string_key_case(root_name))) {\n'
         '      return X_ERROR_ALREADY_EXISTS;\n'
         '    }\n'
         '  }\n'
         '\n'
         '  // The header exactly as WriteContentHeaderFile would write it.\n'
         '  XCONTENT_AGGREGATE_DATA header = data;\n'
         '  if (header.title_id == uint32_t(-1)) {\n'
         '    header.title_id = kernel_state_->title_id();\n'
         '  }\n'
         '  if (header.xuid == uint64_t(-1)) {\n'
         '    header.xuid = xuid;\n'
         '  }\n'
         '  uint64_t used_xuid =\n'
         '      (header.xuid != uint64_t(-1) && header.xuid != 0) ? uint64_t(header.xuid) : xuid;\n'
         '\n'
         '  auto package_path = ResolvePackagePath(xuid, data);\n'
         '  // <xuid>/<title id>/.staging: beside the content-type directories, never enumerated as content.\n'
         '  auto staging_root = package_path.parent_path().parent_path() / m20save::kStagingDirName;\n'
         '  m20save::Sweep(staging_root);\n'
         '  auto stage = std::make_shared<m20save::Stage>();\n'
         '  if (!m20save::Begin(staging_root, stage.get())) {\n'
         '    REXLOG_INFO("M20 save stage result=failed content={}", data.file_name());\n'
         '    return X_ERROR_ACCESS_DENIED;\n'
         '  }\n'
         '  stage->live = package_path;\n'
         '  stage->header = ResolvePackageHeaderPath(header.file_name(), used_xuid, header.title_id,\n'
         '                                           header.content_type);\n'
         '  const auto* header_begin = reinterpret_cast<const uint8_t*>(&header);\n'
         '  stage->header_bytes.assign(header_begin, header_begin + sizeof(XCONTENT_AGGREGATE_DATA));\n'
         '  REXLOG_INFO("M20 save stage result=ok content={} stage={} replaces_existing={}", data.file_name(),\n'
         '              rex::path_to_utf8(stage->base.filename()), std::filesystem::exists(package_path));\n'
         '\n'
         '  auto package = std::make_unique<ContentPackage>(kernel_state_, root_name, data, stage->content);\n'
         '  package->m20_stage = stage;\n'
         '  {\n'
         '    auto global_lock = global_critical_region_.Acquire();\n'
         '    if (open_packages_.count(string::string_key_case(root_name))) {\n'
         '      return X_ERROR_ALREADY_EXISTS;  // the package destructor drops the stage\n'
         '    }\n'
         '    open_packages_.insert({string::string_key_case::create(root_name), package.release()});\n'
         '  }\n'
         '  return X_ERROR_SUCCESS;\n'
         '}\n'),
        ('    package = DetachPackage(it);\n'
         '  }\n'
         '  delete package;\n'
         '  return X_ERROR_SUCCESS;\n'
         '}\n'
         '\n'
         'X_RESULT ContentManager::GetContentThumbnail(',
         '    package = DetachPackage(it);\n'
         '  }\n'
         '  // M20 (D-049): the guest closed staged content. Its files are closed and the device is gone before the\n'
         '  // staged files replace the live ones; a failed commit leaves the previous content in place.\n'
         '  std::shared_ptr<void> m20_stage = std::move(package->m20_stage);\n'
         '  package->m20_stage.reset();\n'
         '  delete package;\n'
         '  if (m20_stage) {\n'
         '    auto committed = m20save::Commit(*static_cast<m20save::Stage*>(m20_stage.get()));\n'
         '    if (committed != m20save::Result::kOk) {\n'
         '      return X_ERROR_ACCESS_DENIED;\n'
         '    }\n'
         '  }\n'
         '  return X_ERROR_SUCCESS;\n'
         '}\n'
         '\n'
         'X_RESULT ContentManager::GetContentThumbnail('),
        # A stage left by a process that died is removed the first time the title lists that content type.
        ('  auto package_root = ResolvePackageRoot(xuid, content_type, title_id);\n'
         '  auto file_infos = rex::filesystem::ListFiles(package_root);\n',
         '  auto package_root = ResolvePackageRoot(xuid, content_type, title_id);\n'
         '  if (m20save::Enabled()) {\n'
         '    // M20 (D-049): stages of processes that no longer exist.\n'
         '    m20save::state().log = &M20Log;\n'
         '    m20save::Sweep(package_root.parent_path() / m20save::kStagingDirName);\n'
         '  }\n'
         '  auto file_infos = rex::filesystem::ListFiles(package_root);\n'),
    ])

    patch_once('src/kernel/xam/xam_content.cpp', [
        ('    X_RESULT result = X_ERROR_INVALID_PARAMETER;\n'
         '    kDispositionState disposition = kDispositionState::Unknown;\n'
         '    switch (flags & 0xF) {\n',
         '    X_RESULT result = X_ERROR_INVALID_PARAMETER;\n'
         '    kDispositionState disposition = kDispositionState::Unknown;\n'
         '    bool m20_staged = false;  // M20 (D-049)\n'
         '    switch (flags & 0xF) {\n'),
        ('        content_manager->CloseContent(root_name);\n'
         '        if (content_manager->ContentExists(xuid, content_data)) {\n'
         '          content_manager->DeleteContent(xuid, content_data);\n'
         '        }\n',
         '        content_manager->CloseContent(root_name);\n'
         '        if (rex::system::xam::ContentManager::M20StagedCommitEnabled()) {\n'
         '          // M20 (D-049): the new content is staged and replaces the existing one at the close; nothing\n'
         '          // is deleted here. The guest gets an empty root and "created", as before.\n'
         '          result = content_manager->CreateContentStaged(root_name, xuid, content_data);\n'
         '          disposition = kDispositionState::Create;\n'
         '          m20_staged = true;\n'
         '          break;\n'
         '        }\n'
         '        if (content_manager->ContentExists(xuid, content_data)) {\n'
         '          content_manager->DeleteContent(xuid, content_data);\n'
         '        }\n'),
        ('    uint32_t content_license = 0;\n'
         '    if (disposition == kDispositionState::Create) {\n',
         '    uint32_t content_license = 0;\n'
         '    if (m20_staged) {\n'
         '      // M20 (D-049): created above; the header file is written by the commit.\n'
         '    } else if (disposition == kDispositionState::Create) {\n'),
        ('    if (license_mask_ptr && XSUCCEEDED(result)) {\n'
         '      *license_mask_ptr = content_license;\n'
         '    }\n',
         '    if ((flags & 0xF) == 2 && XSUCCEEDED(result)) {\n'
         '      // M20: test-only end of the process between the create and the first write (R3HD_SAVE_FAULT).\n'
         '      rex::system::xam::ContentManager::M20FaultExitAfterCreate();\n'
         '    }\n'
         '    if (license_mask_ptr && XSUCCEEDED(result)) {\n'
         '      *license_mask_ptr = content_license;\n'
         '    }\n'),
    ])

    patch('src/filesystem/devices/host_path_file.cpp', [
        ('#include <rex/filesystem/devices/host_path_file.h>\n',
         '#include <rex/filesystem/devices/host_path_file.h>\n#include <rex/m20_save_commit.h>\n'),
        ('  if (file_handle_->Write(byte_offset, buffer.data(), buffer.size(), out_bytes_written)) {\n'
         '    return X_STATUS_SUCCESS;\n'
         '  } else {\n'
         '    return X_STATUS_END_OF_FILE;\n'
         '  }\n',
         '  // M20 (D-049): a failed or short host write into staged save content stops that content from\n'
         '  // replacing the live one. The guest gets the status it got before.\n'
         '  const auto& m20_path = static_cast<HostPathEntry*>(entry())->host_path();\n'
         '  if (m20save::FaultArmed() && m20save::InActiveStage(m20_path) &&\n'
         '      m20save::Fire(m20save::Fault::kWrite)) {\n'
         '    // Test-only: half of the buffer reaches the file, then the write fails.\n'
         '    file_handle_->Write(byte_offset, buffer.data(), buffer.size() / 2, out_bytes_written);\n'
         '    m20save::NoteWriteFailure(m20_path);\n'
         '    return X_STATUS_END_OF_FILE;\n'
         '  }\n'
         '  if (file_handle_->Write(byte_offset, buffer.data(), buffer.size(), out_bytes_written)) {\n'
         '    if (*out_bytes_written != buffer.size()) {\n'
         '      m20save::NoteWriteFailure(m20_path);\n'
         '    }\n'
         '    return X_STATUS_SUCCESS;\n'
         '  } else {\n'
         '    m20save::NoteWriteFailure(m20_path);\n'
         '    return X_STATUS_END_OF_FILE;\n'
         '  }\n'),
        ('  if (file_handle_->SetLength(length)) {\n'
         '    return X_STATUS_SUCCESS;\n'
         '  } else {\n'
         '    return X_STATUS_END_OF_FILE;\n'
         '  }\n',
         '  if (file_handle_->SetLength(length)) {\n'
         '    return X_STATUS_SUCCESS;\n'
         '  } else {\n'
         '    // M20 (D-049): as for a failed write.\n'
         '    m20save::NoteWriteFailure(static_cast<HostPathEntry*>(entry())->host_path());\n'
         '    return X_STATUS_END_OF_FILE;\n'
         '  }\n'),
    ])
