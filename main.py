import os
import sys
import traceback
from datetime import datetime

# Force UTF-8 stdout so non-ASCII log lines survive Windows cp1252 encoding.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from src.enrichment.pipeline import run_pipeline, DEFAULT_WORKERS


def get_listing_url():
    """Resolve the platform listing URL from CLI arg or PLATFORM_URL env var."""
    if len(sys.argv) > 1 and sys.argv[1].strip():
        return sys.argv[1].strip()
    return os.environ.get("PLATFORM_URL", "").strip()


def main():
    listing_url = get_listing_url()

    print("\nMULTI-SOURCE LEAD ENRICHMENT PIPELINE STARTED\n")

    if not listing_url:
        print(
            "ERROR: No platform URL provided.\n"
            "Usage: python main.py <coinmarketcap|coingecko|coinranking listing URL>"
        )
        sys.exit(1)

    print("=" * 60)
    print(f"Input URL: {listing_url}")
    print("=" * 60)

    limit_env = os.environ.get("LEAD_LIMIT", "").strip()
    limit = int(limit_env) if limit_env.isdigit() else None

    mode = os.environ.get("EXTRACT_MODE", "ranked").strip().lower()
    if mode not in ("ranked", "recent"):
        mode = "ranked"

    workers_env = os.environ.get("WORKERS", "").strip()
    workers = int(workers_env) if workers_env.isdigit() and int(workers_env) >= 1 else DEFAULT_WORKERS

    start = datetime.now()
    try:
        run_pipeline(
            listing_url,
            emit=lambda msg: print(msg, flush=True),
            limit=limit,
            mode=mode,
            workers=workers,
        )
    except Exception as exc:
        print(f"\nPIPELINE FAILED: {exc}")
        traceback.print_exc()
        sys.exit(1)

    print(f"\nPIPELINE COMPLETED SUCCESSFULLY in {datetime.now() - start}")


if __name__ == "__main__":
    main()
