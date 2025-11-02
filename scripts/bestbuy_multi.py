import json
import os
import time
from typing import Dict, List

import requests

API_URL = "https://api.bestbuy.com/v1/products((categoryPath.id=abcat0100000))"
API_KEY = os.getenv("BESTBUY_API_KEY")

STORES: Dict[str, str] = {
    "anjou": "917",
    "brossard": "931",
    "laval": "934",
    "chomedey": "933",
    "drummondville": "924",
    "gatineau": "925",
    "granby": "926",
    "joliette": "927",
    "longueuil": "928",
    "mascouche": "929",
    "montreal": "930",
    "pointe-claire": "936",
    "quebec": "937",
    "repentigny": "938",
    "rosemere": "939",
    "saint-eustache": "940",
    "saint-hyacinthe": "941",
    "saint-jean-sur-richelieu": "942",
    "saint-jerome": "935",
}


def fetch_products(store_id: str) -> List[Dict[str, object]]:
    url = f"{API_URL}&storeId={store_id}&format=json&apiKey={API_KEY}"
    response = requests.get(url, timeout=30)
    response.raise_for_status()
    data = response.json()
    products: List[Dict[str, object]] = []

    for product in data.get("products", []):
        regular_price = product.get("regularPrice")
        sale_price = product.get("salePrice")
        if regular_price and sale_price and sale_price < regular_price:
            products.append(
                {
                    "name": product.get("name"),
                    "regularPrice": regular_price,
                    "salePrice": sale_price,
                    "sku": str(product.get("sku")),
                    "url": f"https://www.bestbuy.ca/en-ca/product/{product.get('sku')}",
                    "image": product.get("image"),
                    "storeId": store_id,
                }
            )

    return products


def main() -> None:
    os.makedirs("data", exist_ok=True)

    for city, store_id in STORES.items():
        print(f"🏬 Scraping Best Buy {city.title()} ({store_id}) ...")
        try:
            products = fetch_products(store_id)
            output_path = f"data/bestbuy_{city}.json"
            with open(output_path, "w", encoding="utf-8") as file:
                json.dump(products, file, indent=2, ensure_ascii=False)
            print(f"✅ {len(products)} produits sauvegardés dans {output_path}")
        except Exception as error:  # pragma: no cover - logging purposes only
            print(f"❌ Erreur {city}: {error}")
        time.sleep(2)


if __name__ == "__main__":
    main()
