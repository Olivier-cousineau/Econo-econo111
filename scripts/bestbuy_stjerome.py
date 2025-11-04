import json
import os
from datetime import datetime
from typing import List, Dict, Any
import requests

# --- Configuration ---
STORE_ID = "935"  # 🏬 Saint-Jérôme
OUTPUT_PATH = "data/best-buy/st-jerome.json"  # ✅ format compatible avec ton site

def fetch_bestbuy_canada() -> List[Dict[str, Any]]:
    """Scrape toutes les pages de la section liquidation du Best Buy Saint-Jérôme."""
    page = 1
    products: List[Dict[str, Any]] = []

    print(f"🔍 Scraping Best Buy Saint-Jérôme (storeId={STORE_ID})...")

    while True:
        # API Best Buy (recherche par mot-clé 'liquidation')
        url = (
            "https://www.bestbuy.ca/api/v2/json/search"
            f"?query=liquidation&storeId={STORE_ID}&lang=fr-CA&page={page}"
        )
        headers = {"User-Agent": "Mozilla/5.0"}
        response = requests.get(url, headers=headers, timeout=30)

        if response.status_code != 200:
            print(f"❌ HTTP {response.status_code} sur la page {page}")
            break

        data = response.json()
        items = data.get("products", [])
        if not items:
            print("🚫 Plus de pages à scraper.")
            break

        for item in items:
            # Nettoyage et uniformisation des données
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

        total_pages = data.get("totalPages", 1)
        print(f"✅ Page {page}/{total_pages} → {len(items)} produits")

        if page >= total_pages:
            print("🏁 Toutes les pages ont été traitées.")
            break

        page += 1

    print(f"🔹 Total produits extraits : {len(products)}")
    return products


def save_json(products: List[Dict[str, Any]]) -> None:
    """Sauvegarde les produits dans le bon répertoire pour le site."""
    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as file:
        json.dump(products, file, indent=2, ensure_ascii=False)
    print(f"💾 Fichier sauvegardé : {OUTPUT_PATH}")


def main() -> None:
    products = fetch_bestbuy_canada()
    save_json(products)
    print("🕒 Terminé à", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))


if __name__ == "__main__":
    main()
