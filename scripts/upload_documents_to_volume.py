"""
Upload synthetic GridLens Queensland documents to a Unity Catalog volume.

Default target volume:
    /Volumes/anzgt_may/energyq/asset_docs

This uses the Databricks SDK Files API. The local layout
    data/documents/<region_id>/<document_type>/<doc>.md
is mirrored to
    /Volumes/anzgt_may/energyq/asset_docs/<region_id>/<document_type>/<doc>.md

Usage:
    python scripts/upload_documents_to_volume.py
    python scripts/upload_documents_to_volume.py --volume /Volumes/anzgt_may/energyq/asset_docs
    python scripts/upload_documents_to_volume.py --dry-run
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--local-dir", default="data/documents")
    parser.add_argument(
        "--volume",
        default=os.getenv("DATABRICKS_VOLUME_PATH", "/Volumes/anzgt_may/energyq/asset_docs"),
    )
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--limit", type=int, help="Only upload first N files.")
    args = parser.parse_args()

    local_root = Path(args.local_dir)
    if not local_root.exists():
        print(f"Local dir not found: {local_root}", file=sys.stderr)
        return 2
    files = sorted(local_root.rglob("*.md"))
    if args.limit:
        files = files[: args.limit]

    print(f"\n  Found {len(files)} markdown files under {local_root}")
    print(f"  Target volume: {args.volume}")

    if args.dry_run:
        print("  --dry-run: not uploading.")
        for f in files[:5]:
            rel = f.relative_to(local_root)
            print(f"    would upload {rel} -> {args.volume}/{rel}")
        return 0

    try:
        from databricks.sdk import WorkspaceClient  # type: ignore
    except ImportError:
        print("Install databricks-sdk: pip install databricks-sdk", file=sys.stderr)
        return 3

    ws = WorkspaceClient()
    uploaded = 0
    for f in files:
        rel = f.relative_to(local_root)
        target = f"{args.volume}/{rel.as_posix()}"
        with f.open("rb") as src:
            ws.files.upload(target, src, overwrite=True)
        uploaded += 1
        if uploaded % 50 == 0:
            print(f"    uploaded {uploaded}/{len(files)}")
    print(f"\n  Uploaded {uploaded} files to {args.volume}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
