import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests

# --- Configuration ---
STORE_ID = "935"  # 🏬 Saint-Jérôme
STORE_NAME = "best-buy"
CITY = "st-jerome"
OUTPUT_PATH = Path(f"data/{STORE_NAME}/{CITY}.json")


PRICE_CLEAN_RE = re.compile(r"[^0-9.,-]+")


def parse_price(value: Any) -> Optional[float]:
    """Convertit une valeur de prix Best Buy en float."""

    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        cleaned = PRICE_CLEAN_RE.sub("", value)
        if not cleaned:
            return None
        if cleaned.count(",") == 1 and cleaned.count(".") == 0:
            cleaned = cleaned.replace(",", ".")
        else:
            cleaned = cleaned.replace(",", "")
        try:
            return float(cleaned)
        except ValueError:
            return None
    return None


def fetch_bestbuy_canada() -> List[Dict[str, Any]]:
    """Scrape toutes les pages de la section liquidation du Best Buy Saint-Jérôme."""
    page = 1
    products: List[Dict[str, Any]] = []

    print(f"🔍 Scraping Best Buy Saint-Jérôme (storeId={STORE_ID})...")

    while True:
        # URL API officielle pour la recherche
        url = (
            "https://www.bestbuy.ca/api/v2/json/search"
            f"?query=liquidation&storeId={STORE_ID}&lang=fr-CA&page={page}"
        )
        headers = {"User-Agent": "Mozilla/5.0"}
        response = requests.get(url, headers=headers, timeout=30)

        # Erreur HTTP
        if response.status_code != 200:
            print(f"❌ HTTP {response.status_code} sur la page {page}")
            break

        data = response.json()
        items = data.get("products", [])

        # Si aucune donnée → fin
        if not items:
            print("🚫 Plus de pages à scraper.")
            break

        # Ajoute tous les produits de la page
        for item in items:
            name = item.get("name") or item.get("title")
            raw_sku = item.get("sku")
            sku = str(raw_sku).strip() if raw_sku else ""
            if not name or not sku:
                continue

            regular_price = parse_price(
                item.get("regularPrice") or item.get("regular_price")
            )
            sale_price = parse_price(
                item.get("salePrice")
                or item.get("sale_price")
                or item.get("salePriceWithPromotions")
            )

            availability_raw = item.get("availability") or item.get(
                "availabilityStatus"
            )
            if isinstance(availability_raw, dict):
                availability = availability_raw.get("label") or availability_raw.get(
                    "value"
                )
            else:
                availability = availability_raw

            product = {
                "product_name": name,
                "sku": sku,
                "image": item.get("thumbnailImage"),
                "product_link": f"https://www.bestbuy.ca/fr-ca/produit/{sku}",
                "availability": availability or "Inconnu",
                "store": "Best Buy Saint-Jérôme",
            }

            if regular_price is not None:
                product["regular_price"] = regular_price
            if sale_price is not None:
                product["sale_price"] = sale_price

            products.append(product)

        total_pages = data.get("totalPages", 1)
        print(f"✅ Page {page}/{total_pages} → {len(items)} produits")

        # Si on est rendu à la dernière page, on arrête
        if page >= total_pages:
            print("🏁 Toutes les pages ont été traitées.")
            break

        page += 1

    print(f"🔹 Total produits extraits : {len(products)}")
    return products


def save_json(products: List[Dict[str, Any]]) -> None:
    """Sauvegarde les produits dans le fichier JSON."""
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT_PATH.open("w", encoding="utf-8") as file:
        json.dump(products, file, indent=2, ensure_ascii=False)
    print(f"💾 Sauvegardé dans {OUTPUT_PATH}")


def main() -> None:
    products = fetch_bestbuy_canada()
    save_json(products)
    print("🕒 Terminé à", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))


if __name__ == "__main__":
    main()
