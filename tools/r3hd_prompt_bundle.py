"""D-203: accepted exact binary resources; normal payload audit is mandatory."""
import hashlib
import json
from pathlib import Path

import r3hd_button_prompts as prompts

PREFIX = "app/assets/playstation_prompts/"
MANIFEST = (json.dumps({"schema": 2, "kind": "r3hd-private-ps3-button-glyphs"},
                       sort_keys=True, separators=(",", ":")) + "\n").encode()


def collect(root, descriptor):
    record = json.loads((Path(root) / descriptor["record"]).read_text(encoding="utf-8"))
    if record.get("bundling_authorized") is not True:
        raise ValueError("D-203: exact glyph bundle inclusion is not authorized")
    return candidate(root, descriptor)


def candidate(root, descriptor):
    """Private inspection only, not a staged installer or authorization bypass."""
    root = Path(root)
    record = json.loads((root / descriptor["record"]).read_text(encoding="utf-8"))
    names = {PREFIX + n + ".png" for n in prompts.NATIVE_GLYPHS} | {PREFIX + "glyphs.json"}
    if (record.get("schema") != 1 or record.get("kind") != "r3hd-controller-prompt-bundle"
            or record.get("decision") != "D-203"
            or record.get("publication_authorized") is not False or set(record.get("files", {})) != names):
        raise ValueError("invalid controller prompt bundle record")
    source = root / descriptor["source_manifest"]
    prompts.read_glyphs(source)  # accepted dimensions and decoded-pixel identities
    files = {PREFIX + n + ".png": (source.parent / (n + ".png")).read_bytes()
             for n in prompts.NATIVE_GLYPHS}
    files[PREFIX + "glyphs.json"] = MANIFEST
    for name, data in files.items():
        pin = record["files"][name]
        if pin != {"size": len(data), "sha256": hashlib.sha256(data).hexdigest()}:
            raise ValueError("controller prompt resource pin mismatch: " + name)
    return files
