import argparse

from . import db, jev, tools

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--skip-jev", action="store_true", help="use rule-based fallback only")
    ap.add_argument("--limit", type=int, default=None, help="classify only top N merchants")
    ap.add_argument("--enrich-only", action="store_true", help="only rebuild enriched table")
    args = ap.parse_args()

    if args.enrich_only:
        tools.build_enriched()
        print("done: enriched")
    else:
        db.ingest()
        if not args.skip_jev:
            jev.classify_merchants(limit=args.limit)
        tools.build_enriched()
        print("done: ingested, classified, enriched")
