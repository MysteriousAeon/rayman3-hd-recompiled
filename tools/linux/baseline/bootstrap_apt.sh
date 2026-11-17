#!/bin/sh
# Authenticate public Ubuntu roots before the first TLS request. No install/registration
# here: ca-certificates' openssl/debconf dependencies are installed later through APT.
set -eu
export LC_ALL=C
root=${1:-/}  # offline fixture root only; Containerfile supplies no argument
seed=${root%/}/opt/r3hd-bootstrap
keyring=${root%/}/usr/share/keyrings/ubuntu-archive-keyring.gpg
stop() { printf 'R3HD_CA_BOOTSTRAP STOP: %s\n' "$*" >&2; exit 2; }
printf '%s\n' "80a36b0a6de2f69f49d2df75ef473ccde121e9e190b9ea01d20a4f63778d5c31  $keyring" \
 "4fc50c210fe25d45aeb6d6a3e0d0c03f506dde317af2999761547e47a9b2df8d  $seed/InRelease" \
 "5be105a4c1cde9a3fefc639f9c26ac40a53165690c98dcd2730f6409db2525ec  $seed/Packages.gz" \
 "f9fbacd417b515450b831032cc39d18059e9874e67525679a43c16071dabf9a0  $seed/ca-certificates.deb" \
 | sha256sum -c - || stop 'input hash mismatch'
gpgv --keyring "$keyring" "$seed/InRelease" || stop 'Ubuntu archive signature failed'
awk '$0=="SHA256:" {sha=1; next} sha && $0 !~ /^ / {sha=0}
 sha && $1=="5be105a4c1cde9a3fefc639f9c26ac40a53165690c98dcd2730f6409db2525ec" && $2==1761749 && $3=="main/binary-amd64/Packages.gz" {found++}
 END {exit found!=1}' "$seed/InRelease" || stop 'index not bound to signed release'
gzip -cd "$seed/Packages.gz" | awk 'BEGIN {RS=""; FS="\n"}
 {p=v=h=f=""; for(i=1;i<=NF;i++) {
  if($i~/^Package: /) p=substr($i,10); if($i~/^Version: /) v=substr($i,10);
  if($i~/^SHA256: /) h=substr($i,9); if($i~/^Filename: /) f=substr($i,11)}
  if(p=="ca-certificates" && v=="20260816ubuntu0.24.04.2" && h=="f9fbacd417b515450b831032cc39d18059e9874e67525679a43c16071dabf9a0" && f=="pool/main/c/ca-certificates/ca-certificates_20260816ubuntu0.24.04.2_all.deb") found++}
 END {exit found!=1}' || stop 'CA package not bound to authenticated index'
[ "$(dpkg-deb -f "$seed/ca-certificates.deb" Package)" = ca-certificates ] || stop 'package identity'
[ "$(dpkg-deb -f "$seed/ca-certificates.deb" Version)" = 20260816ubuntu0.24.04.2 ] || stop 'package version'
[ "$(dpkg-deb -f "$seed/ca-certificates.deb" Architecture)" = all ] || stop 'package architecture'
[ ! -e "$seed/extracted" ] && [ ! -L "$seed/extracted" ] || stop 'extraction already exists'
[ ! -e "$seed/ca-bundle.crt" ] && [ ! -L "$seed/ca-bundle.crt" ] || stop 'bundle already exists'
dpkg-deb -x "$seed/ca-certificates.deb" "$seed/extracted"
count=0
for cert in "$seed/extracted/usr/share/ca-certificates/mozilla/"*.crt; do
    [ -f "$cert" ] && [ ! -L "$cert" ] || stop 'invalid certificate member'
    cat "$cert" >> "$seed/ca-bundle.crt"
    count=$((count+1))
done
[ "$count" -eq 120 ] || stop 'certificate inventory differs'
printf '%s\n' "64e7c24b0536b525fb19b145768bd5e6e12ced0df3db837c34553ea789acd143  $seed/ca-bundle.crt" \
 | sha256sum -c - || stop 'public root bundle differs'
# Public CA data must be readable by APT's existing _apt download sandbox, even if
# the host build context was created with a restrictive umask. Do not disable _apt.
chmod 0755 "$seed"
chmod 0644 "$seed/ca-bundle.crt"
printf 'R3HD_CA_BOOTSTRAP PASS (Ubuntu signature/index/package verified; no package installed)\n'
