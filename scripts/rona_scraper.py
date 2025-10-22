import asyncio
from contextlib import suppress
import json
import os
from datetime import datetime

from playwright.async_api import TimeoutError as PlaywrightTimeoutError
from playwright.async_api import async_playwright


async def scrape_rona_liquidation():
    url = "https://www.rona.ca/fr/promotions/liquidation"
    results = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()

        await page.goto(url, timeout=60000, wait_until="domcontentloaded")
        await page.wait_for_load_state("networkidle")
        await asyncio.sleep(5)

        # Several overlays (cookie banner, store selector) can hide the content.
        # Try to dismiss the most common ones without failing when they are missing.
        dismissal_selectors = [
            "#onetrust-accept-btn-handler",
            "button[data-testid='accept-all']",
            "button[data-testid='closeStoreModal']",
            "button[aria-label='Fermer']",
        ]
        for selector in dismissal_selectors:
            with suppress(PlaywrightTimeoutError):
                element = await page.wait_for_selector(selector, timeout=3000)
                if element:
                    await element.click()

        product_selectors = [
            "[data-testid='plp-product-card']",
            "[data-testid='product-card']",
            "article[data-testid='product-card']",
            "article[data-automation-id='product-card']",
            "article.plp-product-card",
            "li[data-testid='plp-product-card']",
            ".plp-product-card",
            ".product-card",
            ".product__info",
            ".product",
            "li.product-grid__item",
            ".product-tile",
        ]

        products = None
        for selector in product_selectors:
            try:
                await page.wait_for_selector(selector, state="attached", timeout=60000)
            except PlaywrightTimeoutError:
                continue

            candidate = page.locator(selector)
            if await candidate.count() > 0:
                products = candidate
                break

        if products is None:
            combined_selector = ", ".join(product_selectors)
            try:
                await page.wait_for_selector(
                    combined_selector, state="attached", timeout=10000
                )
            except PlaywrightTimeoutError:
                pass
            else:
                candidate = page.locator(combined_selector)
                if await candidate.count() > 0:
                    products = candidate

        if products is None:
            raise RuntimeError(
                "Aucun conteneur de produit n'a été trouvé. Vérifiez les sélecteurs CSS."
            )

        # Ensure that lazy loaded products are visible.
        with suppress(PlaywrightTimeoutError):
            await page.wait_for_load_state("networkidle")
        await asyncio.sleep(2)
        await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        await page.wait_for_timeout(1000)

        async def safe_text(locator, *, timeout=2000):
            with suppress(PlaywrightTimeoutError):
                text = await locator.text_content(timeout=timeout)
                if text:
                    text = text.strip()
                    if text:
                        return text
            return None

        async def extract_first_text(base_locator, selectors, *, timeout=2000):
            for selector in selectors:
                text = await safe_text(base_locator.locator(selector), timeout=timeout)
                if text:
                    return text
            return None

        count = await products.count()

        for index in range(count):
            product = products.nth(index)

            title = await extract_first_text(
                product,
                [
                    ".product__description",
                    ".product__name",
                    ".product-card__title",
                    ".plp-product-card__name",
                    ".product-tile__title",
                    "[data-testid='plp-product-card__name']",
                    "[data-testid='product-card-title']",
                    "[data-testid='plp-product-card-title']",
                    "[data-testid='product-name']",
                    "a[title]",
                ],
            )
            price = await extract_first_text(
                product,
                [
                    ".price__value",
                    ".price__number",
                    ".product-card__price",
                    ".plp-product-card__price",
                    ".product-tile__price",
                    ".product-tile__price-value",
                    "[data-testid='price']",
                    "[data-testid='product-card-price']",
                    "[data-testid='plp-product-card-price']",
                    "[data-testid='price-amount']",
                ],
            )
            discount = await extract_first_text(
                product,
                [
                    ".price__discount",
                    ".product-card__promotion",
                    ".plp-product-card__discount",
                    ".product-tile__badge",
                    ".product-tile__tag",
                    "[data-testid='badge-text']",
                    "[data-testid='badge-label']",
                    "[data-testid='savings']",
                ],
                timeout=1000,
            )

            if not price:
                price_attribute = await product.get_attribute("data-price")
                if price_attribute:
                    price_attribute = price_attribute.strip()
                    if price_attribute:
                        price = price_attribute

            if not any([title, price, discount]):
                continue

            results.append(
                {
                    "title": title,
                    "price": price,
                    "discount": discount,
                }
            )

        await browser.close()

    os.makedirs("data/rona", exist_ok=True)
    filename = f"data/rona/rona_liquidation_{datetime.now().strftime('%Y%m%d_%H%M')}.json"

    with open(filename, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    print(f"{len(results)} produits enregistrés dans {filename}")


if __name__ == "__main__":
    asyncio.run(scrape_rona_liquidation())
