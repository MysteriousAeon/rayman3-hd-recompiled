#!/bin/sh
# Bind every authenticated APT release to the exact locked snapshot, before installing.
set -eu
root=${1:-/}
lists=${root%/}/var/lib/apt/lists
printf '%s\n' \
 "cdb2f31d809f589719a53c6ad15f255b27569c4059542ada282aaa21b8e164b0  $lists/snapshot.ubuntu.com_ubuntu_20261108T000000Z_dists_noble_InRelease" \
 "4fc50c210fe25d45aeb6d6a3e0d0c03f506dde317af2999761547e47a9b2df8d  $lists/snapshot.ubuntu.com_ubuntu_20261108T000000Z_dists_noble-updates_InRelease" \
 "ccdb2434d2725a726fead9e11c1ab0f2ad99c1e72881a68244afab698156d6cc  $lists/snapshot.ubuntu.com_ubuntu_20261108T000000Z_dists_noble-security_InRelease" \
 | sha256sum -c -
printf 'R3HD_SNAPSHOT_LISTS PASS\n'
