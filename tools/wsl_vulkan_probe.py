"""Read-only Linux Vulkan inventory using the installed loader; no window/device creation.

Run in WSL with python3 tools/wsl_vulkan_probe.py. No third-party Python modules.
"""
import ctypes as c
import ctypes.util
import glob
import json
import os
import pathlib
import platform
import shutil
import subprocess


def version(value):
    return f"{value >> 22}.{(value >> 12) & 1023}.{value & 4095}"


class Application(c.Structure):
    _fields_ = [("sType", c.c_uint32), ("pNext", c.c_void_p),
                ("name", c.c_char_p), ("appVersion", c.c_uint32),
                ("engine", c.c_char_p), ("engineVersion", c.c_uint32),
                ("apiVersion", c.c_uint32)]


class InstanceInfo(c.Structure):
    _fields_ = [("sType", c.c_uint32), ("pNext", c.c_void_p),
                ("flags", c.c_uint32), ("app", c.POINTER(Application)),
                ("layerCount", c.c_uint32), ("layers", c.c_void_p),
                ("extensionCount", c.c_uint32), ("extensions", c.c_void_p)]


class Extension(c.Structure):
    _fields_ = [("name", c.c_char * 256), ("specVersion", c.c_uint32)]


class QueryBlock(c.Structure):
    # Aligned pNext output storage, large enough for the queried Vulkan structures.
    _fields_ = [("sType", c.c_uint32), ("pNext", c.c_void_p), ("values", c.c_uint32 * 1024)]


def main():
    if platform.system() != "Linux":
        raise SystemExit("Run this probe inside Linux/WSL.")
    print("architecture:", platform.machine())
    print("tools:", json.dumps({n: shutil.which(n) for n in
          ("vulkaninfo", "wine", "wine64", "proton", "steam", "glxinfo")}))
    packages = subprocess.run(["dpkg-query", "-W", "-f=${binary:Package} ${Version} ${db:Status-Status}\n",
                               "*vulkan*", "*mesa*", "*wine*", "*proton*", "*vkd3d*"],
                              capture_output=True, text=True)
    print("installed packages:\n" + "\n".join(
        line for line in packages.stdout.splitlines() if line.endswith(" installed")))
    for directory in ("/usr/share/vulkan/icd.d", "/etc/vulkan/icd.d",
                      os.path.expanduser("~/.config/vulkan/icd.d")):
        for path in sorted(glob.glob(directory + "/*.json")):
            print("ICD:", path, pathlib.Path(path).read_text().strip())
    for directory in ("~/.steam/steam/steamapps/common", "~/.local/share/Steam/steamapps/common",
                      "~/.local/share/Steam/compatibilitytools.d", "~/.steam/root/compatibilitytools.d",
                      "/opt", "/usr/local/bin"):
        path = pathlib.Path(directory).expanduser()
        print("installation directory:", str(path),
              sorted(p.name for p in path.iterdir())[:40] if path.is_dir() else "absent")
    print("graphics overrides:", json.dumps({k: v for k, v in os.environ.items()
          if k.startswith(("VK_", "MESA", "GALLIUM", "LIBGL"))}))
    loader = ctypes.util.find_library("vulkan")
    print("loader:", loader)
    if not loader:
        raise SystemExit("Vulkan loader absent")
    vk = c.CDLL(loader)
    api = c.c_uint32(1 << 22)
    if hasattr(vk, "vkEnumerateInstanceVersion"):
        vk.vkEnumerateInstanceVersion(c.byref(api))
    print("loader API:", version(api.value))
    if api.value < (1 << 22) | (2 << 12):
        raise SystemExit("This probe's feature queries require a Vulkan 1.2+ loader.")
    vk.vkEnumerateInstanceExtensionProperties.argtypes = [c.c_char_p, c.POINTER(c.c_uint32), c.c_void_p]
    extension_count = c.c_uint32()
    result = vk.vkEnumerateInstanceExtensionProperties(None, c.byref(extension_count), None)
    if result:
        raise SystemExit(f"instance extension count failed: {result}")
    instance_extensions = (Extension * extension_count.value)()
    result = vk.vkEnumerateInstanceExtensionProperties(None, c.byref(extension_count), instance_extensions)
    if result:
        raise SystemExit(f"instance extension enumeration failed: {result}")
    print("instance extensions:", " ".join(sorted(e.name.decode() for e in instance_extensions)))
    app = Application(sType=0, name=b"read-only-wsl-probe", apiVersion=min(api.value, (1 << 22) | (3 << 12)))
    info = InstanceInfo(sType=1, app=c.pointer(app))
    instance = c.c_void_p()
    vk.vkCreateInstance.argtypes = [c.POINTER(InstanceInfo), c.c_void_p, c.POINTER(c.c_void_p)]
    result = vk.vkCreateInstance(c.byref(info), None, c.byref(instance))
    print("vkCreateInstance:", result)
    if result:
        raise SystemExit(1)
    try:
        vk.vkEnumeratePhysicalDevices.argtypes = [c.c_void_p, c.POINTER(c.c_uint32), c.c_void_p]
        vk.vkGetPhysicalDeviceProperties.argtypes = [c.c_void_p, c.c_void_p]
        vk.vkGetPhysicalDeviceFeatures.argtypes = [c.c_void_p, c.c_void_p]
        vk.vkEnumerateDeviceExtensionProperties.argtypes = [c.c_void_p, c.c_char_p, c.POINTER(c.c_uint32), c.c_void_p]
        count = c.c_uint32()
        result = vk.vkEnumeratePhysicalDevices(instance, c.byref(count), None)
        print("vkEnumeratePhysicalDevices:", result, "count:", count.value)
        if result:
            raise SystemExit(1)
        devices = (c.c_void_p * count.value)()
        result = vk.vkEnumeratePhysicalDevices(instance, c.byref(count), devices)
        if result:
            raise SystemExit(f"device enumeration failed: {result}")
        for device in devices:
            # Oversized, aligned storage for VkPhysicalDeviceProperties; only fixed header read.
            props = (c.c_uint64 * 512)()
            vk.vkGetPhysicalDeviceProperties(device, props)
            header = c.cast(props, c.POINTER(c.c_uint32))
            name = c.string_at(c.addressof(props) + 20, 256).split(b"\0", 1)[0].decode()
            print("device:", json.dumps(dict(name=name, api=version(header[0]), driver_raw=header[1],
                  vendor=hex(header[2]), device=hex(header[3]), type=header[4])))
            features = (c.c_uint32 * 55)()
            vk.vkGetPhysicalDeviceFeatures(device, features)
            print("core features:", json.dumps({name: bool(features[index]) for name, index in
                  (("geometryShader", 4), ("tessellationShader", 5), ("multiDrawIndirect", 9),
                   ("shaderStorageImageReadWithoutFormat", 31), ("shaderInt64", 40))}))
            indexing = QueryBlock(sType=1000161001)
            features2 = QueryBlock(sType=1000059000, pNext=c.addressof(indexing))
            vk.vkGetPhysicalDeviceFeatures2.argtypes = [c.c_void_p, c.c_void_p]
            vk.vkGetPhysicalDeviceFeatures2(device, c.byref(features2))
            print("descriptor indexing features (20 VkBool32 in spec order):",
                  list(indexing.values[:20]))
            vulkan12 = QueryBlock(sType=51)
            draw_parameters = QueryBlock(sType=1000063000, pNext=c.addressof(vulkan12))
            features2.pNext = c.addressof(draw_parameters)
            vk.vkGetPhysicalDeviceFeatures2(device, c.byref(features2))
            print("additional required features:", json.dumps(dict(
                samplerMirrorClampToEdge=bool(vulkan12.values[0]),
                shaderDrawParameters=bool(draw_parameters.values[0]))))
            indexing_props = QueryBlock(sType=1000161002)
            properties2 = QueryBlock(sType=1000059001, pNext=c.addressof(indexing_props))
            vk.vkGetPhysicalDeviceProperties2.argtypes = [c.c_void_p, c.c_void_p]
            vk.vkGetPhysicalDeviceProperties2(device, c.byref(properties2))
            print("descriptor indexing limits:", json.dumps({name: indexing_props.values[index]
                  for name, index in (("allPools", 0), ("perStageSamplers", 8),
                  ("perStageStorageBuffers", 10), ("perStageSampledImages", 11),
                  ("perStageStorageImages", 12), ("setSamplers", 15),
                  ("setStorageBuffers", 18), ("setSampledImages", 20), ("setStorageImages", 21))}))
            n = c.c_uint32()
            result = vk.vkEnumerateDeviceExtensionProperties(device, None, c.byref(n), None)
            if result:
                raise SystemExit(f"extension count failed: {result}")
            extensions = (Extension * n.value)()
            result = vk.vkEnumerateDeviceExtensionProperties(device, None, c.byref(n), extensions)
            if result:
                raise SystemExit(f"extension enumeration failed: {result}")
            print("device extensions:", " ".join(sorted(e.name.decode() for e in extensions)))
    finally:
        vk.vkDestroyInstance.argtypes = [c.c_void_p, c.c_void_p]
        vk.vkDestroyInstance(instance, None)


if __name__ == "__main__":
    main()
