"""One-time: extract Refine Tree nodes and prerequisite edges. See README."""

import re
import sys
from pathlib import Path

RAW = Path("data/raw/Minerals__Refine_Tree.wikitext")
RN_PATTERN = re.compile(r"\{\{RN\|(\d+)\|([^{}]*)\}\}", re.DOTALL)


def parse_params(blob: str) -> dict[str, str]:
    params: dict[str, str] = {}
    for part in blob.split("|"):
        if "=" not in part:
            continue
        key, _, value = part.partition("=")
        params[key.strip()] = value.strip()
    return params


def main() -> int:
    if not RAW.is_file():
        print(f"missing {RAW} — run `uv run atlas scrape` first", file=sys.stderr)
        return 1

    matches = RN_PATTERN.findall(RAW.read_text(encoding="utf-8"))
    if not matches:
        print("no {{RN|...}} invocations found", file=sys.stderr)
        return 1

    print("# --- Refine Tree nodes (bootstrap output, review before pasting) ---")
    print("nodes:")
    for number, _ in matches:
        print(f"  - id: refine-node-{number}")
        print(f"    name: Refine Node {number}")
        print("    system: mineral")
        print("    kind: tree-node")
        print("    wiki: Minerals/Refine_Tree")
        print("    confidence: documented")

    print()
    print("edges:")
    edge_count = 0
    for number, blob in matches:
        params = parse_params(blob)
        req = params.get("req", "").strip()
        if not req:
            continue
        # "0" is the wiki's root-node sentinel meaning "no prerequisite" (RN1
        # uses it), not a reference to a node. Filtered per-entry rather than on
        # the whole `req` string so a hypothetical "0,5" drops only the sentinel.
        for prereq in (r.strip() for r in req.split(",") if r.strip() and r.strip() != "0"):
            print(f"  - from: refine-node-{prereq}")
            print(f"    to: refine-node-{number}")
            print("    rel: requires")
            print("    source: wiki:Minerals/Refine_Tree")
            print("    confidence: documented")
            edge_count += 1

    print(f"\n# {len(matches)} nodes, {edge_count} prerequisite edges", file=sys.stderr)
    print(f"# {len(matches)} nodes, {edge_count} prerequisite edges")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
