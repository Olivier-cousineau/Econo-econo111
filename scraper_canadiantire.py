from __future__ import annotations

import os
import random
import urllib.parse
from typing import Iterable

import requests
from bs4 import BeautifulSoup

API_TOKEN = "79806d0a26a2413fb4a1c33f14dda9743940a7548ba"
TARGET_URL = "https://www.canadiantire.ca/fr/promotions/liquidation.html"

DEFAULT_PROXY_ADDRESSES = [
    "142.111.48.253:7030",
]
DEFAULT_PROXY_USERNAME = "rzjohgsg"
DEFAULT_PROXY_PASSWORD = "55keyvw66umr"

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/119.0.0.0 Safari/537.36"
)


def _build_proxy_rotation() -> list[dict[str, str]]:
    """Create a list of requests-compatible proxy dictionaries."""

    addresses_env = os.environ.get("CANADIANTIRE_PROXIES")
    if addresses_env:
        addresses: Iterable[str] = (
            entry.strip() for entry in addresses_env.split(",") if entry.strip()
        )
    else:
        addresses = DEFAULT_PROXY_ADDRESSES

    username = os.environ.get("CANADIANTIRE_PROXY_USERNAME", DEFAULT_PROXY_USERNAME)
    password = os.environ.get("CANADIANTIRE_PROXY_PASSWORD", DEFAULT_PROXY_PASSWORD)

    if not username or not password:
        return []

    proxies: list[dict[str, str]] = []
    for address in addresses:
        proxies.append(
            {
                "http": f"http://{username}:{password}@{address}",
                "https": f"http://{username}:{password}@{address}",
            }
        )
    return proxies


PROXIES = _build_proxy_rotation()


def _request_with_proxy(url: str) -> str | None:
    """Attempt to download ``url`` using the configured proxies."""

    if not PROXIES:
        return None

    # shuffle to avoid hammering the same endpoint every run
    for proxy in random.sample(PROXIES, k=len(PROXIES)):
        try:
            response = requests.get(
                url,
                timeout=60,
                proxies=proxy,
                headers={"User-Agent": USER_AGENT, "Accept-Language": "fr-CA,fr;q=0.9"},
            )
            response.raise_for_status()
            return response.text
        except requests.RequestException:
            continue
    return None


def fetch_html(url: str, token: str | None) -> str:
    """Fetch the rendered HTML for ``url`` using a proxy and fall back to scrape.do."""

    html = _request_with_proxy(url)
    if html is not None:
        return html

    if not token:
        raise RuntimeError("Unable to fetch page and no scrape.do token provided.")

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
    token = os.environ.get("SCRAPE_DO_TOKEN", API_TOKEN)
    html = fetch_html(TARGET_URL, token)
    liquidations = parse_liquidations(html)

    for item in liquidations:
        print(
            f"{item['title']} - Prix soldé : {item['price_sale']}$ "
            f"(rabais {item['discount_percent']}%)"
        )

if __name__ == "__main__":
    main()
