"""Scrape Sporting Life liquidation listings and refresh local datasets.

The script drives a headless Chromium browser via Playwright to load the
liquidation listing, follows the pagination controls, and extracts key fields
for every product. The collected data is stored in a CSV export as well as in
the JSON dataset consumed by the web application.

Usage
-----

    python sportinglife_liquidation_scraper.py

Optional arguments allow overriding the output locations or disabling the
polite delay between paginated requests. Run ``python
sportinglife_liquidation_scraper.py --help`` for the full list of options.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List
from urllib.parse import urljoin

from bs4 import BeautifulSoup
from bs4.element import Tag
from playwright.sync_api import Page
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright

BASE_URL = "https://www.sportinglife.ca/fr-CA/liquidation/"
DEFAULT_CSV_PATH = Path("sportinglife_liquidation_laval.csv")
DEFAULT_JSON_PATH = Path("data/sporting-life/laval.json")
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)
HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept-Language": "fr-CA,fr;q=0.9,en-CA;q=0.8,en;q=0.7",
}
SHOW_MORE_PATTERN = re.compile(
    r"(voir|afficher).{0,40}?(plus|autres|encore|articles|items)"
    r"|see\s+more|show\s+more|load\s+more|view\s+more|more\s+products",
    re.IGNORECASE | re.DOTALL,
)


def _parse_result_count(text: str) -> tuple[int, int] | tuple[int, None] | None:
    """Return the number of loaded and total items from a status string."""

    numbers = re.findall(r"\d[\d\s.,]*", text)
    if not numbers:
        return None

    def _to_int(raw: str) -> int:
        cleaned = re.sub(r"[^0-9]", "", raw)
        return int(cleaned) if cleaned else 0

    loaded = _to_int(numbers[0])
    total = _to_int(numbers[1]) if len(numbers) > 1 else None
    return loaded, total


def _read_loaded_total(page: Page) -> tuple[int, int] | tuple[int, None] | None:
    """Attempt to read the current "showing X of Y" indicator."""

    try:
        locator = page.locator(
            "div.search-result-count, span.search-result-count, #search-result-count"
        )
        if locator.count() == 0:
            return None
        text = locator.first.inner_text().strip()
    except PlaywrightTimeoutError:
        return None
    except Exception:
        return None

    return _parse_result_count(text)


@dataclass
class Product:
    """Representation of a liquidation product entry."""

    title: str
    url: str
    price_display: str
    sale_price_display: str
    stock: str
    brand: str = ""
    image: str = ""
    sku: str = ""
    price: float | None = None
    sale_price: float | None = None

    def as_csv_row(self) -> List[str]:
        return [self.title, self.sale_price_display, self.stock, self.url]

    def as_json_row(self) -> dict[str, object]:
        price_value = self.price if self.price is not None else self.sale_price
        return {
            "title": self.title,
            "brand": self.brand,
            "url": self.url,
            "image": self.image,
            "price": price_value,
            "salePrice": self.sale_price,
            "priceDisplay": self.price_display or None,
            "salePriceDisplay": self.sale_price_display or None,
            "store": "Sporting Life",
            "city": "laval",
            "sku": self.sku,
            "stock": self.stock,
        }


def _select_text(parent: Tag, selectors: Iterable[str]) -> str:
    for selector in selectors:
        element = parent.select_one(selector)
        if element and element.text:
            return element.text.strip()
    return ""


def _extract_href(parent: Tag, selectors: Iterable[str]) -> str:
    for selector in selectors:
        element = parent.select_one(selector)
        if element and element.has_attr("href"):
            return element["href"]
    return ""


def _extract_image(parent: Tag) -> str:
    image = parent.select_one("img")
    if not isinstance(image, Tag):
        return ""
    for attribute in ("data-src", "data-original", "src", "data-lazy"):
        value = image.get(attribute)
        if value:
            return value
    return ""


def _parse_price_value(raw: str) -> float | None:
    if not raw:
        return None
    cleaned = (
        raw.replace("$", "")
        .replace("CAD", "")
        .replace("CA", "")
        .replace("\xa0", " ")
        .replace("\u202f", " ")
        .strip()
    )
    # Keep only digits, commas, periods and spaces to handle French formatting.
    cleaned = re.sub(r"[^0-9,\.\s-]", "", cleaned)
    cleaned = cleaned.replace(" ", "")
    cleaned = cleaned.replace(",", ".")
    try:
        return float(cleaned)
    except ValueError:
        match = re.search(r"-?\d+(?:\.\d+)?", cleaned)
        if match:
            try:
                return float(match.group(0))
            except ValueError:
                return None
    return None


def parse_product(tile: Tag) -> Product:
    title = _select_text(
        tile,
        (
            "div.product-title a",
            "div.product-name a",
            "a.name-link",
        ),
    )
    brand = _select_text(tile, ("div.product-brand", "div.brand-name"))
    price_display = _select_text(
        tile,
        (
            "span.price-standard",
            "span.was",
            "span.value.original-price",
        ),
    )
    sale_price_display = _select_text(
        tile,
        (
            "span.sales",
            "span.price-sales",
            "span.value",
        ),
    )
    stock = _select_text(
        tile,
        (
            "div.product-inventory",
            "div.inventory-level",
            "div.stock-message",
        ),
    )
    href = _extract_href(
        tile,
        (
            "div.product-title a",
            "div.product-name a",
            "a.name-link",
        ),
    )
    image_url = _extract_image(tile)
    sku = tile.get("data-itemid") or tile.get("data-productid") or tile.get("data-product-id") or ""

    absolute_url = href
    if href and href.startswith("/"):
        absolute_url = f"https://www.sportinglife.ca{href}"
    elif href and href.startswith("http"):
        absolute_url = href

    return Product(
        title=title,
        brand=brand,
        price_display=price_display,
        sale_price_display=sale_price_display,
        stock=stock,
        url=absolute_url,
        image=image_url,
        sku=sku,
        price=_parse_price_value(price_display),
        sale_price=_parse_price_value(sale_price_display),
    )


def parse_products(soup: BeautifulSoup) -> List[Product]:
    tiles = soup.select("div.product-tile")
    products: List[Product] = []
    for tile in tiles:
        product = parse_product(tile)
        if product.title and product.url:
            products.append(product)
    return products


def get_next_page_url(soup: BeautifulSoup, current_url: str) -> str:
    """Return the absolute URL for the next pagination link if present."""

    selectors = (
        "li.pagination-next:not(.disabled) a",
        "a.pagination__next",
        "a[rel='next']",
        "a[aria-label='Next']",
        "a[aria-label='Suivant']",
    )
    for selector in selectors:
        link = soup.select_one(selector)
        if isinstance(link, Tag):
            href = (link.get("href") or "").strip()
            if href:
                absolute = urljoin(current_url, href)
                if absolute != current_url:
                    return absolute

    # Some Sporting Life templates expose data attributes for pagination.
    candidate = soup.select_one("li.pagination-next[data-page], button[data-page]")
    if isinstance(candidate, Tag):
        for attribute in ("data-page", "data-page-number", "data-pagevalue"):
            page_value = (candidate.get(attribute) or "").strip()
            if page_value:
                base, *_ = current_url.split("?", 1)
                return f"{base}?page={page_value}"

    return ""


def _expand_show_more_buttons(
    playwright_page: Page, *, click_delay: float = 1.0, max_clicks: int = 100
) -> None:
    """Keep revealing products until no more can be loaded."""

    wait_ms = max(int(click_delay * 1000), 500)
    product_locator = playwright_page.locator("div.product-tile")
    stagnant_rounds = 0

    for _ in range(max_clicks):
        before_count = product_locator.count()

        # Try to click explicit "show more" controls first.
        candidates = playwright_page.locator("button, a, [role='button']").filter(
            has_text=SHOW_MORE_PATTERN
        )
        triggered = False

        try:
            if candidates.count() > 0:
                button = candidates.first
                try:
                    button.wait_for(state="visible", timeout=5000)
                except PlaywrightTimeoutError:
                    pass
                try:
                    button.scroll_into_view_if_needed(timeout=2000)
                except Exception:
                    # Best effort; scrolling failures should not abort the run.
                    pass
                try:
                    button.click(timeout=5000, force=True, no_wait_after=True)
                    triggered = True
                except PlaywrightTimeoutError:
                    triggered = False
                except Exception as exc:
                    # Sporadic site widgets (e.g. chat popups) can interfere with the
                    # click binding and raise generic Playwright errors. Fallback to
                    # scrolling behaviour instead of aborting the scrape.
                    print(
                        "Impossible de cliquer sur le bouton 'voir plus':",
                        str(exc),
                    )
                    triggered = False
        except PlaywrightTimeoutError:
            triggered = False
        except Exception:
            triggered = False

        # Fallback for infinite scroll layouts where the products load on scroll.
        if not triggered:
            try:
                playwright_page.evaluate(
                    "window.scrollTo(0, document.documentElement.scrollHeight)"
                )
                triggered = True
            except PlaywrightTimeoutError:
                triggered = False

        if not triggered:
            counts = _read_loaded_total(playwright_page)
            if counts and counts[1] is not None and counts[0] < counts[1]:
                playwright_page.wait_for_timeout(wait_ms)
                continue
            break

        playwright_page.wait_for_timeout(wait_ms)
        try:
            playwright_page.wait_for_function(
                "(previous) => document.querySelectorAll('div.product-tile').length > previous",
                arg=before_count,
                timeout=max(wait_ms * 3, 5000),
            )
        except PlaywrightTimeoutError:
            pass
        after_count = product_locator.count()

        if after_count <= before_count:
            stagnant_rounds += 1
            counts = _read_loaded_total(playwright_page)
            if counts and counts[1] is not None and counts[0] >= counts[1]:
                break
            if stagnant_rounds >= 3:
                break
        else:
            stagnant_rounds = 0

    # Give the DOM a moment to settle after the last interaction.
    playwright_page.wait_for_timeout(250)


def _load_page(
    playwright_page: Page, url: str, *, click_delay: float = 1.0
) -> BeautifulSoup:
    try:
        playwright_page.goto(url, wait_until="networkidle")
    except PlaywrightTimeoutError:
        # Continue with the current DOM snapshot even if navigation timed out.
        pass
    try:
        playwright_page.wait_for_selector("div.product-tile", timeout=20000)
    except PlaywrightTimeoutError:
        # Proceed with whatever was rendered to allow downstream checks
        pass
    _expand_show_more_buttons(playwright_page, click_delay=click_delay)
    return BeautifulSoup(playwright_page.content(), "html.parser")


def collect_all_pages(delay: float, *, headless: bool) -> List[Product]:
    products: List[Product] = []
    page_num = 1
    current_url = BASE_URL
    visited_urls: set[str] = set()

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=headless)
        context = browser.new_context(
            user_agent=USER_AGENT, extra_http_headers=HEADERS
        )
        page = context.new_page()
        page.set_default_timeout(60000)

        try:
            while True:
                if current_url in visited_urls:
                    break
                print(f"Téléchargement page {page_num}...")
                visited_urls.add(current_url)
                soup = _load_page(page, current_url, click_delay=max(delay, 0.5))
                page_products = parse_products(soup)
                if not page_products:
                    break
                products.extend(page_products)
                next_url = get_next_page_url(soup, current_url)
                if not next_url or next_url in visited_urls:
                    break
                current_url = next_url
                page_num += 1
                if delay:
                    page.wait_for_timeout(delay * 1000)
        finally:
            context.close()
            browser.close()

    return products


def write_csv(products: Iterable[Product], output_file: Path) -> None:
    output_file.parent.mkdir(parents=True, exist_ok=True)
    with output_file.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["name", "sale_price", "stock", "url"])
        for product in products:
            writer.writerow(product.as_csv_row())


def write_json(products: Iterable[Product], output_file: Path) -> None:
    payload = [product.as_json_row() for product in products]
    output_file.parent.mkdir(parents=True, exist_ok=True)
    with output_file.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-csv",
        type=Path,
        default=DEFAULT_CSV_PATH,
        help=f"Chemin du fichier CSV de sortie (défaut: {DEFAULT_CSV_PATH})",
    )
    parser.add_argument(
        "--output-json",
        type=Path,
        default=DEFAULT_JSON_PATH,
        help=f"Chemin du fichier JSON de sortie (défaut: {DEFAULT_JSON_PATH})",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=2.0,
        help="Temps d'attente (en secondes) entre les requêtes de pagination.",
    )
    parser.add_argument(
        "--no-headless",
        dest="headless",
        action="store_false",
        help="Désactive le mode headless pour déboguer le navigateur.",
    )
    parser.set_defaults(headless=True)
    return parser


def main() -> int:
    parser = build_argument_parser()
    args = parser.parse_args()

    products = collect_all_pages(delay=max(args.delay, 0.0), headless=args.headless)
    if not products:
        print("Aucun produit n'a été trouvé sur la page de liquidation.")
        return 1

    write_csv(products, args.output_csv)
    write_json(products, args.output_json)
    print(
        f"{len(products)} produits enregistrés dans {args.output_csv} et {args.output_json}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
