#pragma once

#if defined(_WIN32)
#if defined(PGEH_BRIDGE_EXPORTS)
#define PGEH_BRIDGE_API __declspec(dllexport)
#else
#define PGEH_BRIDGE_API __declspec(dllimport)
#endif
#else
#define PGEH_BRIDGE_API __attribute__((visibility("default")))
#endif

extern "C" PGEH_BRIDGE_API void pgeh_bridge(void (*callback)(void*), void* context);
extern "C" PGEH_BRIDGE_API unsigned pgeh_bridge_unwind_count() noexcept;
