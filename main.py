import json
import time
from scrapers.billa import scrape_billa
from scrapers.spar import scrape_spar
from scrapers.hofer import scrape_hofer


def main():
    start_time = time.time()

    print("Starting Billa scraper...")
    #scrape_billa()
    print()

    print("Starting Spar scraper...")
    scrape_spar()
    print()

    print("Starting Hofer scraper...")
    #scrape_hofer()
    print()

    elapsed = time.time() - start_time
    if elapsed < 60:
        print(f"Finished in {elapsed:.1f} seconds")
    else:
        minutes = elapsed / 60
        print(f"Finished in {minutes:.1f} minutes")


if __name__ == "__main__":
    main()
