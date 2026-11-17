#!/bin/sh
# No Python/awk/install required: run before the first APT request. Optional root is
# for offline synthetic tests only. Production uses / and explicit APT source paths.
set -eu
export LC_ALL=C
stop() { printf 'R3HD_APT_SOURCES STOP: %s\n' "$*" >&2; exit 2; }
root=${1:-/}
apt_dir=${root%/}/etc/apt
legacy=$apt_dir/sources.list
parts=$apt_dir/sources.list.d
[ -z "${APT_CONFIG:-}" ] || stop 'APT_CONFIG override requires review'
[ ! -L "$apt_dir" ] && [ -d "$apt_dir" ] || stop 'invalid apt directory'
if [ -e "$legacy" ] || [ -L "$legacy" ]; then
    [ ! -L "$legacy" ] && [ -f "$legacy" ] || stop 'sources.list must be a regular file'
    while IFS= read -r line || [ -n "$line" ]; do
        # Strip leading spaces/tabs/etc.; blank/comment lines have no APT entries.
        line=${line#"${line%%[![:space:]]*}"}
        case "$line" in ''|\#*) ;; *) stop 'active or unsupported sources.list entry' ;; esac
    done < "$legacy"
fi
[ ! -L "$parts" ] && [ -d "$parts" ] || stop 'invalid sources.list.d'
for entry in "$parts"/* "$parts"/.[!.]* "$parts"/..?*; do
    if [ ! -e "$entry" ] && [ ! -L "$entry" ]; then continue; fi
    [ "$entry" = "$parts/ubuntu.sources" ] || stop "unexpected source entry: $entry"
    [ ! -L "$entry" ] && [ -f "$entry" ] || stop 'snapshot source must be a regular file'
done
[ -f "$parts/ubuntu.sources" ] || stop 'snapshot source missing'
# Exact HTTPS snapshot policy, including Signed-By; no additional/duplicate fields,
# live URI, Trusted=yes, alternate keyring, component, suite or architecture accepted.
printf '%s\n' "be122120d6ee9ed4204c3e9443a1d0173032275a4becdf51f652f6523720c3f5  $parts/ubuntu.sources" \
    | sha256sum -c - || stop 'snapshot source content differs from the locked policy'
printf 'R3HD_APT_SOURCES PASS (comment-only legacy file; exact signed snapshot source)\n'
