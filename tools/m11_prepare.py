"""M11 host additions: include the GPU-wait hook configuration (D-037) in the codegen manifest."""
from m2_prepare import W, write_text_if_changed

if __name__ == '__main__':
    manifest = W / 'r3hd_manifest.toml'
    text = manifest.read_text()
    entry = '"../../../config/rexglue/r3hd_wait.toml"'
    if entry not in text:
        anchor = '"../../../config/rexglue/r3hd_nonlocal.toml"]'
        assert text.count(anchor) == 1, 'manifest include list not recognised'
        text = text.replace(anchor, anchor[:-1] + ', ' + entry + ']')
    write_text_if_changed(manifest, text)
