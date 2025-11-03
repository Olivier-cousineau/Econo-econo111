import json
import os
from datetime import datetime
from typing import List, Dict, Any

import requests

# --- Configuration ---
STORE_ID = "62"  # 🏬 ID du magasin Best Buy Anjou
OUTPUT_PATH = "data/bestbuy_anjou.json"


def fetch_bestbuy_canada() -> List[Dict[str, Any]]:
    """Scrape la section liquidation du Best Buy Anjou."""
    page = 1
    products: List[Dict[str, Any]] = []

    while True:
        url = (
            "https://www.bestbuy.ca/api/v2/json/search?query=liquidation"
            f"&storeId={STORE_ID}&lang=fr-CA&page={page}"
        )
        headers = {"User-Agent": "Mozilla/5.0"}
        response = requests.get(url, headers=headers, timeout=30)

        if response.status_code != 200:
            print(f"❌ HTTP {response.status_code} sur la page {page}")
            break

        data = response.json()
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
                    "store": "Best Buy Anjou",
                }
            )

        print(f"✅ Page {page} : {len(items)} produits")
        total_pages = data.get("totalPages")
        if not total_pages or page >= total_pages:
            break
        page += 1

    print(f"🔹 Total produits extraits : {len(products)}")
    return products


def save_json(products: List[Dict[str, Any]]) -> None:
    """Sauvegarde les produits dans le bon fichier."""
    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as file:
        json.dump(products, file, indent=2, ensure_ascii=False)
    print(f"💾 Sauvegardé dans {OUTPUT_PATH}")


def main() -> None:
    print("🔍 Scraping Best Buy Anjou...")
    products = fetch_bestbuy_canada()
    save_json(products)
    print("🏁 Terminé à", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))


if __name__ == "__main__":
    main()
