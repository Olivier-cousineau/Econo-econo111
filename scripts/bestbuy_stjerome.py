import os
import json
import requests
from datetime import datetime

API_KEY = os.getenv("BESTBUY_API_KEY")
STORE_ID = "935"  # Best Buy Saint-Jérôme
OUTPUT_PATH = "data/bestbuy_liquidation.json"

def fetch_bestbuy_stjerome():
    all_products = []
    page = 1

    while True:
        url = (
            f"https://api.bestbuy.com/v1/products(onSale=true&storeId={STORE_ID})"
            f"?apiKey={API_KEY}&format=json&pageSize=100&page={page}"
        )
        r = requests.get(url, timeout=30)
        if r.status_code != 200:
            print(f"❌ HTTP Error {r.status_code} on page {page}")
            break

        data = r.json()
        products = data.get("products", [])
        if not products:
            break

        for p in products:
            all_products.append({
                "product_name": p.get("name"),
                "sku": str(p.get("sku")),
                "regular_price": p.get("regularPrice"),
                "sale_price": p.get("salePrice"),
                "image": p.get("image"),
                "product_link": f"https://www.bestbuy.ca/en-ca/product/{p.get('sku')}",
                "availability": p.get("inStoreAvailabilityText", "Unknown"),
                "store": "Best Buy Saint-Jérôme"
            })

        print(f"Fetched page {page} → {len(products)} produits")
        if page >= data.get("totalPages", 1):
            break
        page += 1

    return all_products


def save_to_json(data):
    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    print(f"✅ {len(data)} produits enregistrés dans {OUTPUT_PATH}")


def main():
    print("🔍 Scraping Best Buy Saint-Jérôme...")
    products = fetch_bestbuy_stjerome()
    save_to_json(products)
    print("🏁 Terminé à", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))


if __name__ == "__main__":
    main()
