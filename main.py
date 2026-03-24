import json
import time
from scrapers.billa import scrape_billa
from scrapers.spar import scrape_spar
from scrapers.hofer import scrape_hofer
from scrapers.penny import scrape_penny
from firebase_store import upload_all


def main():
    start_time = time.time()

    print("Starting Billa scraper...")
    billa_products = scrape_billa()
    print()

    print("Starting Spar scraper...")
    #spar_products = scrape_spar()
    print()

    print("Starting Hofer scraper...")
    #hofer_products = scrape_hofer()
    print()

    print("Starting Penny scraper...")
    #penny_products = scrape_penny()
    print()

    # Upload to Firebase Firestore
    print("Uploading to Firebase...")
    upload_all({
        "billa": billa_products,
       # "spar": spar_products,
        #"hofer": hofer_products,
        #"penny": penny_products,
    })
    print()

    elapsed = time.time() - start_time
    if elapsed < 60:
        print(f"Finished in {elapsed:.1f} seconds")
    else:
        minutes = elapsed / 60
        print(f"Finished in {minutes:.1f} minutes")


if __name__ == "__main__":
    main()
