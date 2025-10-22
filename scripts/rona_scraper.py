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

        # Wait until at least one product container is attached to the DOM.
        await page.wait_for_selector(".product__info", state="attached", timeout=60000)

        # Ensure that lazy loaded products are visible.
        await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        await page.wait_for_timeout(1000)

        async def safe_text(locator, *, timeout=2000):
            with suppress(PlaywrightTimeoutError):
                text = await locator.text_content(timeout=timeout)
                return text.strip() if text else None
            return None

        products = page.locator(".product__info")
        count = await products.count()

        for index in range(count):
            product = products.nth(index)

            title = await safe_text(product.locator(".product__description"))
            price = await safe_text(product.locator(".price__value"))
            discount = await safe_text(product.locator(".price__discount"), timeout=1000)

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
