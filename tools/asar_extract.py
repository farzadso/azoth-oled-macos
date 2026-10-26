#!/usr/bin/env python3
"""Extract an Electron app.asar archive.

Usage: asar_extract.py APP_ASAR OUT_DIR

Files that the archive marks as unpacked live next to it in app.asar.unpacked
and are skipped.
"""

import json
import os
import struct
import sys


def extract(src, out):
    with open(src, "rb") as f:
        data = f.read()
    # Chromium pickle header: payload size, header size, then the JSON length.
    header_size = struct.unpack("<I", data[4:8])[0]
    json_len = struct.unpack("<I", data[12:16])[0]
    header = json.loads(data[16:16 + json_len])
    base = 8 + header_size

    def walk(node, path):
        for name, child in node.get("files", {}).items():
            target = os.path.join(path, name)
            if "files" in child:
                os.makedirs(target, exist_ok=True)
                walk(child, target)
            elif "offset" in child and not child.get("unpacked"):
                start = base + int(child["offset"])
                with open(target, "wb") as g:
                    g.write(data[start:start + child["size"]])

    os.makedirs(out, exist_ok=True)
    walk(header, out)


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit(__doc__.strip())
    extract(sys.argv[1], sys.argv[2])
