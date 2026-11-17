// LM-1 Linux compat header. Deliberately empty.
//
// tools/m2_host/m2_trace.h and m2_trace.cpp include <windows.h> on a line that cannot be wrapped in a
// preprocessor guard without moving every following Windows line (the Windows build must stay byte-identical).
// Every use of Windows declarations in those files is guarded with `#if defined(_WIN32)`, so on Linux the include
// only needs to resolve. Linux builds of the game host and of generated code add tools/linux/compat to their
// include path; Windows builds never do.
#pragma once
#if defined(_WIN32)
#error "tools/linux/compat must never be on a Windows include path"
#endif
