import urllib.parse
import requests
from bs4 import BeautifulSoup

API_TOKEN = "79806d0a26a2413fb4a1c33f14dda9743940a7548ba"
TARGET_URL = "https://www.canadiantire.ca/fr/promotions/liquidation.html"

def fetch_html(url: str, token: str) -> str:
    """Fetch the rendered HTML for ``url`` through scrape.do."""
    api_url = f"https://api.scrape.do/?token={token}&url={urllib.parse.quote_plus(url)}"
    response = requests.get(api_url, timeout=60)
    response.raise_for_status()
    return response.text

def parse_liquidations(html: str) -> list[dict[str, float | str]]:
    """Parse liquidation cards from the provided HTML."""
    soup = BeautifulSoup(html, "html.parser")
    products: list[dict[str, float | str]] = []

    for card in soup.select("div.product-card"):
        title_el = card.select_one("a.product-title-link")
        price_sale_el = card.select_one("span.price-sale")
        price_regular_el = card.select_one("span.price-regular")

        if not (title_el and price_sale_el and price_regular_el):
            continue

        title = title_el.text.strip()

        try:
            price_sale = float(price_sale_el.text.strip().replace("$", "").replace(",", ""))
            price_regular = float(price_regular_el.text.strip().replace("$", "").replace(",", ""))
        except ValueError:
            continue

        if price_regular <= 0:
            continue

        discount = 1 - (price_sale / price_regular)

        if discount >= 0.60:
            products.append(
                {
                    "title": title,
                    "price_sale": price_sale,
                    "price_regular": price_regular,
                    "discount_percent": round(discount * 100, 1),
                }
            )

    return products

def main() -> None:
    html = fetch_html(TARGET_URL, API_TOKEN)
    liquidations = parse_liquidations(html)

    for item in liquidations:
        print(
            f"{item['title']} - Prix soldé : {item['price_sale']}$ "
            f"(rabais {item['discount_percent']}%)"
        )

if __name__ == "__main__":
    main()
