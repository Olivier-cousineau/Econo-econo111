"""Scraper Canadian Tire via Scrape.do"""

import json
from datetime import datetime
from typing import Dict, List, Optional

import requests
from bs4 import BeautifulSoup

SCRAPE_DO_API_KEY = "79806d0a26a2413fb4a1c33f14dda9743940a7548ba"
TARGET_URL = "https://www.canadiantire.ca/fr/promotions/liquidation.html"
SCRAPE_DO_ENDPOINT = "https://api.scrape.do/"


def fetch_page_html() -> str:
    """Download the rendered Canadian Tire liquidation page through Scrape.do."""
    print("🕐 Téléchargement de la page Canadian Tire via Scrape.do...")
    try:
        response = requests.get(
            SCRAPE_DO_ENDPOINT,
            params={
                "url": TARGET_URL,
                "key": SCRAPE_DO_API_KEY,
                "country": "CA",
            },
            timeout=120,
        )
    except requests.RequestException as exc:
        raise SystemExit(f"❌ Erreur réseau Scrape.do : {exc}") from exc

    if response.status_code != 200:
        raise SystemExit(
            f"❌ Erreur Scrape.do ({response.status_code}) : {response.text[:200]}"
        )

    print("✅ Page reçue avec succès!")
    return response.text


def extract_products(html: str) -> List[Dict[str, Optional[str]]]:
    """Parse the liquidation page and return a list of product dictionaries."""
    soup = BeautifulSoup(html, "html.parser")
    items = soup.select(".product-tile, .product__list-item")

    products: List[Dict[str, Optional[str]]] = []
    for item in items:
        name = item.select_one(".product__title, .product-tile__title")
        image = item.select_one("img")
        original_price = item.select_one(".price__was, .price-was")
        sale_price = item.select_one(".price__sale, .price-sale")
        link = item.select_one("a")

        data = {
            "product_name": name.get_text(strip=True) if name else None,
            "original_price": original_price.get_text(strip=True)
            if original_price
            else None,
            "discount_price": sale_price.get_text(strip=True) if sale_price else None,
            "image_url": image["src"] if image and image.has_attr("src") else None,
            "product_link": f"https://www.canadiantire.ca{link['href']}"
            if link and link.has_attr("href")
            else None,
            "availability": "En stock" if "En stock" in item.get_text() else "Non précisé",
        }

        if data["product_name"]:
            products.append(data)

    return products


def save_products(products: List[Dict[str, Optional[str]]]) -> str:
    """Persist the scraped products list into the data directory with a timestamp."""
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M")
    output_file = f"data/canadian_tire_liquidation_{timestamp}.json"

    with open(output_file, "w", encoding="utf-8") as handle:
        json.dump(products, handle, indent=2, ensure_ascii=False)

    return output_file


def main() -> None:
    html = fetch_page_html()

    with open("debug_canadiantire.html", "w", encoding="utf-8") as debug_file:
        debug_file.write(html)

    products = extract_products(html)
    print(f"🧾 {len(products)} produits trouvés.")

    output_path = save_products(products)
    print(f"✅ Données sauvegardées dans {output_path}")


if __name__ == "__main__":
    main()
