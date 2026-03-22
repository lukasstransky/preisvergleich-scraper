import json
import time
from scrapers.billa import scrape_billa


def main():
    start_time = time.time()
    print("Starting Billa scraper...")

    results = scrape_billa()

    total = 0
    example = None

    for category, products in results.items():
        count = len(products)
        total += count
        print(f"{category}: {count} products")
        if example is None and products:
            example = products[0]

    print(f"\nTotal: {total} products")

    if example:
        print("\nExample product:")
        print(json.dumps(example, indent=2, ensure_ascii=False))

    elapsed = time.time() - start_time
    if elapsed < 60:
        print(f"\nFinished in {elapsed:.1f} seconds")
    else:
        minutes = elapsed / 60
        print(f"\nFinished in {minutes:.1f} minutes")


if __name__ == "__main__":
    main()
