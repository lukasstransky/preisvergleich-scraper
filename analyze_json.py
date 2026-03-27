#!/usr/bin/env python3
"""Analyze scraped supermarket JSON files for data quality issues.

Usage:
    python analyze_json.py                  # analyze all *.json product files
    python analyze_json.py spar.json        # analyze a specific file
    python analyze_json.py spar.json billa.json  # analyze multiple files
"""

import json
import sys
from collections import Counter
from pathlib import Path

# JSON files that are NOT product data — skip them automatically.
SKIP_FILES = {"firebase-key.json", "package.json", "package-lock.json", "spar_errors.json"}

REQUIRED_FIELDS = ["id", "name", "price", "category", "supermarket"]


def analyze(filepath: str) -> dict:
    """Analyze a single JSON product file and return a summary dict."""
    with open(filepath, "r", encoding="utf-8") as f:
        data = json.load(f)

    if not isinstance(data, list):
        return {"file": filepath, "error": "Root element is not a list"}

    total = len(data)
    if total == 0:
        return {"file": filepath, "error": "File contains 0 products"}

    issues = {}

    # ── Missing required fields ──────────────────────────────────────────
    for field in REQUIRED_FIELDS:
        bad = [i for i, p in enumerate(data)
               if p.get(field) is None or (isinstance(p.get(field), str) and p[field].strip() == "")]
        if bad:
            issues[f"missing_{field}"] = {
                "count": len(bad),
                "examples": [
                    {k: data[i].get(k) for k in ("id", "name", "price", "category")}
                    for i in bad[:5]
                ],
            }

    # ── Null / zero / negative prices ────────────────────────────────────
    null_prices = [i for i, p in enumerate(data) if p.get("price") is None]
    zero_prices = [i for i, p in enumerate(data) if p.get("price") == 0]
    neg_prices = [i for i, p in enumerate(data)
                  if isinstance(p.get("price"), (int, float)) and p["price"] < 0]
    non_numeric = [i for i, p in enumerate(data)
                   if p.get("price") is not None and not isinstance(p["price"], (int, float))]
    for label, lst in [("null_price", null_prices), ("zero_price", zero_prices),
                       ("negative_price", neg_prices), ("non_numeric_price", non_numeric)]:
        if lst:
            issues[label] = {
                "count": len(lst),
                "examples": [
                    {"id": data[i].get("id"), "name": data[i].get("name"), "price": data[i].get("price")}
                    for i in lst[:5]
                ],
            }

    # ── Duplicate IDs ────────────────────────────────────────────────────
    id_counts = Counter(p.get("id") for p in data)
    dupes = {k: v for k, v in id_counts.items() if v > 1}
    if dupes:
        issues["duplicate_ids"] = {
            "unique_ids_with_dupes": len(dupes),
            "total_duplicate_entries": sum(dupes.values()),
            "examples": {k: v for k, v in list(dupes.items())[:10]},
        }

    # ── Exact duplicate entries ──────────────────────────────────────────
    seen = set()
    exact_dupes = 0
    for p in data:
        key = json.dumps(p, sort_keys=True)
        if key in seen:
            exact_dupes += 1
        seen.add(key)
    if exact_dupes:
        issues["exact_duplicate_entries"] = {"count": exact_dupes}

    # ── Price > originalPrice (inconsistent discount) ────────────────────
    bad_discount = [i for i, p in enumerate(data)
                    if isinstance(p.get("price"), (int, float))
                    and isinstance(p.get("originalPrice"), (int, float))
                    and p["price"] > p["originalPrice"]]
    if bad_discount:
        issues["price_greater_than_original"] = {
            "count": len(bad_discount),
            "examples": [
                {"id": data[i].get("id"), "price": data[i]["price"],
                 "originalPrice": data[i]["originalPrice"]}
                for i in bad_discount[:5]
            ],
        }

    # ── inPromotion=True but no originalPrice ────────────────────────────
    promo_no_orig = [i for i, p in enumerate(data)
                     if p.get("inPromotion") and p.get("originalPrice") is None]
    if promo_no_orig:
        issues["promotion_without_original_price"] = {
            "count": len(promo_no_orig),
            "examples": [
                {"id": data[i].get("id"), "name": data[i].get("name"),
                 "price": data[i].get("price")}
                for i in promo_no_orig[:5]
            ],
        }

    # ── originalPrice set but inPromotion=False ──────────────────────────
    orig_no_promo = [i for i, p in enumerate(data)
                     if isinstance(p.get("originalPrice"), (int, float))
                     and not p.get("inPromotion")]
    if orig_no_promo:
        issues["original_price_without_promotion"] = {
            "count": len(orig_no_promo),
            "examples": [
                {"id": data[i].get("id"), "price": data[i].get("price"),
                 "originalPrice": data[i].get("originalPrice")}
                for i in orig_no_promo[:5]
            ],
        }

    # ── Missing optional but important fields ────────────────────────────
    for field in ("sku", "amount", "imageUrl", "brand"):
        missing = [i for i, p in enumerate(data)
                   if p.get(field) is None or (isinstance(p.get(field), str) and p[field].strip() == "")]
        if missing:
            issues[f"missing_{field}"] = {
                "count": len(missing),
                "examples": [
                    {"id": data[i].get("id"), "name": data[i].get("name")}
                    for i in missing[:3]
                ],
            }

    # ── Suspiciously high prices (>500) ──────────────────────────────────
    high = [i for i, p in enumerate(data)
            if isinstance(p.get("price"), (int, float)) and p["price"] > 500]
    if high:
        issues["price_above_500"] = {
            "count": len(high),
            "examples": [
                {"id": data[i].get("id"), "name": data[i].get("name"),
                 "price": data[i]["price"]}
                for i in high[:5]
            ],
        }

    # ── Price statistics ─────────────────────────────────────────────────
    prices = [p["price"] for p in data if isinstance(p.get("price"), (int, float))]
    stats = {}
    if prices:
        sorted_p = sorted(prices)
        stats = {
            "min": sorted_p[0],
            "max": sorted_p[-1],
            "avg": round(sum(prices) / len(prices), 2),
            "median": sorted_p[len(prices) // 2],
        }

    return {
        "file": filepath,
        "total_products": total,
        "keys": list(data[0].keys()) if data else [],
        "issues_found": len(issues),
        "issues": issues,
        "price_stats": stats,
    }


def print_report(result: dict):
    """Pretty-print the analysis result."""
    sep = "=" * 60
    print(f"\n{sep}")
    print(f"  FILE: {result['file']}")
    print(sep)

    if "error" in result:
        print(f"  ERROR: {result['error']}")
        return

    print(f"  Total products : {result['total_products']}")
    print(f"  Fields         : {', '.join(result['keys'])}")

    stats = result.get("price_stats", {})
    if stats:
        print(f"  Price range    : {stats['min']} – {stats['max']} EUR")
        print(f"  Price avg      : {stats['avg']} EUR  |  median: {stats['median']} EUR")

    issues = result.get("issues", {})
    if not issues:
        print(f"\n  ✅  No issues found!")
        return

    print(f"\n  ⚠️   {result['issues_found']} issue type(s) found:\n")

    for key, detail in issues.items():
        count = detail.get("count", detail.get("unique_ids_with_dupes", "?"))
        label = key.replace("_", " ").title()
        print(f"  [{count:>5}]  {label}")

        # Print examples
        examples = detail.get("examples", {})
        if isinstance(examples, list):
            for ex in examples:
                parts = [f"{k}={v}" for k, v in ex.items()]
                print(f"           └─ {', '.join(parts)}")
        elif isinstance(examples, dict):
            for k, v in list(examples.items())[:5]:
                print(f"           └─ {k} × {v}")

    print()


def main():
    files = sys.argv[1:]
    if not files:
        # Auto-discover product JSON files in current directory
        files = sorted(
            str(p) for p in Path(".").glob("*.json")
            if p.name not in SKIP_FILES
        )
        if not files:
            print("No JSON files found in current directory.")
            sys.exit(1)
        print(f"Auto-discovered {len(files)} JSON file(s): {', '.join(files)}")

    for filepath in files:
        try:
            result = analyze(filepath)
            print_report(result)
        except json.JSONDecodeError as e:
            print(f"\n  ERROR: {filepath} is not valid JSON: {e}")
        except Exception as e:
            print(f"\n  ERROR analyzing {filepath}: {e}")


if __name__ == "__main__":
    main()
