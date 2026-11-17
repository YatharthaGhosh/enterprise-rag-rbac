"""Index everything under data/docs (incrementally).

    python scripts/ingest.py           # index new/changed files, purge deleted ones
    python scripts/ingest.py --force   # re-embed everything

Stop the API first when using embedded Qdrant: it allows one process at a time.
"""

import argparse
import logging
import sys
import time
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.ingest import sync_directory  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true", help="re-embed even unchanged files")
    args = ap.parse_args()
    logging.basicConfig(level=logging.WARNING)
    t0 = time.perf_counter()
    results = sync_directory(force=args.force)
    for r in results:
        print(f"{r.status:8} {r.chunks:4} chunks  {r.source_path}  {r.detail}")
    print(dict(Counter(r.status for r in results)), f"total chunks: {sum(r.chunks for r in results)}",
          f"in {time.perf_counter() - t0:.1f}s")


if __name__ == "__main__":
    main()
