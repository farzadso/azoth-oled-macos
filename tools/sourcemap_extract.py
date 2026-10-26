#!/usr/bin/env python3
"""Write out the original sources embedded in a webpack source map.

Usage: sourcemap_extract.py SOURCE_MAP OUT_DIR

Skips node_modules and sources without embedded content.
"""

import json
import os
import sys


def extract(map_path, out):
    with open(map_path) as f:
        source_map = json.load(f)
    count = 0
    for name, content in zip(source_map.get("sources", []), source_map.get("sourcesContent") or []):
        if content is None or "node_modules" in name:
            continue
        rel = name.replace("webpack://", "").replace("../", "").lstrip("./")
        target = os.path.join(out, rel)
        os.makedirs(os.path.dirname(target), exist_ok=True)
        with open(target, "w") as g:
            g.write(content)
        count += 1
    print(f"{count} files written to {out}")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit(__doc__.strip())
    extract(sys.argv[1], sys.argv[2])
