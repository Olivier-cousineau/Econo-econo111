import json
import logging
from pathlib import Path

import requests
from bs4 import BeautifulSoup

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

CLEARANCE_URL = "https://www.bestbuy.ca/en-ca/collection/clearance-products/113065"
OUTPUT_FILE = Path("data/best-buy/liquidations/clearance.json")

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
    ),
    "Accept-Language": "en-CA,en;q=0.9,fr;q=0.8",
}


def fetch_html(url: str) -> str:
    """Télécharge le HTML brut de la page Best Buy Clearance."""
    logging.info("Fetching: %s", url)
    response = requests.get(url, headers=HEADERS, timeout=30)
    response.raise_for_status()
    return response.text


def parse_clearance(html: str) -> list[dict]:
    """Analyse la page pour extraire les produits en liquidation."""
    soup = BeautifulSoup(html, "html.parser")
    products: list[dict] = []

    # Chaque produit se trouve dans un <li> avec class qui contient "productItem"
    for li in soup.find_all("li", class_=lambda c: c and "productItem" in c):
        try:
            name_el = li.find("h4")
            name = name_el.get_text(strip=True) if name_el else "Unknown Product"

            link_el = li.find("a", href=True)
            link = f"https://www.bestbuy.ca{link_el['href']}" if link_el else None

            image_el = li.find("img")
            image = image_el.get("src") if image_el else None

            price_el = li.select_one(".price_FHDfG span")
            price = price_el.get_text(strip=True) if price_el else "N/A"

            products.append(
                {
                    "product_name": name,
                    "price": price,
                    "product_link": link,
                    "image": image,
                    "store": "Best Buy Clearance (EN)",
                }
            )
        except Exception as exc:  # pragma: no cover - defensive logging
            logging.warning("Skipping one product: %s", exc)

    return products


def main() -> None:
    html = fetch_html(CLEARANCE_URL)
    products = parse_clearance(html)
    logging.info("✅ Extracted %d clearance items", len(products))

    if not products:
        raise SystemExit("❌ No products found. Site structure may have changed.")

    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT_FILE.open("w", encoding="utf-8") as fp:
        json.dump(products, fp, indent=2, ensure_ascii=False)

    logging.info("💾 Saved to %s", OUTPUT_FILE)


if __name__ == "__main__":
    main()
