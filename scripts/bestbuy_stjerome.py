import json
import os
from datetime import datetime

import requests

OUTPUT_PATH = "data/bestbuy_liquidation.json"
STORE_ID = "935"  # Saint-Jérôme


def fetch_bestbuy_canada():
    url = (
        "https://www.bestbuy.ca/api/v2/json/search?"
        f"query=liquidation&storeId={STORE_ID}&lang=fr-CA"
    )
    response = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=30)
    if response.status_code != 200:
        print(f"❌ HTTP {response.status_code}")
        return []

    data = response.json()
    products = []

    for item in data.get("products", []):
        products.append(
            {
                "product_name": item.get("name"),
                "sku": item.get("sku"),
                "regular_price": item.get("regularPrice"),
                "sale_price": item.get("salePrice"),
                "image": item.get("thumbnailImage"),
                "product_link": f"https://www.bestbuy.ca/fr-ca/produit/{item.get('sku')}",
                "availability": item.get("availability", "Inconnu"),
                "store": "Best Buy Saint-Jérôme",
            }
        )

    print(f"✅ {len(products)} produits extraits")
    return products


def save_json(products):
    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(products, f, indent=2, ensure_ascii=False)
    print(f"💾 Sauvegardé dans {OUTPUT_PATH}")


def main():
    print("🔍 Scraping Best Buy Saint-Jérôme (Canada)...")
    products = fetch_bestbuy_canada()
    save_json(products)
    print("🏁 Terminé à", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))


if __name__ == "__main__":
    main()
