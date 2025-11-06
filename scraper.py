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

from playwright.async_api import async_playwright

URLS: Dict[str, str] = {
    "st-jerome": "https://www.sportinglife.ca/fr-CA/liquidation/?store=st-jerome",
    "montreal": "https://www.sportinglife.ca/fr-CA/liquidation/?store=montreal",
}

PRODUCT_TILE_SELECTOR = ".product-listing__list-item"
TITLE_SELECTOR = ".product-tile__title"
PRICE_SELECTOR = ".product-price__value"
SCROLL_PAUSE_SECONDS = 2


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
    return parser.parse_args()


async def extract_text(element, selector: str) -> str:
    """Return the trimmed text content for a selector within an element."""
    target = await element.query_selector(selector)
    if not target:
        return ""
    text = await target.inner_text()
    return text.strip()


async def collect_products(page) -> List[Dict[str, Any]]:
    """Collect product information from the current page."""
    tiles = await page.query_selector_all(PRODUCT_TILE_SELECTOR)
    items: List[Dict[str, Any]] = []
    for tile in tiles:
        title = await extract_text(tile, TITLE_SELECTOR)
        price = await extract_text(tile, PRICE_SELECTOR)
        if not title and not price:
            continue
        items.append({"title": title, "price": price})
    return items


async def run_scraper(ville: str, output_path: Path) -> None:
    """Run the scraper for the given city and output path."""
    url = URLS[ville]

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()
        page = await context.new_page()
        await page.goto(url, wait_until="networkidle")
        await page.wait_for_selector(PRODUCT_TILE_SELECTOR, timeout=30000)

        previous_height = -1
        while True:
            current_height = await page.evaluate("document.body.scrollHeight")
            if current_height == previous_height:
                break
            previous_height = current_height
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            await asyncio.sleep(SCROLL_PAUSE_SECONDS)

        items = await collect_products(page)

        output_path.parent.mkdir(parents=True, exist_ok=True)
        with output_path.open("w", encoding="utf-8") as output_file:
            json.dump(items, output_file, ensure_ascii=False, indent=2)

        await browser.close()

        print(f"Scraping terminé pour {ville}, {len(items)} items sauvegardés dans {output_path}")


def main() -> None:
    args = parse_args()
    ville = args.ville.lower()
    output = Path(args.output)
    asyncio.run(run_scraper(ville, output))


if __name__ == "__main__":
    main()
