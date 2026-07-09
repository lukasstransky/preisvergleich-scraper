import argparse
import json
import os
import time
from scrapers.billa import scrape_billa
from scrapers.spar import scrape_spar, CATEGORIES as SPAR_CATEGORIES
from scrapers.hofer import scrape_hofer
from scrapers.hofer_flugblatt import scrape_hofer_flugblatt
from scrapers.penny import scrape_penny
from scrapers.lidl import scrape_lidl
from scrapers.mpreis import scrape_mpreis
from firebase_store import upload_all

SCRAPERS = {
    "billa":  ("billa.json",  scrape_billa),
    "spar":   ("spar.json",   scrape_spar),
    "hofer":  ("hofer.json",  scrape_hofer),
    "hofer_flugblatt": ("hofer_flugblatt.json", scrape_hofer_flugblatt),
    "penny":  ("penny.json",  scrape_penny),
    "lidl":   ("lidl.json",   scrape_lidl),
    #"mpreis": ("mpreis.json", scrape_mpreis), #run scraper first
}


def _fmt_duration(seconds):
    if seconds < 60:
        return f"{seconds:.1f}s"
    return f"{seconds / 60:.1f}m"


def _load_from_json(filepath):
    """Load products from a JSON file."""
    with open(filepath, "r", encoding="utf-8") as f:
        products = json.load(f)
    print(f"Loaded {len(products)} products from {filepath}")
    return products


def main():
    parser = argparse.ArgumentParser(description="Scrape supermarkets and upload to Firebase.")
    parser.add_argument(
        "--upload-only",
        action="store_true",
        help="Skip scraping and upload existing JSON files to Firebase.",
    )
    parser.add_argument(
        "--no-upload",
        action="store_true",
        help="Skip uploading to Firebase (scrape only).",
    )
    parser.add_argument(
        "--scraper",
        nargs="+",
        choices=list(SCRAPERS.keys()),
        metavar="SCRAPER",
        help=f"Run only the specified scraper(s). Choices: {', '.join(SCRAPERS.keys())}",
    )
    parser.add_argument(
        "--spar-categories",
        nargs="+",
        choices=SPAR_CATEGORIES,
        metavar="CATEGORY",
        help=f"Limit SPAR scraper to specific categories. Choices: {', '.join(SPAR_CATEGORIES)}",
    )
    args = parser.parse_args()

    active_scrapers = {k: v for k, v in SCRAPERS.items() if not args.scraper or k in args.scraper}

    start_time = time.time()
    timings = {}
    all_products = {}

    if args.upload_only:
        print("Upload-only mode: loading products from JSON files...\n")
        for name, (json_file, _) in active_scrapers.items():
            if os.path.exists(json_file):
                t = time.time()
                all_products[name] = _load_from_json(json_file)
                timings[name.capitalize()] = time.time() - t
            else:
                print(f"WARNING: {json_file} not found, skipping {name}")
        print()
    else:
        # Delete existing JSON files to avoid duplicated data
        for name, (json_file, _) in active_scrapers.items():
            if os.path.exists(json_file):
                os.remove(json_file)
                print(f"Deleted {json_file}")

        for name, (json_file, scrape_fn) in active_scrapers.items():
            label = name.capitalize()
            print(f"Starting {label} scraper...")
            t = time.time()
            if name == "spar" and args.spar_categories:
                all_products[name] = scrape_fn(categories=args.spar_categories)
            else:
                all_products[name] = scrape_fn()
            timings[label] = time.time() - t
            print()

    # Upload to Firebase Firestore
    if args.no_upload:
        print("Skipping Firebase upload (--no-upload).\n")
    else:
        print("Uploading to Firebase...")
        t = time.time()
        upload_all(all_products)
        timings["Upload"] = time.time() - t
        print()

    total = time.time() - start_time

    print("=" * 40)
    print("Timing summary:")
    for name, duration in timings.items():
        print(f"  {name:<10} {_fmt_duration(duration)}")
    print(f"  {'Total':<10} {_fmt_duration(total)}")
    print("=" * 40)


if __name__ == "__main__":
    main()
