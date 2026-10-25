#!/usr/bin/env python3
"""Join the target's real import table with ReXGlue and Xenia implementation status.
Usage: import_surface.py <pe_analysis.json> <import_xrefs.json> <rexglue_dir> <xenia_git_dir> <out.csv>"""
import sys, json, re, os, subprocess, csv, collections
pe, xr, rex, xen, outp = sys.argv[1:6]
R = json.load(open(pe)); X = {(e["lib"], e["name"]): e["direct_refs"] for e in json.load(open(xr))["imports"]}
rex_impl, rex_stub = set(), set()
for root, _, files in os.walk(os.path.join(rex, "src")):
    for f in files:
        if not f.endswith((".cpp", ".h", ".inc")): continue
        s = open(os.path.join(root, f), encoding="utf-8", errors="replace").read()
        rex_impl |= set(re.findall(r"\b(?:REX|XBOXKRNL|XAM)_EXPORT\(\s*__imp__(\w+)\s*,", s))
        rex_stub |= set(re.findall(r"\b(?:REX|XBOXKRNL|XAM)_EXPORT_STUB(?:_RETURN)?\(\s*__imp__(\w+)", s))
        rex_impl |= set(re.findall(r"REX_HOOK_RAW[(]\s*__imp__(\w+)\s*[)]", s))
xs = subprocess.run(["git", "-C", xen, "grep", "-h", "-A3", "-E", r"DECLARE_\w*EXPORT[0-9]?\(", "HEAD", "--", "src/xenia/kernel"],
                    capture_output=True, text=True).stdout
xen_status = {}
for m in re.finditer(r"DECLARE_\w*EXPORT[0-9]?\(\s*(\w+)\s*,[^;]*?,\s*k(\w+)\s*\)", xs):
    xen_status[m.group(1)] = m.group(2)
def subsystem(lib, n):
    r = [("networking", r"^NetDll_|^XNetLogon"), ("graphics/display", r"^Vd"), ("audio", r"^XAudio|^XMA"),
         ("threading/sync", r"^Ke(Wait|Set|Reset|Init|Insert|Enter|Leave|Acquire|Release|Delay|Query(Base)|Tls|Lock|Unlock|GetCurrentProcess|SetCurrentProcess|SetAff|SetBase|SetDisable)|^Kf|^KiApc|^Nt(Create(Event|Mutant|Semaphore)|Set(Event)|Clear|Pulse|Release|Wait|Signal|Yield|Suspend|Resume|QueueApc|DuplicateObject)|^Rtl.*CriticalSection|^Ex(Create|Terminate)Thread|^Ex\w+ObjectType|^ObLookupThread"),
         ("memory/VM", r"^Mm|^Nt(Allocate|Free|Protect|Query)VirtualMemory|^ExAllocate|^ExFreePool|^XamAlloc|^XamFree"),
         ("filesystem/io", r"^Nt(Create|Open|Read|Write|Flush|Query(Dir|Full|Information|Volume)|SetInformation|DeviceIoControl)|^Io|^Fsc|^Stfs|^ObCreateSymbolicLink|^ObDeleteSymbolicLink"),
         ("content/storage/save", r"^XamContent"), ("profile/user", r"^XamUser|^XamReadTile|^XamWriteGamerTile|^XamParseGamerTile|^XamReadString"),
         ("input", r"^XamInput"), ("system UI", r"^XamShow"), ("achievements/XLive msg", r"^XMsg|^XamSession|^XamCreateEnumeratorHandle|^XamEnumerate|^XamGetPrivateEnum|^XNotify|^XamNotify|^XamTask"),
         ("timing", r"^KeQuery(Performance|SystemTime)|^KeTimeStampBundle|^RtlTime"),
         ("module/loader", r"^Xex|^XamLoader|^XamGetExecutionId|^ExLoadedCommandLine|^RtlImageXexHeaderField"),
         ("crypto/keys", r"^XeCrypt|^XeKeys"), ("exceptions/debug", r"^Rtl(Unwind|RaiseException|CaptureContext)|^__C_specific|^Dbg|^KeBugCheck|^Ke(Debug|Cert)MonitorData|^KeEnableFpu"),
         ("object manager", r"^Ob|^NtClose"), ("config/system info", r"^ExGetXConfig|^XGet|^XboxHardware|^XboxKrnlVersion|^XamGetSystemVersion|^HalReturn|^ExRegisterTitleTerminate"),
         ("CRT/string", r"^Rtl|sprintf|snprintf")]
    for name, rx in r:
        if re.search(rx, n): return name
    return "miscellaneous"
rows, summ = [], collections.Counter()
for e in sorted(R["imports"], key=lambda e: (e["lib"], e["name"] or "")):
    n = e["name"]; isvar = e["thunk"] is None
    rs = "variable(patched by loader)" if isvar else "implemented" if n in rex_impl else "stub" if n in rex_stub else "ABSENT"
    xs_ = xen_status.get(n, "variable" if isvar else "ABSENT")
    sub = subsystem(e["lib"], n)
    rows.append([e["lib"], f"0x{e['ordinal']:03X}", n, "variable" if isvar else "function", X.get((e["lib"], n), ""), sub, rs, xs_])
    summ[(sub, rs)] += 1
with open(outp, "w", newline="") as f:
    w = csv.writer(f); w.writerow(["library", "ordinal", "name", "kind", "direct_call_refs", "subsystem", "rexglue_c94f5eb", "xenia_95a5c3e"]); w.writerows(rows)
subs = sorted({k[0] for k in summ})
print(f"{'subsystem':26} total impl stub absent var")
for s in subs:
    g = lambda k: sum(v for (a, b), v in summ.items() if a == s and b.startswith(k))
    print(f"{s:26} {sum(v for (a,b),v in summ.items() if a==s):5} {g('impl'):4} {g('stub'):4} {g('ABSENT'):6} {g('variable'):3}")
tot = collections.Counter(r[6] for r in rows); print(dict(tot)); print("xenia:", dict(collections.Counter(r[7] for r in rows)))
print("REX STUB (referenced):", " ".join(f"{r[2]}" for r in rows if r[6] == "stub" and not r[2].startswith("NetDll_")))
print("REX ABSENT:", " ".join(r[2] for r in rows if r[6] == "ABSENT"))
print("NetDll stubs:", sum(1 for r in rows if r[6] == "stub" and r[2].startswith("NetDll_")), "NetDll impl:", sum(1 for r in rows if r[6] == "implemented" and r[2].startswith("NetDll_")))
