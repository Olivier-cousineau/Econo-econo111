import json
import logging
from time import sleep

import requests

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

OUTPUT_FILE = "data/best-buy/liquidations/clearance.json"
API_URL = "https://www.bestbuy.ca/api/v2/json/search"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
    ),
    "Accept-Language": "en-CA,en;q=0.9,fr;q=0.8",
}


def fetch_clearance_products() -> list[dict]:
    """Retrieve all clearance products through the public Best Buy API."""
    products: list[dict] = []
    page = 1

    while True:
        params = {
            "query": "clearance",
            "page": page,
            "lang": "en-CA",
            "sortBy": "salePrice",
            "sortDir": "asc",
        }

        logging.info("Fetching page %d ...", page)
        response = requests.get(API_URL, headers=HEADERS, params=params, timeout=30)
        if response.status_code != 200:
            logging.error("HTTP %s on page %d", response.status_code, page)
            break

        data = response.json()
        items = data.get("products", [])
        if not items:
            logging.info("No more products.")
            break

        for product in items:
            products.append(
                {
                    "product_name": product.get("name"),
                    "sku": str(product.get("sku")),
                    "regular_price": product.get("regularPrice"),
                    "sale_price": product.get("salePrice"),
                    "product_link": f"https://www.bestbuy.ca/en-ca/product/{product.get('sku')}",
                    "image": product.get("thumbnailImage"),
                    "store": "Best Buy Canada",
                    "availability": product.get("availability"),
                }
            )

        logging.info("✅ Collected %d products from page %d", len(items), page)
        page += 1
        sleep(0.8)  # avoid hammering the API

    logging.info("🔹 Total collected: %d products", len(products))
    return products


def main() -> None:
    products = fetch_clearance_products()

    if not products:
        raise SystemExit("❌ No clearance products found.")

    with open(OUTPUT_FILE, "w", encoding="utf-8") as fp:
        json.dump(products, fp, indent=2, ensure_ascii=False)

    logging.info("💾 Saved %d items to %s", len(products), OUTPUT_FILE)


if __name__ == "__main__":
    main()
