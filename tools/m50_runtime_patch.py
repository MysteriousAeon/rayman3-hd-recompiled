"""Replay after the M49 patch at the same pin: the shipped runtime carries no key this title cannot use (M50, D-089).

`src/kernel/xboxkrnl/xboxkrnl_crypt.cpp` (idempotent):
  * the kernel HMAC key 0x19 array is removed, and `XeKeysHmacSha` returns X_STATUS_UNSUCCESSFUL for every key
    number, as it already did for every number but 0x19. Rayman 3 HD does not import `XeKeysHmacSha` (its import
    table: reports/milestone1/import_surface.csv), so no guest code can reach it: no behaviour change for this title.

The XEX2 retail key stays: the runtime decrypts the player's own Default.xex at every launch (D-065, D-089). The
devkit and key-obfuscation arrays are all-zero placeholders in this SDK and carry no key.

No key byte appears here (D-003): the array is matched by its name, not its contents. Host-only.
"""
import re

from m8_runtime_patch import SDK

CRYPT = SDK / 'src/kernel/xboxkrnl/xboxkrnl_crypt.cpp'

ARRAY = re.compile(r'// Retail key 0x19\nstatic const uint8_t key19\[\] = \{[^}]*\};\n')
BRANCH = '  if (key_num == 0x19) {\n    key = key19;\n  }\n'
MARK = '// M50 (D-089): key 0x19 removed; this title does not import XeKeysHmacSha.\n'

if __name__ == '__main__':
    text = CRYPT.read_text()
    if MARK not in text:
        assert len(ARRAY.findall(text)) == 1 and text.count(BRANCH) == 1, 'xboxkrnl_crypt.cpp: unexpected layout'
        text = ARRAY.sub(lambda m: MARK, text)
        text = text.replace(BRANCH, '  (void)key_num;  // M50 (D-089): no key is available.\n')
        CRYPT.write_text(text)
        print('patched', CRYPT.relative_to(SDK).as_posix())
    assert 'key19' not in text, 'xboxkrnl_crypt.cpp: key19 still referenced'
