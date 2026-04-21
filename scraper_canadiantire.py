from __future__ import annotations

import argparse
import os
import sys
import urllib.parse
from typing import Iterable

import requests
from bs4 import BeautifulSoup


DEFAULT_TARGET_URL = "https://www.canadiantire.ca/fr/promotions/liquidation.html"
TOKEN_ENV_VAR = "SCRAPE_DO_TOKEN"


class ScraperError(RuntimeError):
    """Raised when the scraper cannot complete successfully."""


def fetch_html(url: str, token: str) -> str:
    """Fetch the rendered HTML for ``url`` through scrape.do."""
    if not token:
        raise ScraperError(
            "A scrape.do API token is required. Provide it with the --token option "
            f"or by exporting the {TOKEN_ENV_VAR} environment variable."
        )

    api_url = (
        "https://api.scrape.do/?token="
        f"{urllib.parse.quote_plus(token)}&url={urllib.parse.quote_plus(url)}"
    )

    try:
        response = requests.get(api_url, timeout=60)
        response.raise_for_status()
    except requests.RequestException as exc:  # pragma: no cover - network failure
        raise ScraperError(f"Unable to fetch liquidation page: {exc}") from exc

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
                    "discount_percent": discount * 100,
                }
            )

    return products

def iter_discount_messages(liquidations: Iterable[dict[str, float | str]]) -> Iterable[str]:
    """Yield printable strings describing each liquidation product."""

    for item in liquidations:
        yield (
            f"{item['title']} - Prix soldé : {item['price_sale']}$ "
            f"(rabais {item['discount_percent']:.1f}%)"
        )


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Scrape Canadian Tire liquidations with a minimum discount threshold.",
    )
    parser.add_argument(
        "--token",
        default=os.environ.get(TOKEN_ENV_VAR),
        help=(
            "scrape.do API token. If not provided, the value is read from the "
            f"{TOKEN_ENV_VAR} environment variable."
        ),
    )
    parser.add_argument(
        "--url",
        default=DEFAULT_TARGET_URL,
        help="Canadian Tire liquidation page URL to scrape.",
    )
    parser.add_argument(
        "--min-discount",
        type=float,
        default=60.0,
        help="Minimum discount percentage to report (default: 60).",
    )
    return parser


def main(argv: Iterable[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)

    try:
        html = fetch_html(args.url, args.token)
        liquidations = parse_liquidations(html)
    except ScraperError as exc:
        parser.error(str(exc))

    filtered = [
        item for item in liquidations if item["discount_percent"] >= args.min_discount
    ]

    if not filtered:
        print("Aucun produit en liquidation avec le rabais demandé.")
        return 0

    for message in iter_discount_messages(filtered):
        print(message)

    return 0


if __name__ == "__main__":
    sys.exit(main())
