import json
import time
from scrapers.billa import scrape_billa


def main():
    start_time = time.time()
    print("Starting Billa scraper...")

    results = scrape_billa()

    all_products = []
    total = 0

    for category, products in results.items():
        count = len(products)
        total += count
        all_products.extend(products)
        print(f"{category}: {count} products")

    print(f"\nTotal: {total} products")

    with open("output.json", "w", encoding="utf-8") as f:
        json.dump(all_products, f, ensure_ascii=False, indent=2)
    print(f"Saved {len(all_products)} products to output.json")

    elapsed = time.time() - start_time
    if elapsed < 60:
        print(f"\nFinished in {elapsed:.1f} seconds")
    else:
        minutes = elapsed / 60
        print(f"\nFinished in {minutes:.1f} minutes")


if __name__ == "__main__":
    main()
