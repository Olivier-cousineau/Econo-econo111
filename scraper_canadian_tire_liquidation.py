"""Scrape Canadian Tire liquidation items for the Saint-Jérôme store."""

from __future__ import annotations

import asyncio
import json
import os
import re
from dataclasses import asdict, dataclass
from typing import Any, Dict, List, Optional
from urllib.parse import urljoin

from playwright.async_api import (
    Browser,
    Error as PlaywrightError,
    Page,
    TimeoutError as PlaywrightTimeoutError,
    async_playwright,
)

LIQUIDATION_URL = "https://www.canadiantire.ca/fr/promotions/liquidation.html"
STORE_POSTAL_CODE = "J7Y 4Y9"
STORE_ID = "271"
OUTPUT_FILE = "data/canadian-tire/saint-jerome.json"
MIN_DISCOUNT = 0.60
PRICE_PATTERN = re.compile(r"(\d+[\.,]\d+)")


@dataclass
class Product:
    """Serializable representation of a discounted product."""

    product_name: str
    original_price: str
    discount_price: str
    image_url: str
    product_link: str
    availability: str
    sku: str = ""

    def discount_ratio(self) -> float:
        try:
            original = float(self.original_price)
            discount = float(self.discount_price)
        except (TypeError, ValueError):
            return 0.0
        if original <= 0:
            return 0.0
        return 1 - (discount / original)


async def _extract_text(locator) -> str:
    try:
        text = await locator.inner_text()
    except (PlaywrightTimeoutError, PlaywrightError):
        return ""
    if not text:
        return ""
    return " ".join(text.split())


async def _extract_attribute(locator, attribute: str) -> str:
    try:
        value = await locator.get_attribute(attribute)
    except (PlaywrightTimeoutError, PlaywrightError):
        return ""
    return value or ""


def _parse_price(value: str) -> Optional[str]:
    if not value:
        return None
    cleaned = value.replace("\xa0", " ").replace("$", "").replace("CAD", "")
    cleaned = cleaned.replace("\u202f", "").strip()
    match = PRICE_PATTERN.search(cleaned.replace(",", "."))
    if not match:
        return None
    try:
        amount = float(match.group(1))
    except ValueError:
        return None
    return f"{amount:.2f}"


async def _select_store(page: Page) -> None:
    """Ensure the Saint-Jérôme store is selected when browsing the listing."""

    try:
        store_button = page.locator("button:has-text(\"Sélectionner le magasin\")")
        if await store_button.count():
            await store_button.first.click()
            await page.wait_for_timeout(1_000)
    except PlaywrightError:
        return

    try:
        postal_input = page.locator("input[placeholder*=\"Code postal\"]")
        if await postal_input.count():
            await postal_input.first.fill(STORE_POSTAL_CODE)
            await postal_input.first.press("Enter")
            await page.wait_for_timeout(3_000)
            store_option = page.locator(f"button:has-text(\"{STORE_ID}\")")
            if await store_option.count():
                await store_option.first.click()
                await page.wait_for_timeout(3_000)
    except PlaywrightError:
        pass


async def _collect_products_from_page(page: Page) -> List[Product]:
    products: List[Product] = []
    cards = page.locator("div[class*=\"product-card\"]")
    count = await cards.count()
    for index in range(count):
        card = cards.nth(index)
        name = await _extract_text(card.locator("a[class*=\"product-title-link\"]"))
        original_price_raw = await _extract_text(card.locator("span[class*=\"price-regular\"]"))
        sale_price_raw = await _extract_text(card.locator("span[class*=\"price-sale\"]"))
        product_link = await _extract_attribute(card.locator("a[class*=\"product-title-link\"]"), "href")
        if product_link:
            product_link = urljoin(LIQUIDATION_URL, product_link)
        image_url = await _extract_attribute(card.locator("img"), "src")
        availability = await _extract_text(card.locator("[class*=\"availability\"]"))
        sku = await _extract_text(card.locator("[class*=\"product-number\"] span:last-child"))

        original_price = _parse_price(original_price_raw)
        sale_price = _parse_price(sale_price_raw)
        if not name or not original_price or not sale_price:
            continue
        if float(original_price) <= 0:
            continue
        discount_ratio = 1 - (float(sale_price) / float(original_price))
        if discount_ratio < MIN_DISCOUNT:
            continue

        products.append(
            Product(
                product_name=name,
                original_price=original_price,
                discount_price=sale_price,
                image_url=image_url,
                product_link=product_link,
                availability=availability,
                sku=sku,
            )
        )
    return products


async def _paginate_products(page: Page) -> List[Product]:
    aggregated: List[Product] = []
    while True:
        try:
            await page.wait_for_selector("div[class*=\"product-card\"]", timeout=20_000)
        except PlaywrightTimeoutError:
            await page.wait_for_timeout(1_000)
        aggregated.extend(await _collect_products_from_page(page))
        next_button = page.locator('button[aria-label*="Suivant"]')
        try:
            if not await next_button.count():
                break
            if await next_button.is_disabled():
                break
        except PlaywrightError:
            break
        try:
            await next_button.click()
        except PlaywrightError:
            break
        try:
            await page.wait_for_load_state("networkidle", timeout=30_000)
        except PlaywrightTimeoutError:
            await page.wait_for_timeout(3_000)
    return aggregated


async def scrape_liquidation() -> List[Product]:
    proxy_url = os.environ.get("PROXY") or os.environ.get("HTTPS_PROXY")
    proxy_config: Optional[Dict[str, Any]] = None
    if proxy_url:
        proxy_config = {"server": proxy_url}

    async with async_playwright() as playwright:
        browser: Browser
        browser = await playwright.chromium.launch(headless=True, proxy=proxy_config)
        context = await browser.new_context(locale="fr-CA")
        page = await context.new_page()
        await page.goto(LIQUIDATION_URL, wait_until="load", timeout=90_000)
        await page.wait_for_timeout(5_000)
        await _select_store(page)
        products = await _paginate_products(page)
        await context.close()
        await browser.close()
        return products


async def main() -> None:
    products = await scrape_liquidation()
    unique_products: Dict[str, Product] = {}
    for product in products:
        key = product.product_link or product.product_name
        if key in unique_products:
            if product.discount_ratio() > unique_products[key].discount_ratio():
                unique_products[key] = product
            continue
        unique_products[key] = product

    sorted_products = sorted(
        unique_products.values(), key=lambda item: item.discount_ratio(), reverse=True
    )

    data = [asdict(product) for product in sorted_products]
    os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2)
    print(f"Sauvegardé {len(data)} produits dans {OUTPUT_FILE}.")


if __name__ == "__main__":
    asyncio.run(main())
