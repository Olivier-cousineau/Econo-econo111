from __future__ import annotations

import argparse
import os
import random
import urllib.parse
from typing import Iterable, Sequence

import requests
from bs4 import BeautifulSoup

API_TOKEN = "79806d0a26a2413fb4a1c33f14dda9743940a7548ba"
TARGET_URL = "https://www.canadiantire.ca/fr/promotions/liquidation.html"

DEFAULT_PROXY_ADDRESSES = [
    "142.111.48.253:7830",
    "31.59.20.176:6754",
]
DEFAULT_PROXY_USERNAME = "rzjohgsg"
DEFAULT_PROXY_PASSWORD = "55keyvw66umr"

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/119.0.0.0 Safari/537.36"
)
def _build_proxy_rotation(
    addresses: Iterable[str] | None,
    username: str | None,
    password: str | None,
) -> list[dict[str, str]]:
    """Create a list of requests-compatible proxy dictionaries."""

    if not addresses or not username or not password:
        return []

    proxies: list[dict[str, str]] = []
    for address in addresses:
        address = address.strip()
        if not address:
            continue
        proxies.append(
            {
                "http": f"http://{username}:{password}@{address}",
                "https": f"http://{username}:{password}@{address}",
            }
        )
    return proxies


def _request_with_proxy(url: str, proxies: Sequence[dict[str, str]]) -> str | None:
    """Attempt to download ``url`` using the configured proxies."""

    if not proxies:
        return None

    # shuffle to avoid hammering the same endpoint every run
    for proxy in random.sample(list(proxies), k=len(proxies)):
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


def fetch_html(url: str, token: str | None, proxies: Sequence[dict[str, str]]) -> str:
    """Fetch the rendered HTML for ``url`` using a proxy and fall back to scrape.do."""

    html = _request_with_proxy(url, proxies)
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

def _format_liquidation(item: dict[str, float | str], language: str) -> str:
    """Return a user-friendly string describing the liquidation item."""

    if language == "en":
        return (
            f"{item['title']} - Sale price: ${item['price_sale']:.2f} "
            f"(discount {item['discount_percent']}%)"
        )

    return (
        f"{item['title']} - Prix soldé : {item['price_sale']:.2f}$ "
        f"(rabais {item['discount_percent']}%)"
    )


def _parse_addresses(addresses: Sequence[str] | None) -> list[str] | None:
    if not addresses:
        return None
    parsed: list[str] = []
    for entry in addresses:
        parts = [chunk.strip() for chunk in entry.split(",") if chunk.strip()]
        parsed.extend(parts)
    return parsed or None


def main() -> None:
    parser = argparse.ArgumentParser(description="Scrape Canadian Tire liquidation deals")
    parser.add_argument(
        "--url",
        default=TARGET_URL,
        help="Page promotions à analyser (défaut: %(default)s)",
    )
    parser.add_argument(
        "--token",
        default=None,
        help="Jeton scrape.do à utiliser en secours (défaut: variable d'environnement ou valeur intégrée).",
    )
    parser.add_argument(
        "--language",
        choices=("fr", "en"),
        default="fr",
        help="Langue de sortie pour les messages (fr ou en).",
    )
    parser.add_argument(
        "--proxies",
        nargs="*",
        help="Liste d'adresses proxy (host:port). Accepte les valeurs séparées par des espaces ou des virgules.",
    )
    parser.add_argument(
        "--proxy-username",
        default=None,
        help="Nom d'utilisateur pour les proxys protégés.",
    )
    parser.add_argument(
        "--proxy-password",
        default=None,
        help="Mot de passe pour les proxys protégés.",
    )

    args = parser.parse_args()

    token = (
        args.token
        or os.environ.get("SCRAPE_DO_TOKEN")
        or os.environ.get("SCRAPEDO_TOKEN")
        or API_TOKEN
    )

    addresses = _parse_addresses(args.proxies)
    if addresses is None:
        addresses_env = os.environ.get("CANADIANTIRE_PROXIES")
        if addresses_env:
            addresses = _parse_addresses([addresses_env])
        else:
            addresses = list(DEFAULT_PROXY_ADDRESSES)

    proxy_username = (
        args.proxy_username
        or os.environ.get("CANADIANTIRE_PROXY_USERNAME")
        or DEFAULT_PROXY_USERNAME
    )
    proxy_password = (
        args.proxy_password
        or os.environ.get("CANADIANTIRE_PROXY_PASSWORD")
        or DEFAULT_PROXY_PASSWORD
    )

    proxies = _build_proxy_rotation(addresses, proxy_username, proxy_password)

    html = fetch_html(args.url, token, proxies)
    liquidations = parse_liquidations(html)

    if not liquidations:
        message = (
            "Aucun rabais de 60 % ou plus trouvé sur la page."
            if args.language == "fr"
            else "No deals with at least 60% off were found on the page."
        )
        print(message)
        return

    for item in liquidations:
        print(_format_liquidation(item, args.language))


if __name__ == "__main__":
    main()
