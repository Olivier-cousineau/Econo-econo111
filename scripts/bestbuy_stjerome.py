import json
import os
from datetime import datetime

import requests


STORE_ID = "935"  # Saint-Jérôme
OUTPUT_PATH = "data/bestbuy_stjerome.json"


def fetch_bestbuy_canada():
    """Scrape la section liquidation du Best Buy Saint-Jérôme"""
    page = 1
    products = []

    while True:
        url = (
            "https://www.bestbuy.ca/api/v2/json/search?query=liquidation"
            f"&storeId={STORE_ID}&lang=fr-CA&page={page}"
        )
        headers = {"User-Agent": "Mozilla/5.0"}
        r = requests.get(url, headers=headers, timeout=30)

        if r.status_code != 200:
            print(f"❌ HTTP {r.status_code} sur la page {page}")
            break

        data = r.json()
        items = data.get("products", [])
        if not items:
            break

        for item in items:
            products.append(
                {
                    "product_name": item.get("name"),
                    "sku": str(item.get("sku")),
                    "regular_price": item.get("regularPrice"),
                    "sale_price": item.get("salePrice"),
                    "image": item.get("thumbnailImage"),
                    "product_link": f"https://www.bestbuy.ca/fr-ca/produit/{item.get('sku')}",
                    "availability": item.get("availability", "Inconnu"),
                    "store": "Best Buy Saint-Jérôme",
                }
            )

        print(f"✅ Page {page} : {len(items)} produits")
        if not data.get("totalPages") or page >= data.get("totalPages"):
            break
        page += 1

    print(f"🔹 Total produits extraits : {len(products)}")
    return products


def save_json(products):
    """Sauvegarde les produits dans le bon fichier"""
    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(products, f, indent=2, ensure_ascii=False)
    print(f"💾 Sauvegardé dans {OUTPUT_PATH}")


def main():
    print("🔍 Scraping Best Buy Saint-Jérôme...")
    products = fetch_bestbuy_canada()
    save_json(products)
    print("🏁 Terminé à", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))


if __name__ == "__main__":
    main()
