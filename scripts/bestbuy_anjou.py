import os
import json
import requests

STORE_ID = "917"  # ID du magasin Anjou
API_KEY = os.getenv("BESTBUY_API_KEY")
OUTPUT_FILE = "data/bestbuy_anjou.json"

if not API_KEY:
    raise SystemExit("❌ La variable d'environnement BESTBUY_API_KEY est manquante.")

URL = f"https://api.bestbuy.com/v1/products((categoryPath.id=abcat0100000))&storeId={STORE_ID}&format=json&apiKey={API_KEY}"

print(f"🛒 Scraping Best Buy Anjou (store {STORE_ID})...")

try:
    response = requests.get(URL, timeout=30)
    response.raise_for_status()
    data = response.json()

    products = [
        {
            "name": p.get("name"),
            "sku": p.get("sku"),
            "regularPrice": p.get("regularPrice"),
            "salePrice": p.get("salePrice"),
            "url": p.get("url"),
        }
        for p in data.get("products", [])
    ]

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(products, f, indent=2, ensure_ascii=False)

    print(f"✅ {len(products)} produits enregistrés dans {OUTPUT_FILE}")

except requests.exceptions.RequestException as e:
    print(f"❌ Erreur lors du scraping Best Buy Anjou : {e}")
