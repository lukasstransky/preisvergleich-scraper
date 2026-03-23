import json
import time
from scrapers.billa import scrape_billa
from scrapers.spar import scrape_spar


def main():
    start_time = time.time()
    all_products = []

    # print("Starting Billa scraper...")
    # billa_results = scrape_billa()
    # billa_total = 0
    # for category, products in billa_results.items():
    #     count = len(products)
    #     billa_total += count
    #     all_products.extend(products)
    #     print(f"{category}: {count} products")
    # print(f"Billa total: {billa_total} products\n")

    print("Starting Spar scraper...")
    spar_products = scrape_spar()
    all_products.extend(spar_products)
    print(f"Spar total: {len(spar_products)} products\n")

    print(f"Combined total: {len(all_products)} products")

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
