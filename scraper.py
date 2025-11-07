"""Scraper for Sporting Life liquidation pages.

This module uses Playwright to capture product data for multiple stores and
save the information as JSON.
"""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
from typing import Any, Dict, List

from playwright.async_api import (
    ElementHandle,
    Page,
    TimeoutError as PlaywrightTimeoutError,
    async_playwright,
)

URLS: Dict[str, str] = {
    "st-jerome": "https://www.sportinglife.ca/fr-CA/liquidation/?store=st-jerome",
    "montreal": "https://www.sportinglife.ca/fr-CA/liquidation/?store=montreal",
}

PRODUCT_TILE_SELECTORS = [
    "article.product-grid__tile",
    "li.product-grid__item",
    ".product-listing__list-item",
    "[data-testid='product-tile']",
]
TITLE_SELECTORS = [
    ".product-tile__title",
    ".product-tile__title-link",
    "[data-testid='product-title']",
    "h2",
]
PRICE_SELECTORS = [
    ".product-price__value",
    "[data-testid='product-price']",
    "[itemprop='price']",
]
SCROLL_PAUSE_SECONDS = 2
PRODUCT_WAIT_TIMEOUT_MS = 60_000


def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description="Scrape Sporting Life liquidation data.")
    parser.add_argument(
        "--ville",
        required=True,
        choices=sorted(URLS.keys()),
        help="Ville à scraper (options: %(choices)s)",
    )
    parser.add_argument(
        "--output",
        required=True,
        help="Chemin du fichier de sortie JSON.",
    )
    parser.add_argument(
        "--debug-html",
        action="store_true",
        help="Enregistre le HTML de la page en cas d'échec du scraping.",
    )
    return parser.parse_args()


async def extract_text(element: ElementHandle, selectors: List[str]) -> str:
    """Return the trimmed text content for the first matching selector within an element."""
    for selector in selectors:
        target = await element.query_selector(selector)
        if not target:
            continue
        text = await target.inner_text()
        if text:
            return text.strip()
    return ""


async def collect_products(page: Page, selector: str) -> List[Dict[str, Any]]:
    """Collect product information from the current page using the provided selector."""
    tiles = await page.query_selector_all(selector)
    items: List[Dict[str, Any]] = []
    for tile in tiles:
        title = await extract_text(tile, TITLE_SELECTORS)
        price = await extract_text(tile, PRICE_SELECTORS)
        if not title and not price:
            continue
        items.append({"title": title, "price": price})
    return items


async def wait_for_product_tiles(page: Page) -> str:
    """Wait for one of the known product tile selectors to appear and return it."""
    for selector in PRODUCT_TILE_SELECTORS:
        try:
            await page.wait_for_selector(selector, timeout=PRODUCT_WAIT_TIMEOUT_MS)
            return selector
        except PlaywrightTimeoutError:
            continue
    raise PlaywrightTimeoutError(
        "Aucun des sélecteurs de produits attendus n'a été trouvé : "
        + ", ".join(PRODUCT_TILE_SELECTORS)
    )


async def run_scraper(ville: str, output_path: Path, debug_html: bool = False) -> None:
    """Run the scraper for the given city and output path."""
    url = URLS[ville]

    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=True)
        try:
            async with browser.new_context() as context:
                page = await context.new_page()
                await page.goto(url, wait_until="networkidle")
                await page.wait_for_load_state("networkidle")

                try:
                    product_selector = await wait_for_product_tiles(page)
                except PlaywrightTimeoutError:
                    print(
                        "Sélecteur non trouvé à temps, vérifier le sélecteur ou la structure de la page."
                    )
                    html = await page.content()
                    if debug_html:
                        debug_path = output_path.with_suffix(".html")
                        debug_path.parent.mkdir(parents=True, exist_ok=True)
                        debug_path.write_text(html, encoding="utf-8")
                        print(f"Contenu HTML sauvegardé pour debug: {debug_path}")
                    else:
                        print(html[:1_000])
                    product_selector = PRODUCT_TILE_SELECTORS[0]
                    for selector in PRODUCT_TILE_SELECTORS:
                        tiles = await page.query_selector_all(selector)
                        if tiles:
                            product_selector = selector
                            break

                previous_height = -1
                while True:
                    current_height = await page.evaluate("document.body.scrollHeight")
                    if current_height == previous_height:
                        break
                    previous_height = current_height
                    await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                    await asyncio.sleep(SCROLL_PAUSE_SECONDS)

                print(f"Extraction avec le sélecteur: {product_selector}")
                items = await collect_products(page, product_selector)

                output_path.parent.mkdir(parents=True, exist_ok=True)
                with output_path.open("w", encoding="utf-8") as output_file:
                    json.dump(items, output_file, ensure_ascii=False, indent=2)

                print(
                    f"Scraping terminé pour {ville}, {len(items)} items sauvegardés dans {output_path}"
                )
        finally:
            await browser.close()


def main() -> None:
    args = parse_args()
    ville = args.ville.lower()
    output = Path(args.output)
    asyncio.run(run_scraper(ville, output, args.debug_html))


if __name__ == "__main__":
    main()
