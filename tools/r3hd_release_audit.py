#!/usr/bin/env python3
"""Fail-closed release-package audit (gate G-PKG, D-059).

The project ships source and tooling only: never game data, game executables,
translated game code, SDK binaries, keys, saves or captures.  This tool checks
a candidate package (a directory, a .zip, or the files git tracks) against a
positive allowlist (config/release/allowlist.json) and a set of content rules.

    r3hd_release_audit.py scan DIR|ZIP [--allowlist FILE] [--json OUT]
                          [--game-manifest TSV] [--allow-finding CODE:PATH]
    r3hd_release_audit.py git [--rev REV] [same options]
    r3hd_release_audit.py selftest

Exit codes: 0 PASS, 2 FAIL (rejected files), 1 selftest failure, 3 usage or
configuration error.  The audit is technical only and is NOT a legal
clearance.  Matched key bytes are never printed: findings carry line numbers.
Standard library only; read-only (a zip is read in memory, never extracted).
"""
import argparse
import hashlib
import io
import json
import os
import re
import stat
import subprocess
import sys
import tempfile
import zipfile

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_ALLOWLIST = os.path.join(REPO, "config", "release", "allowlist.json")
DEFAULT_MANIFEST = os.path.join(REPO, "reports", "milestone1", "data", "content_manifest.tsv")
DEFAULT_RELEASES = os.path.join(REPO, "config", "intake", "known_releases.json")

NOT_LEGAL = "technical audit only; this is NOT a legal clearance"

TEXT_KINDS = {"python", "powershell", "batch", "cpp_source", "cpp_header", "json", "toml",
              "markdown", "text", "tsv", "csv", "gitignore", "shell"}

# --- content magic (checked on the first bytes, whatever the name says) ---
# (prefix, type); first match wins.
MAGIC = [
    (b"XEX2", "XEX2"), (b"XEX1", "XEX2"),
    (b"LIVE", "STFS"), (b"PIRS", "STFS"), (b"CON ", "STFS"),
    (b"\x7fELF", "ELF"),
    (b"PK\x03\x04", "ZIP"), (b"PK\x05\x06", "ZIP"), (b"PK\x07\x08", "ZIP"),
    (b"7z\xbc\xaf\x27\x1c", "7Z"), (b"Rar!\x1a\x07", "RAR"), (b"\x1f\x8b", "GZIP"),
    (b"\xfd7zXZ\x00", "XZ"), (b"MSCF", "CAB"), (b"BZh", "BZIP2"),
    (b"\x89PNG\r\n\x1a\n", "PNG"), (b"\xff\xd8\xff", "JPEG"),
    (b"DDS ", "DDS"), (b"GIF87a", "GIF"), (b"GIF89a", "GIF"),
    (b"KB2", "BINK"),
    (b"OggS", "OGG"), (b"fLaC", "FLAC"), (b"ID3", "MP3"), (b"\x1a\x45\xdf\xa3", "MATROSKA"),
    (b"Microsoft C/C++ MSF 7.00", "PDB"), (b"Microsoft C/C++ program database", "PDB"),
]
MAGIC_BINK = re.compile(rb"BIK[bfghik]")


def magic_type(head):
    """Return the binary type of the leading bytes, or None."""
    for prefix, kind in MAGIC:
        if head.startswith(prefix):
            return kind
    if head.startswith(b"RIFF"):
        return "WAV" if head[8:12] == b"WAVE" else "RIFF"
    if MAGIC_BINK.match(head):
        return "BINK"
    if head.startswith(b"MZ"):
        return "PE"
    if head.startswith(b"BM") and (len(head) < 14 or head[6:10] == b"\0\0\0\0"):
        return "BMP"
    if head[4:8] == b"ftyp":
        return "MP4"
    return None


# --- text rules ---
# Markers of ReXGlue-translated game code.  Measured over `git ls-files` the
# maximum hits in one file is GEN_MEASURED_MAX (see the comment at GEN_THRESHOLD).
GEN_MARKERS = re.compile(r"PPC_FUNC_IMPL\(|PPC_FUNC\(|REX_FUNC_PROLOGUE\(\)|__imp__sub_[0-9A-F]{8}"
                         r"|\bsub_8[0-9A-F]{7}\(ctx, base\)")
GEN_NAMES = re.compile(r"^(r3hd_recomp\.\d+\.cpp|r3hd_funcs[^/]*\.h|r3hd_init\.cpp)$")
# Threshold: marker hits in one text file.  See _gen_constants_note below.
GEN_THRESHOLD = 20

PEM_KEY = re.compile(r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----")
KEY_ARRAY = re.compile(r"(\w*key\w*)\s*(?:\[[^\]]*\]\s*)*=\s*\{([^{}]*)\}", re.IGNORECASE)
HEX_BYTE = re.compile(r"^0[xX][0-9A-Fa-f]{1,2}$")
HEX_LITERAL = re.compile(r"(?<![0-9A-Fa-f])(?:[0-9A-Fa-f]{64}|[0-9A-Fa-f]{32})(?![0-9A-Fa-f])")
KEY_WORDS = re.compile(r"key|secret|token", re.IGNORECASE)
HASH_WORDS = re.compile(r"\bsha(?:-?\d+)?\b|sha\d+|hash|digest|content_?id|checksum|md5|crc|fingerprint|signature|uuid|guid|"
                        r"media_?id|title_?id|nonce|salt", re.IGNORECASE)

DEV_PATHS = [
    re.compile(r"[A-Za-z]:[\\/]+Users[\\/]+([^\\/\s\"']+)", re.IGNORECASE),
    re.compile(r"(?<![A-Za-z0-9_.])/[A-Za-z]/Users/([^/\s\"']+)"),
    re.compile(r"(?<![A-Za-z0-9_.])/mnt/[A-Za-z]/Users/([^/\s\"']+)"),
    re.compile(r"(?<![A-Za-z0-9_.])/home/([A-Za-z0-9_.-]+)/"),
    re.compile(r"(?<![A-Za-z0-9_.:\\/])/Users/([A-Za-z0-9_.-]+)/"),
    # M28: CMake / Ninja object paths spell the drive as "C_" followed by the Users folder and the account name.
    re.compile(r"(?<![A-Za-z0-9])[A-Za-z]_[\\/]+Users[\\/]+([^\\/\s\"']+)", re.IGNORECASE),
]
PLACEHOLDER_START = "<%${*"  # C:\Users\<name>, %USERNAME%, $USER, {user}, * are placeholders

CAPTURE_EXT = {".bmp", ".png", ".jpg", ".jpeg", ".dds", ".wav", ".bik", ".xma", ".xmv", ".mp4",
               ".avi", ".webm"}


def scan_text(text):
    """Text rules.  Returns {code: [line numbers]} (never the matched bytes)."""
    found = {}

    def add(code, line):
        found.setdefault(code, [])
        if line not in found[code]:
            found[code].append(line)

    gen_lines = []
    lines = text.split("\n")
    for n, line in enumerate(lines, 1):
        if PEM_KEY.search(line):
            add("KEY_MATERIAL", n)
        if KEY_WORDS.search(line) and not HASH_WORDS.search(line) and HEX_LITERAL.search(line):
            add("KEY_MATERIAL", n)
        for rx in DEV_PATHS:
            for m in rx.finditer(line):
                if m.group(1)[:1] in PLACEHOLDER_START:
                    continue
                add("DEVELOPER_PATH", n)
        hits = len(GEN_MARKERS.findall(line))
        if hits:
            gen_lines.extend([n] * hits)
    for m in KEY_ARRAY.finditer(text):
        items = [i.strip() for i in m.group(2).split(",") if i.strip()]
        if len(items) in (16, 32) and all(HEX_BYTE.match(i) for i in items):
            add("KEY_MATERIAL", text.count("\n", 0, m.start()) + 1)
    if len(gen_lines) >= GEN_THRESHOLD:
        found["GENERATED_CODE"] = sorted(set(gen_lines))[:20]
    return found, len(gen_lines)


# --- globs ---
def glob_regex(pattern):
    out, i = [], 0
    while i < len(pattern):
        if pattern.startswith("**/", i):
            out.append("(?:.*/)?")
            i += 3
        elif pattern.startswith("**", i):
            out.append(".*")
            i += 2
        elif pattern[i] == "*":
            out.append("[^/]*")
            i += 1
        elif pattern[i] == "?":
            out.append("[^/]")
            i += 1
        else:
            out.append(re.escape(pattern[i]))
            i += 1
    return re.compile("^" + "".join(out) + "$")


class ConfigError(Exception):
    pass


class Allowlist:
    def __init__(self, path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, ValueError) as e:
            raise ConfigError("cannot read allowlist %s: %s" % (path, e))
        if data.get("schema") != 1:
            raise ConfigError("allowlist schema must be 1")
        self.path = path
        self.entries = []
        for e in data.get("allow", []):
            if e.get("kind") not in TEXT_KINDS:
                raise ConfigError("allowlist entry %r: kind must be one of %s" % (e, sorted(TEXT_KINDS)))
            self.entries.append((e["glob"], e["kind"], glob_regex(e["glob"])))
        if not self.entries:
            raise ConfigError("allowlist has no entries")
        self.deny_prefixes = [p.lower().rstrip("/") + "/" for p in data.get("deny_paths", [])]
        self.deny_segments = [s.lower() for s in data.get("deny_segments", [])]
        self.max_bytes = int(data.get("max_text_file_bytes", 0))
        if self.max_bytes <= 0:
            raise ConfigError("allowlist max_text_file_bytes missing")

    def kind_of(self, rel):
        for _glob, kind, rx in self.entries:
            if rx.match(rel):
                return kind
        return None

    def denied(self, rel):
        low = rel.lower()
        if any(low.startswith(p) for p in self.deny_prefixes):
            return True
        return any(seg in self.deny_segments for seg in low.split("/"))


class GameHashes:
    """SHA-256 values of the user's game files (manifest TSV) and executable."""

    def __init__(self, manifest_paths, releases_path=None):
        self.hashes = {}      # sha256 -> label
        self.sizes = set()    # sizes with a known hash
        self.any_size = False  # a hash whose size is unknown: hash every file >= BIG
        for path in manifest_paths:
            try:
                with open(path, "r", encoding="utf-8", errors="replace") as f:
                    for line in f:
                        cols = line.rstrip("\r\n").split("\t")
                        h = next((c.lower() for c in cols if re.fullmatch(r"[0-9A-Fa-f]{64}", c)), None)
                        sz = next((int(c) for c in cols if c.isdigit()), None)
                        if h is None:
                            continue
                        self.hashes[h] = "manifest:" + cols[0]
                        if sz is not None:
                            self.sizes.add(sz)
                        else:
                            self.any_size = True
            except OSError as e:
                raise ConfigError("cannot read game manifest %s: %s" % (path, e))
        if releases_path and os.path.exists(releases_path):
            try:
                with open(releases_path, "r", encoding="utf-8") as f:
                    rel = json.load(f)
                for r in rel.get("releases", []):
                    ex, pk = r.get("executable", {}), r.get("package", {})
                    for obj, size_key, key, label in (
                            (ex, "size", "sha256", "executable"),
                            (ex, None, "decrypted_image_sha256", "decrypted_image"),
                            (pk, "observed_package_size", "observed_package_sha256", "package")):
                        h = obj.get(key)
                        if isinstance(h, str) and re.fullmatch(r"[0-9A-Fa-f]{64}", h):
                            self.hashes[h.lower()] = "release:" + label
                            if size_key and isinstance(obj.get(size_key), int):
                                self.sizes.add(obj[size_key])
                            else:
                                self.any_size = True
            except (OSError, ValueError) as e:
                raise ConfigError("cannot read %s: %s" % (releases_path, e))

    BIG = 1 << 20

    def wants(self, size):
        return size in self.sizes or (self.any_size and size >= self.BIG)


class Entry:
    """One candidate file: relative path, size, opener returning a binary stream."""

    def __init__(self, rel, size, opener, unsafe=None, error=None):
        self.rel, self.size, self.opener, self.unsafe, self.error = rel, size, opener, unsafe, error


def norm(name):
    n = name.replace("\\", "/")
    while n.startswith("./"):
        n = n[2:]
    return n


# --- sources ---
def entries_dir(root):
    root = os.path.abspath(root)
    out = []

    def walk(d, prefix):
        try:
            names = sorted(os.listdir(d))
        except OSError as e:
            out.append(Entry(prefix.rstrip("/") or ".", 0, None, error=str(e)))
            return
        for name in names:
            full = os.path.join(d, name)
            rel = prefix + name
            if os.path.islink(full):
                out.append(Entry(rel, 0, None, unsafe="symlink"))
            elif os.path.isdir(full):
                walk(full, rel + "/")
            else:
                try:
                    size = os.path.getsize(full)
                except OSError as e:
                    out.append(Entry(rel, 0, None, error=str(e)))
                    continue
                out.append(Entry(rel, size, (lambda p=full: open(p, "rb"))))

    walk(root, "")
    return out


def entries_zip(path):
    try:
        zf = zipfile.ZipFile(path, "r")
    except (OSError, zipfile.BadZipFile) as e:
        raise ConfigError("cannot open zip %s: %s" % (path, e))
    out, seen = [], set()
    for info in zf.infolist():
        name = info.filename
        if name.endswith("/"):
            continue
        rel = norm(name)
        unsafe = None
        parts = rel.split("/")
        mode = (info.external_attr >> 16) & 0xFFFF
        if rel.startswith("/") or re.match(r"^[A-Za-z]:", rel):
            unsafe = "absolute path"
        elif ".." in parts:
            unsafe = "parent traversal"
        elif "\0" in name:
            unsafe = "NUL in name"
        elif mode and stat.S_ISLNK(mode):
            unsafe = "symlink"
        elif info.flag_bits & 0x1:
            unsafe = "encrypted member"
        elif rel in seen:
            unsafe = "duplicate member"
        seen.add(rel)
        out.append(Entry(name if unsafe else rel, info.file_size,
                         (lambda i=info: zf.open(i, "r")), unsafe=unsafe))
    return out


def git_run(args):
    return subprocess.run(["git"] + args, cwd=REPO, stdout=subprocess.PIPE, stderr=subprocess.PIPE)


def entries_git(rev):
    out = []
    if rev:
        r = git_run(["ls-tree", "-r", "-l", "-z", rev])
        if r.returncode:
            raise ConfigError("git ls-tree failed: " + r.stderr.decode("utf-8", "replace").strip())
        for rec in r.stdout.split(b"\0"):
            if not rec:
                continue
            meta, _, path = rec.partition(b"\t")
            mode, typ, _sha, size = meta.decode().split()
            rel = path.decode("utf-8", "replace")
            if mode == "120000":
                out.append(Entry(rel, 0, None, unsafe="symlink"))
            elif typ != "blob":
                out.append(Entry(rel, 0, None, unsafe="submodule"))
            else:
                def opener(p=rel):
                    g = git_run(["show", "%s:%s" % (rev, p)])
                    if g.returncode:
                        raise OSError(g.stderr.decode("utf-8", "replace").strip())
                    return io.BytesIO(g.stdout)
                out.append(Entry(rel, int(size), opener))
    else:
        r = git_run(["ls-files", "-s", "-z"])
        if r.returncode:
            raise ConfigError("git ls-files failed: " + r.stderr.decode("utf-8", "replace").strip())
        for rec in r.stdout.split(b"\0"):
            if not rec:
                continue
            meta, _, path = rec.partition(b"\t")
            mode = meta.decode().split()[0]
            rel = path.decode("utf-8", "replace")
            full = os.path.join(REPO, rel)
            if mode == "120000" or os.path.islink(full):
                out.append(Entry(rel, 0, None, unsafe="symlink"))
            elif mode == "160000":
                out.append(Entry(rel, 0, None, unsafe="submodule"))
            elif not os.path.isfile(full):
                out.append(Entry(rel, 0, None, error="tracked file missing from working tree"))
            else:
                out.append(Entry(rel, os.path.getsize(full), (lambda p=full: open(p, "rb"))))
    return out


# --- the audit ---
def audit_entry(e, allow, hashes):
    """Return a list of findings [{code, lines?, detail?}] for one entry."""
    f = []

    def add(code, lines=None, detail=None):
        d = {"code": code}
        if lines:
            d["lines"] = lines
        if detail:
            d["detail"] = detail
        f.append(d)

    rel = e.rel
    low = rel.lower()
    base = low.rsplit("/", 1)[-1]
    if e.unsafe:
        add("UNSAFE_MEMBER", detail=e.unsafe)
    if e.error:
        add("UNREADABLE", detail=e.error)
    if allow.denied(rel):
        add("DENIED_PATH")
    if "5841123f/00000001" in low or "/.staging/" in "/" + low or low.startswith(".staging/"):
        add("SAVE_DATA", detail="save/profile path")
    ext = os.path.splitext(base)[1]
    # A CapFrameX capture lives in a capframex directory or is a data file named for it;
    # a tool script such as tools/m16_capframex.py (a source file) is not a capture.
    capframex = any("capframex" in seg for seg in low.split("/")[:-1]) or (
        "capframex" in base and ext in (".json", ".csv", ".txt", ".zip", ""))
    if ext in CAPTURE_EXT or capframex:
        add("CAPTURE", detail="capture/media path")
    kind = None if e.unsafe else allow.kind_of(rel)
    if kind is None:
        add("NOT_ALLOWLISTED")
    if e.size > allow.max_bytes:
        add("TOO_LARGE", detail="%d bytes > %d" % (e.size, allow.max_bytes))
    if GEN_NAMES.match(base):
        add("GENERATED_CODE", detail="generated file name")
    if e.opener is None:
        return f
    try:
        with e.opener() as fh:
            head = fh.read(64)
            mt = magic_type(head)
            if mt:
                add("BINARY_MAGIC_" + mt)
            data = None
            if hashes.wants(e.size) or e.size <= allow.max_bytes:
                h = hashlib.sha256()
                buf = [] if e.size <= allow.max_bytes else None
                h.update(head)
                if buf is not None:
                    buf.append(head)
                while True:
                    chunk = fh.read(1 << 20)
                    if not chunk:
                        break
                    h.update(chunk)
                    if buf is not None:
                        buf.append(chunk)
                if buf is not None:
                    data = b"".join(buf)
                label = hashes.hashes.get(h.hexdigest())
                if label:
                    add("GAME_FILE_HASH", detail=label)
    except (OSError, zipfile.BadZipFile, RuntimeError, NotImplementedError) as ex:
        add("UNREADABLE", detail=str(ex))
        return f
    if data is not None:
        text, bad = None, False
        if b"\0" in data:
            bad = True
        else:
            try:
                text = data.decode("utf-8")
            except UnicodeDecodeError:
                bad = True
        if bad:
            if kind is not None:
                add("BINARY_CONTENT", detail="NUL byte or invalid UTF-8")
        else:
            found, _n = scan_text(text)
            for code in sorted(found):
                add(code, lines=found[code][:20])
    return f


def run_audit(entries, allow, hashes, waivers=()):
    files, counts = [], {}
    used = set()
    for e in entries:
        findings = audit_entry(e, allow, hashes)
        waived = []
        remaining = []
        for fd in findings:
            hit = next((w for w in waivers if w[0] == fd["code"] and w[2].match(e.rel)), None)
            if hit:
                waived.append(fd)
                used.add((hit[0], hit[1]))
            else:
                remaining.append(fd)
        for fd in remaining:
            counts[fd["code"]] = counts.get(fd["code"], 0) + 1
        files.append({"path": e.rel, "verdict": "FAIL" if remaining else "PASS",
                      "reasons": remaining, "waived": waived})
    rejected = sum(1 for x in files if x["verdict"] == "FAIL")
    return {"audit": "r3hd_release_audit", "notice": NOT_LEGAL,
            "verdict": "FAIL" if rejected else "PASS", "files": len(files), "rejected": rejected,
            "reason_counts": counts,
            "allowed_findings": sorted("%s:%s" % w for w in used),
            "results": files}


def fmt_reason(fd):
    s = fd["code"]
    if fd.get("lines"):
        s += "@" + ",".join(str(n) for n in fd["lines"])
    if fd.get("detail"):
        s += " (%s)" % fd["detail"]
    return s


def print_result(res, verbose, out=None):
    out = out or sys.stdout
    out.write("NOTICE: %s\n" % NOT_LEGAL)
    for r in res["results"]:
        if r["verdict"] == "FAIL":
            out.write("FAIL %s: %s\n" % (r["path"], "; ".join(fmt_reason(x) for x in r["reasons"])))
        elif verbose:
            out.write("PASS %s\n" % r["path"])
        for w in r["waived"]:
            out.write("ALLOWED_FINDING %s %s%s\n" % (w["code"], r["path"],
                                                      "@" + ",".join(str(n) for n in w["lines"]) if w.get("lines") else ""))
    if res["reason_counts"]:
        out.write("REASONS %s\n" % " ".join("%s=%d" % kv for kv in sorted(res["reason_counts"].items())))
    if res["verdict"] == "PASS":
        out.write("R3HD_RELEASE_AUDIT PASS files=%d\n" % res["files"])
    else:
        out.write("R3HD_RELEASE_AUDIT FAIL files=%d rejected=%d\n" % (res["files"], res["rejected"]))
    out.write("(%s)\n" % NOT_LEGAL)


WAIVABLE = {"DEVELOPER_PATH", "CAPTURE"}


def parse_waivers(items):
    out = []
    for it in items or []:
        code, sep, path = it.partition(":")
        if not sep or not code or not path:
            raise ConfigError("--allow-finding expects CODE:PATH, got %r" % it)
        # M28 review: a waiver is a recorded exception for one text finding on named files, never a way around
        # the allowlist or a content check that identifies game data, binaries, keys or generated code.
        if code not in WAIVABLE:
            raise ConfigError("--allow-finding: %s cannot be waived (waivable: %s)" % (code, ", ".join(sorted(WAIVABLE))))
        if any(ch in path for ch in "*?["):
            raise ConfigError("--allow-finding names one path, not a pattern: %r" % it)
        out.append((code, path, glob_regex(norm(path))))
    return out


def build_context(args):
    allow = Allowlist(args.allowlist or DEFAULT_ALLOWLIST)
    manifests = [args.game_manifest] if args.game_manifest else [DEFAULT_MANIFEST]
    return allow, GameHashes(manifests, DEFAULT_RELEASES), parse_waivers(args.allow_finding)


def cmd_scan(args):
    allow, hashes, waivers = build_context(args)
    target = args.target
    if os.path.isdir(target):
        entries = entries_dir(target)
    elif os.path.isfile(target) and zipfile.is_zipfile(target):
        entries = entries_zip(target)
    else:
        raise ConfigError("scan target must be a directory or a .zip: %s" % target)
    return finish(run_audit(entries, allow, hashes, waivers), args)


def cmd_git(args):
    allow, hashes, waivers = build_context(args)
    return finish(run_audit(entries_git(args.rev), allow, hashes, waivers), args)


# --- M29 (D-066): the private installer payload (a prebuilt application, never game data) ---
DEFAULT_PAYLOAD_ALLOWLIST = os.path.join(REPO, "config", "release", "payload_allowlist.json")
DEFAULT_PAYLOAD_DEF = os.path.join(REPO, "config", "release", "payload.json")
PRIVATE_NOTICE = ("PRIVATE payload: translated game code and a runtime with the public XEX keys compiled in; "
                  "NOT publishable (D-065, D-066)")
# M30 (D-067): launcher_native = the Settings launcher, built from tools/launcher only (no SDK or game code): it is
# checked like a native binary but does not by itself make a payload private.
BINARY_ROLES = {"native": "PE", "launcher_native": "PE", "python_runtime": "PE", "python_stdlib": "ZIP"}


def load_payload_rules(allow_path, def_path):
    """Text allowlist, exact binary paths with their roles, and pinned hashes of the bundled Python runtime."""
    allow = Allowlist(allow_path)
    try:
        with open(allow_path, "r", encoding="utf-8") as f:
            binaries = json.load(f).get("binaries", {})
        with open(def_path, "r", encoding="utf-8") as f:
            py = json.load(f)["python"]
    except (OSError, ValueError, KeyError) as e:
        raise ConfigError("cannot read payload rules: %s" % e)
    if not binaries or any(r not in BINARY_ROLES for r in binaries.values()):
        raise ConfigError("payload allowlist: binaries must map exact paths to %s" % sorted(BINARY_ROLES))
    pins = {"app/python/" + n: h.lower() for n, h in py["files"].items()}
    pins["app/python/python311.zip"] = py["stdlib_zip_sha256"].lower()
    return allow, binaries, pins


def binary_dev_paths(data):
    """Count absolute user-profile paths in a binary (ASCII and UTF-16LE strings); never returns the names."""
    n = 0
    for text in (data.decode("latin-1"), data.decode("utf-16-le", "ignore")):
        for rx in DEV_PATHS:
            n += sum(1 for m in rx.finditer(text) if m.group(1)[:1] not in PLACEHOLDER_START)
    return n


def audit_payload(root, allow, binaries, pins, hashes):
    root = os.path.abspath(root)
    files, counts, listed = [], {}, {}
    native = 0
    mf = os.path.join(root, "payload.json")
    manifest_problem = None
    try:
        with open(mf, "r", encoding="utf-8") as f:
            pdata = json.load(f)
        listed = pdata["files"]
        if pdata.get("publishable") is not False:
            manifest_problem = "publishable must be false"
    except (OSError, ValueError, KeyError) as e:
        manifest_problem = "payload.json unreadable: %s" % e
    seen = set()
    for e in entries_dir(root):
        found = []
        rel = e.rel
        seen.add(rel)
        role = binaries.get(rel)
        if rel == "payload.json":
            found = audit_entry(e, allow, hashes)
            if manifest_problem:
                found.append({"code": "PAYLOAD_MANIFEST", "detail": manifest_problem})
        elif role is None:
            found = audit_entry(e, allow, hashes)
        else:
            try:
                with e.opener() as fh:
                    data = fh.read()
            except (OSError, TypeError) as ex:
                found.append({"code": "UNREADABLE", "detail": str(ex)})
                data = b""
            kind = magic_type(data[:64])
            if kind != BINARY_ROLES[role]:
                found.append({"code": "BINARY_KIND", "detail": "%s where %s expected" % (kind, BINARY_ROLES[role])})
            digest = hashlib.sha256(data).hexdigest()
            if rel in pins and digest != pins[rel]:
                found.append({"code": "PIN_MISMATCH", "detail": "not the pinned Python runtime file"})
            if digest in hashes.hashes:
                found.append({"code": "GAME_FILE_HASH", "detail": hashes.hashes[digest]})
            if role in ("native", "launcher_native"):
                native += role == "native"
                n = binary_dev_paths(data)
                if n:
                    found.append({"code": "DEVELOPER_PATH", "detail": "%d absolute user-profile path(s) in the binary" % n})
            if role == "python_stdlib" and kind == "ZIP":
                try:
                    with zipfile.ZipFile(io.BytesIO(data)) as zf:
                        bad = [i.filename for i in zf.infolist() if not i.filename.endswith(".py")
                               or i.filename.startswith(("/", "\\")) or ".." in i.filename.split("/")]
                    if bad:
                        found.append({"code": "ZIP_MEMBER", "detail": "%d member(s) that are not plain .py files" % len(bad)})
                except zipfile.BadZipFile as ex:
                    found.append({"code": "UNREADABLE", "detail": str(ex)})
        if rel != "payload.json" and e.opener is not None:
            info = listed.get(rel)
            if info is None:
                found.append({"code": "UNLISTED_FILE"})
            elif e.size != info.get("size"):
                found.append({"code": "MANIFEST_MISMATCH", "detail": "size"})
            else:
                with e.opener() as fh:
                    h = hashlib.sha256()
                    for chunk in iter(lambda: fh.read(1 << 20), b""):
                        h.update(chunk)
                if h.hexdigest() != info.get("sha256"):
                    found.append({"code": "MANIFEST_MISMATCH", "detail": "sha256"})
        for fd in found:
            counts[fd["code"]] = counts.get(fd["code"], 0) + 1
        files.append({"path": rel, "verdict": "FAIL" if found else "PASS", "reasons": found, "waived": []})
    for rel in sorted(set(listed) - seen):
        counts["MISSING_FILE"] = counts.get("MISSING_FILE", 0) + 1
        files.append({"path": rel, "verdict": "FAIL", "reasons": [{"code": "MISSING_FILE"}], "waived": []})
    if "payload.json" not in seen:
        counts["PAYLOAD_MANIFEST"] = counts.get("PAYLOAD_MANIFEST", 0) + 1
        files.append({"path": "payload.json", "verdict": "FAIL", "reasons": [{"code": "PAYLOAD_MANIFEST"}], "waived": []})
    rejected = sum(1 for x in files if x["verdict"] == "FAIL")
    return {"audit": "r3hd_release_audit payload", "notice": NOT_LEGAL, "private": native > 0,
            "classification": PRIVATE_NOTICE if native else "no native binary",
            "verdict": "FAIL" if rejected else "PASS", "files": len(files), "rejected": rejected,
            "reason_counts": counts, "allowed_findings": [], "results": files}


def cmd_payload(args):
    allow, binaries, pins = load_payload_rules(args.allowlist or DEFAULT_PAYLOAD_ALLOWLIST, DEFAULT_PAYLOAD_DEF)
    manifests = [args.game_manifest] if args.game_manifest else [DEFAULT_MANIFEST]
    if not os.path.isdir(args.target):
        raise ConfigError("payload target must be a directory: %s" % args.target)
    res = audit_payload(args.target, allow, binaries, pins, GameHashes(manifests, DEFAULT_RELEASES))
    if res["private"]:
        print("CLASSIFICATION: %s" % res["classification"])
    return finish(res, args)


def finish(res, args):
    print_result(res, args.verbose)
    if args.json:
        with open(args.json, "w", encoding="utf-8", newline="\n") as f:
            json.dump(res, f, indent=1)
            f.write("\n")
    return 0 if res["verdict"] == "PASS" else 2


# --- selftest ---
def selftest():
    checks = []

    def check(name, ok):
        checks.append((name, bool(ok)))
        if not ok:
            print("  FAILED: " + name)

    allow = Allowlist(DEFAULT_ALLOWLIST)
    # Fixture strings that would trip the rules are assembled from parts so that
    # this file itself stays clean under its own audit.
    users = "Us" + "ers"
    pem = "-----BEGIN RSA PRIV" + "ATE KEY-----"
    home = "/ho" + "me/"
    with tempfile.TemporaryDirectory(prefix="r3hd_audit_") as tmp:
        manifest = os.path.join(tmp, "manifest.tsv")
        planted = b"synthetic planted game file payload " * 4
        with open(manifest, "wb") as f:
            f.write(b"synthetic.dat\t%d\t%s\n" % (len(planted), hashlib.sha256(planted).hexdigest().encode()))
        hashes = GameHashes([manifest], None)

        def reasons(files, name, waivers=()):
            """Audit a dict {relpath: bytes}; return {path: set(codes)} and the result."""
            root = os.path.join(tmp, name)
            for rel, data in files.items():
                p = os.path.join(root, *rel.split("/"))
                os.makedirs(os.path.dirname(p), exist_ok=True)
                with open(p, "wb") as f:
                    f.write(data)
            res = run_audit(entries_dir(root), allow, hashes, waivers)
            return {r["path"]: {x["code"] for x in r["reasons"]} for r in res["results"]}, res

        def has(m, path, code):
            return code in m.get(path, set())

        # clean fixture
        m, res = reasons({"README.md": b"# Tool\n\nPlain text.\n",
                          "tools/x.py": b"print('hello')\n",
                          "config/a.json": b'{"sha256": "%s", "n": 1}\n' % (b"ab" * 32),
                          "notes.md": b"Install LLVM from C:\\Program Files\\LLVM\\bin or "
                                      b"C:\\Program Files (x86)\\Microsoft Visual Studio\\2022. "
                                      + ("Profile at C:\\" + users + "\\<name>\\x\n").encode(),
                          "reports/h.md": b"hash 0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef\n"
                                          b"key note: the content_id 3D8189500116FB22A848B806DDF3F90B\n"},
                         "clean")
        check("clean fixture passes", res["verdict"] == "PASS" and res["rejected"] == 0)
        check("Program Files / placeholder paths pass", not m["notes.md"])
        check("hash lines are not key material", not m["reports/h.md"])
        m, res = reasons({".claude/settings.json": b'{"env": {"CLAUDE_CODE_MAX_CONCURRENT_SUBAGENTS": "2"}}\n',
                          ".codex/config.toml": b'[agents]\nenabled = true\nmax_concurrent_threads_per_session = 2\n'},
                         "agent-config")
        check("tracked agent configuration passes text audit", res["verdict"] == "PASS" and res["rejected"] == 0)
        m, _ = reasons({".claude/settings.local.json": b'{}\n', ".codex/auth.json": b'{}\n'}, "agent-neighbors")
        check("neighboring agent configuration stays unlisted", all(v == {"NOT_ALLOWLISTED"} for v in m.values()))
        m, res = reasons({".recomp.json": b'{"game":"Rayman 3 HD","status":"released"}\n'}, "public-manifest")
        check("public project manifest passes the ordinary JSON/text audit", res["verdict"] == "PASS")
        m, _ = reasons({".recomp.local.json": b'{}\n'}, "public-manifest-neighbor")
        check("neighboring project manifests stay unlisted", m[".recomp.local.json"] == {"NOT_ALLOWLISTED"})

        # negative fixtures
        m, _ = reasons({"notes.md": b"XEX2" + b"\0" * 60}, "xex")
        check("XEX2 magic in notes.md", has(m, "notes.md", "BINARY_MAGIC_XEX2"))
        check("XEX2 NUL content in allowlisted name", has(m, "notes.md", "BINARY_CONTENT"))
        m, _ = reasons({"a.md": b"LIVE" + b"\0" * 60, "b.md": b"PIRS" + b"\0" * 60,
                        "c.md": b"CON " + b"\0" * 60}, "stfs")
        check("STFS LIVE/PIRS/CON magic", all(has(m, p, "BINARY_MAGIC_STFS") for p in ("a.md", "b.md", "c.md")))
        m, _ = reasons({"tools/tool.py": b"MZ\x90\0\x03\0\0\0" + b"\0" * 60}, "mz")
        check("MZ magic in tool.py", has(m, "tools/tool.py", "BINARY_MAGIC_PE"))
        m, _ = reasons({"config/pic.json": b"\x89PNG\r\n\x1a\n" + b"\0" * 20,
                        "config/e.json": b"\x7fELF" + b"\0" * 20,
                        "config/z.json": b"PK\x03\x04" + b"\0" * 20,
                        "config/g.json": b"\x1f\x8b\x08" + b"\0" * 20,
                        "config/w.json": b"RIFF\0\0\0\0WAVEfmt ",
                        "config/k.json": b"BIKi" + b"\0" * 20,
                        "config/d.json": b"DDS " + b"\0" * 20,
                        "config/b.json": b"BM" + b"\0" * 20,
                        "config/p.json": b"Microsoft C/C++ MSF 7.00\r\n\x1aDS\0\0\0"}, "magic")
        for p, t in (("pic", "PNG"), ("e", "ELF"), ("z", "ZIP"), ("g", "GZIP"), ("w", "WAV"),
                     ("k", "BINK"), ("d", "DDS"), ("b", "BMP"), ("p", "PDB")):
            check("PNG-renamed-json style magic %s" % t, has(m, "config/%s.json" % p, "BINARY_MAGIC_" + t))
        m, _ = reasons({"docs.md": b"a\0b\n"}, "nulcase")
        check("NUL byte in text file", has(m, "docs.md", "BINARY_CONTENT"))
        m, _ = reasons({"docs.md": b"caf\xe9 latin-1\n"}, "badutf")
        check("invalid UTF-8 in text file", has(m, "docs.md", "BINARY_CONTENT"))
        m, _ = reasons({"tools/k.h": b"static const unsigned char my_retail_key[16] = {\n"
                        b"0x00,0x01,0x02,0x03,0x04,0x05,0x06,0x07,0x08,0x09,0x0a,0x0b,0x0c,0x0d,0x0e,0x0f};\n"},
                       "key16")
        check("16-byte key array", has(m, "tools/k.h", "KEY_MATERIAL"))
        m, _ = reasons({"tools/k.h": b"static const unsigned char other[16] = {"
                        b"0,1,2,3,4,5,6,7,8,9,10,11,12,13,14,15};\n"
                        b"static const unsigned char my_key[5] = {1,2,3,4,5};\n"}, "keynot")
        check("non-key array and short key array pass", not m["tools/k.h"])
        m, _ = reasons({"x.md": (pem + "\nAAAA\n").encode()}, "pem")
        check("PEM private key header", has(m, "x.md", "KEY_MATERIAL"))
        m, _ = reasons({"x.txt": b"api_secret = " + b"ab" * 16 + b"\n"}, "hexkey")
        check("hex secret literal", has(m, "x.txt", "KEY_MATERIAL") and "ab" * 16 not in repr(m))
        m, _ = reasons({"x.txt": b"shared key = " + b"cd" * 16 + b"\n"}, "hexkey2")
        check("'shared' does not count as a hash word", has(m, "x.txt", "KEY_MATERIAL"))
        for bad in ("NOT_ALLOWLISTED:x.md", "GAME_FILE_HASH:x.md", "DEVELOPER_PATH:reports/*"):
            try:
                parse_waivers([bad])
                check("waiver refused: " + bad, False)
            except ConfigError:
                check("waiver refused: " + bad, True)
        m, _ = reasons({"x.md": ("line1\npath C:\\" + users + "\\alice\\work\\x\n").encode()}, "dev")
        check("developer path (Windows)", has(m, "x.md", "DEVELOPER_PATH"))
        m, _ = reasons({"x.md": ("see " + home + "bob/proj and /c/" + users + "/carol/x and C:\\\\" + users + "\\\\dave\\\\y\n").encode()}, "dev2")
        check("developer path (posix/msys/json-escaped)", has(m, "x.md", "DEVELOPER_PATH"))
        m, _ = reasons({"x.log": ("obj CMakeFiles/t.dir/C_/" + users + "/erin/proj/a.cpp.obj\n").encode()}, "dev3")
        check("developer path (CMake object path C_/Users)", has(m, "x.log", "DEVELOPER_PATH"))
        m, res = reasons({"private/x.md": b"hello\n"}, "priv")
        check("file under private/", has(m, "private/x.md", "DENIED_PATH"))
        m, _ = reasons({"Generated/a.md": b"x\n", "tools/__pycache__/a.py": b"x\n", "sub/.git/c.md": b"x\n",
                        "config/build/ok.json": b"{}\n"}, "deny")
        check("deny: case-insensitive prefix, __pycache__, .git segment",
              has(m, "Generated/a.md", "DENIED_PATH") and has(m, "tools/__pycache__/a.py", "DENIED_PATH")
              and has(m, "sub/.git/c.md", "DENIED_PATH"))
        check("deny: root-only build/ does not hit config/build/", not m["config/build/ok.json"])
        m, _ = reasons({"blob.bin": b"hello\n", "tools/y.txt": b"hello\n"}, "unk")
        check("unknown extension .bin", m["blob.bin"] == {"NOT_ALLOWLISTED"})
        check("harmless but unlisted dir is rejected", has(m, "tools/y.txt", "NOT_ALLOWLISTED"))
        marker = b"PPC_FUNC_IMPL(fn) {\n"
        m, _ = reasons({"tools/gen.cpp": marker * (GEN_THRESHOLD + 5),
                        "tools/few.cpp": marker * (GEN_THRESHOLD - 1),
                        "tools/r3hd_recomp.12.cpp": b"// empty\n"}, "gen")
        check("bulk generated code markers", has(m, "tools/gen.cpp", "GENERATED_CODE"))
        check("few markers do not trip", not has(m, "tools/few.cpp", "GENERATED_CODE"))
        check("generated file name", has(m, "tools/r3hd_recomp.12.cpp", "GENERATED_CODE"))
        m, _ = reasons({"reports/planted.txt": planted, "reports/other.txt": planted + b"x"}, "hash")
        check("game file hash from manifest", has(m, "reports/planted.txt", "GAME_FILE_HASH"))
        check("different hash passes", not m["reports/other.txt"])
        m, _ = reasons({"docs/5841123F/00000001/save.md": b"x\n", "a/.staging/1.md": b"x\n"}, "save")
        check("save-data paths", has(m, "docs/5841123F/00000001/save.md", "SAVE_DATA")
              and has(m, "a/.staging/1.md", "SAVE_DATA"))
        m, _ = reasons({"reports/frame.png": b"x", "reports/s.wav": b"x", "capframex/a.json": b"{}\n",
                        "reports/v.mp4": b"x"}, "cap")
        check("capture extensions and capframex paths", all(
            has(m, p, "CAPTURE") for p in ("reports/frame.png", "reports/s.wav", "capframex/a.json",
                                           "reports/v.mp4")))
        big = os.path.join(tmp, "big")
        os.makedirs(big)
        with open(os.path.join(big, "x.md"), "wb") as f:
            f.write(b"a" * (allow.max_bytes + 1))
        res = run_audit(entries_dir(big), allow, hashes)
        check("oversize text file", res["reason_counts"].get("TOO_LARGE") == 1)

        # zip fixtures (members are read in memory; nothing is extracted)
        def make_zip(name, members):
            p = os.path.join(tmp, name)
            with zipfile.ZipFile(p, "w") as z:
                for member, data in members:
                    if isinstance(member, zipfile.ZipInfo):
                        z.writestr(member, data)
                    else:
                        z.writestr(member, data)
            return p

        z = make_zip("trav.zip", [("../evil.md", b"x\n"), ("/abs.md", b"x\n"), ("C:/drive.md", b"x\n"),
                                  ("ok.md", b"fine\n"), ("dir\\..\\back.md", b"x\n")])
        res = run_audit(entries_zip(z), allow, hashes)
        by = {r["path"]: {x["code"] for x in r["reasons"]} for r in res["results"]}
        check("zip ../evil.md", "UNSAFE_MEMBER" in by["../evil.md"])
        check("zip absolute and drive members", "UNSAFE_MEMBER" in by["/abs.md"]
              and "UNSAFE_MEMBER" in by["C:/drive.md"])
        check("zip backslash traversal", "UNSAFE_MEMBER" in next(v for k, v in by.items() if k.endswith("back.md")))
        check("zip clean member still passes", not by["ok.md"])
        info = zipfile.ZipInfo("link.md")
        info.external_attr = (stat.S_IFLNK | 0o777) << 16
        z = make_zip("sym.zip", [(info, "ok.md")])
        res = run_audit(entries_zip(z), allow, hashes)
        check("zip symlink member", res["results"][0]["reasons"][0]["code"] == "UNSAFE_MEMBER")
        z = make_zip("nested.zip", [("deep/Default.xex", b"XEX2" + b"\0" * 60), ("x.md", b"ok\n")])
        res = run_audit(entries_zip(z), allow, hashes)
        by = {r["path"]: {x["code"] for x in r["reasons"]} for r in res["results"]}
        check("zip with nested .xex", {"BINARY_MAGIC_XEX2", "NOT_ALLOWLISTED"} <= by["deep/Default.xex"])
        z = make_zip("clean.zip", [("README.md", b"# ok\n"), ("tools/a.py", b"print(1)\n")])
        res = run_audit(entries_zip(z), allow, hashes)
        check("clean zip passes", res["verdict"] == "PASS" and res["files"] == 2)
        check("zip not extracted", sorted(os.listdir(tmp)).count("README.md") == 0)

        # waivers
        m, res = reasons({"x.md": ("path C:\\" + users + "\\alice\\w\n").encode()}, "waive",
                         waivers=parse_waivers(["DEVELOPER_PATH:x.md"]))
        check("--allow-finding waives and records", res["verdict"] == "PASS"
              and res["allowed_findings"] == ["DEVELOPER_PATH:x.md"]
              and res["results"][0]["waived"][0]["code"] == "DEVELOPER_PATH")
        m, res = reasons({"x.md": ("path C:\\" + users + "\\alice\\w\n").encode(), "y.md": ("C:\\" + users + "\\bob\\w\n").encode()}, "waive2",
                         waivers=parse_waivers(["DEVELOPER_PATH:x.md"]))
        check("waiver is per path", res["verdict"] == "FAIL" and res["rejected"] == 1)
        m, res = reasons({"x.md": ("path C:\\" + users + "\\alice\\w\n").encode()}, "waive3",
                         waivers=parse_waivers(["CAPTURE:x.md"]))
        check("waiver is per code", res["verdict"] == "FAIL")

        # CLI end to end: exit codes, output lines, JSON notice, no key bytes echoed
        clean = os.path.join(tmp, "clean")
        outp = os.path.join(tmp, "out.json")
        buf = io.StringIO()
        old = sys.stdout
        sys.stdout = buf
        try:
            rc_ok = main(["scan", clean, "--game-manifest", manifest, "--json", outp])
            rc_bad = main(["scan", os.path.join(tmp, "hexkey"), "--game-manifest", manifest])
            rc_w = main(["scan", os.path.join(tmp, "dev"), "--game-manifest", manifest,
                         "--allow-finding", "DEVELOPER_PATH:x.md"])
        finally:
            sys.stdout = old
        text = buf.getvalue()
        check("CLI exit codes 0 / 2 / 0", (rc_ok, rc_bad, rc_w) == (0, 2, 0))
        check("CLI result lines", "R3HD_RELEASE_AUDIT PASS files=5" in text
              and "R3HD_RELEASE_AUDIT FAIL files=1 rejected=1" in text and "ALLOWED_FINDING DEVELOPER_PATH x.md" in text)
        check("CLI prints not-legal notice", text.count("NOT a legal clearance") >= 3)
        check("CLI never echoes key bytes", "ab" * 16 not in text)
        with open(outp, encoding="utf-8") as f:
            js = json.load(f)
        check("JSON carries notice and verdict", "NOT a legal clearance" in js["notice"] and js["verdict"] == "PASS")

    # M29: payload mode (synthetic fixtures; the tracked payload allowlist, fixture pins)
    with tempfile.TemporaryDirectory(prefix="r3hd_payload_") as tmp:
        manifest = os.path.join(tmp, "manifest.tsv")
        planted = b"synthetic planted game file payload " * 4
        with open(manifest, "wb") as f:
            f.write(b"synthetic.dat\t%d\t%s\n" % (len(planted), hashlib.sha256(planted).hexdigest().encode()))
        hashes = GameHashes([manifest], None)
        pallow = Allowlist(DEFAULT_PAYLOAD_ALLOWLIST)
        with open(DEFAULT_PAYLOAD_ALLOWLIST, "r", encoding="utf-8") as f:
            pbin = json.load(f)["binaries"]
        zbuf = io.BytesIO()
        with zipfile.ZipFile(zbuf, "w") as zf:
            zf.writestr("os.py", "import sys\n")
        base = {"bin/r3hd.exe": b"MZ" + b"\0" * 62 + b"game exe", "bin/rexruntime.dll": b"MZ" + b"\0" * 62 + b"rt",
                "bin/rexgpu-xenos.dll": b"MZ" + b"\0" * 62 + b"gpu", "app/python/python.exe": b"MZ" + b"\0" * 62 + b"py",
                "app/python/python311.zip": zbuf.getvalue(), "app/tools/r3hd_installer.py": b"print('ok')\n",
                "app/r3hd_launcher.exe": b"MZ" + b"\0" * 62 + b"settings"}
        pins = {"app/python/python.exe": hashlib.sha256(base["app/python/python.exe"]).hexdigest(),
                "app/python/python311.zip": hashlib.sha256(base["app/python/python311.zip"]).hexdigest()}

        def payload(name, files, unlisted=(), lie=None, publishable=False, drop=()):
            root = os.path.join(tmp, name)
            listed = {}
            for rel, data in files.items():
                p = os.path.join(root, *rel.split("/"))
                os.makedirs(os.path.dirname(p), exist_ok=True)
                with open(p, "wb") as f:
                    f.write(data)
                if rel not in unlisted:
                    listed[rel] = {"size": len(data), "sha256": hashlib.sha256(data).hexdigest()}
            for rel in drop:
                os.remove(os.path.join(root, *rel.split("/")))
            if lie:
                listed[lie]["sha256"] = "0" * 64
            with open(os.path.join(root, "payload.json"), "w", encoding="utf-8") as f:
                json.dump({"schema": 1, "publishable": publishable, "files": listed}, f)
            res = audit_payload(root, pallow, pbin, pins, hashes)
            return {r["path"]: {x["code"] for x in r["reasons"]} for r in res["results"]}, res

        m, res = payload("clean", base)
        check("payload: clean fixture passes, classified private", res["verdict"] == "PASS" and res["private"])
        m, _ = payload("extra", dict(base, **{"app/tools/evil.dll": b"MZ" + b"\0" * 40}), unlisted=("app/tools/evil.dll",))
        check("payload: unlisted binary refused", {"UNLISTED_FILE", "NOT_ALLOWLISTED"} <= m["app/tools/evil.dll"])
        m, _ = payload("devpath", dict(base, **{"bin/r3hd.exe": base["bin/r3hd.exe"] + ("D:\\" + users + "\\bob\\src\\a.cpp").encode()}))
        check("payload: developer path inside a native binary", has(m, "bin/r3hd.exe", "DEVELOPER_PATH"))
        m, _ = payload("devpath16", dict(base, **{"bin/rexruntime.dll": base["bin/rexruntime.dll"]
                                                  + ("C:/" + users + "/bob/x.h").encode("utf-16-le")}))
        check("payload: UTF-16 developer path inside a native binary", has(m, "bin/rexruntime.dll", "DEVELOPER_PATH"))
        m, _ = payload("devpath_launcher", dict(base, **{"app/r3hd_launcher.exe": base["app/r3hd_launcher.exe"]
                                                         + ("C:\\" + users + "\\bob\\l.cpp").encode()}))
        check("payload: developer path inside the Settings launcher (M30)", has(m, "app/r3hd_launcher.exe", "DEVELOPER_PATH"))
        m, _ = payload("launcher_kind", dict(base, **{"app/r3hd_launcher.exe": b"not a program"}))
        check("payload: the Settings launcher must be a PE binary", has(m, "app/r3hd_launcher.exe", "BINARY_KIND"))
        m, _ = payload("pin", dict(base, **{"app/python/python.exe": base["app/python/python.exe"] + b"!"}))
        check("payload: Python runtime that is not the pinned one", has(m, "app/python/python.exe", "PIN_MISMATCH"))
        m, _ = payload("game", dict(base, **{"bin/rexgpu-xenos.dll": planted}))
        check("payload: game file under a binary name", {"GAME_FILE_HASH", "BINARY_KIND"} <= m["bin/rexgpu-xenos.dll"])
        m, _ = payload("missing", base, drop=("bin/rexgpu-xenos.dll",))
        check("payload: listed file missing", has(m, "bin/rexgpu-xenos.dll", "MISSING_FILE"))
        m, _ = payload("lie", base, lie="bin/r3hd.exe")
        check("payload: manifest hash differs", has(m, "bin/r3hd.exe", "MANIFEST_MISMATCH"))
        m, _ = payload("pub", base, publishable=True)
        check("payload: publishable flag refused", has(m, "payload.json", "PAYLOAD_MANIFEST"))
        zbad = io.BytesIO()
        with zipfile.ZipFile(zbad, "w") as zf:
            zf.writestr("x.pyd", b"MZ")
        m, _ = payload("zip", dict(base, **{"app/python/python311.zip": zbad.getvalue()}))
        check("payload: stdlib zip with a non-.py member", has(m, "app/python/python311.zip", "ZIP_MEMBER"))
        m, _ = payload("pdb", dict(base, **{"bin/r3hd.pdb": b"Microsoft C/C++ MSF 7.00\r\n\x1aDS\0\0\0"}))
        check("payload: debug symbols refused", has(m, "bin/r3hd.pdb", "NOT_ALLOWLISTED"))
        m, _ = payload("key", dict(base, **{"app/tools/r3hd_installer.py": ("x = 1\n" + pem + "\n").encode()}))
        check("payload: text rules still apply", has(m, "app/tools/r3hd_installer.py", "KEY_MATERIAL"))

    bad = [n for n, ok in checks if not ok]
    if bad:
        print("R3HD_RELEASE_AUDIT_SELFTEST FAIL checks=%d failed=%d" % (len(checks), len(bad)))
        return 1
    print("R3HD_RELEASE_AUDIT_SELFTEST PASS checks=%d" % len(checks))
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description="Fail-closed release-package audit (technical only, not legal clearance)")
    sub = ap.add_subparsers(dest="cmd", required=True)

    def common(p):
        p.add_argument("--allowlist", help="allowlist JSON (default config/release/allowlist.json)")
        p.add_argument("--json", help="write the full result as JSON")
        p.add_argument("--game-manifest", help="TSV of game file sizes and SHA-256 (default: tracked M1 manifest)")
        p.add_argument("--allow-finding", action="append", metavar="CODE:PATH",
                       help="explicit recorded exception for one reason code on a path (glob); repeatable")
        p.add_argument("-v", "--verbose", action="store_true", help="also print PASS lines")

    p = sub.add_parser("scan", help="audit a directory or a .zip")
    p.add_argument("target")
    common(p)
    p = sub.add_parser("git", help="audit the files git tracks in this repository")
    p.add_argument("--rev", help="read content from this revision instead of the working tree")
    common(p)
    p = sub.add_parser("payload", help="audit a staged private installer payload (tools/r3hd_stage.py)")
    p.add_argument("target")
    common(p)
    sub.add_parser("selftest", help="synthetic fixtures; no game data")
    args = ap.parse_args(argv)
    try:
        if args.cmd == "selftest":
            return selftest()
        if args.cmd == "payload":
            if args.allow_finding:
                raise ConfigError("payload audits take no --allow-finding")
            return cmd_payload(args)
        return cmd_scan(args) if args.cmd == "scan" else cmd_git(args)
    except ConfigError as e:
        sys.stderr.write("R3HD_RELEASE_AUDIT ERROR %s\n" % e)
        return 3


if __name__ == "__main__":
    sys.exit(main())
