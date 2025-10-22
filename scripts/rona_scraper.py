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

        try:
            for selector in dismissal_selectors:
                with suppress(PlaywrightTimeoutError):
                    element = await page.wait_for_selector(selector, timeout=3000)
                    if element:
                        await element.click()

            # Ensure that lazy loaded products are visible before collecting them.
            with suppress(PlaywrightTimeoutError):
                await page.wait_for_load_state("networkidle")
            await asyncio.sleep(2)
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            await page.wait_for_timeout(1000)

            products = await page.query_selector_all(".product-tile.js-product-tile")

            if not products:
                html = await page.content()
                with open("rona_debug.html", "w", encoding="utf-8") as f:
                    f.write(html)
                raise RuntimeError(
                    "Aucun produit trouvé — vérifie le fichier rona_debug.html."
                )

            for product in products:
                title_el = await product.query_selector(".product-title__title")
                brand_el = await product.query_selector(".product-tile__brand")
                price_el = await product.query_selector(".price-box, .price-box__rebate")
                link_el = await product.query_selector("a[href].product-title__title")
                img_el = await product.query_selector("img.product-tile__image")

                title = (await title_el.inner_text()) if title_el else None
                brand = (await brand_el.inner_text()) if brand_el else None
                price = (await price_el.inner_text()) if price_el else None
                link = (await link_el.get_attribute("href")) if link_el else None
                image = (await img_el.get_attribute("src")) if img_el else None

                if title:
                    title = title.strip()
                if brand:
                    brand = brand.strip()
                if price:
                    price = price.strip()

                if link and not link.startswith("http"):
                    link = f"https://www.rona.ca{link}"

                results.append(
                    {
                        "title": title,
                        "brand": brand,
                        "price": price,
                        "link": link,
                        "image": image,
                    }
                )

            if not results:
                html = await page.content()
                with open("rona_debug.html", "w", encoding="utf-8") as f:
                    f.write(html)
                raise RuntimeError(
                    "Aucun produit trouvé — vérifie le fichier rona_debug.html."
                )
        finally:
            await browser.close()

    print(f"{len(results)} produits collectés")

    os.makedirs("data/rona", exist_ok=True)
    filename = f"data/rona/rona_liquidation_{datetime.now().strftime('%Y%m%d_%H%M')}.json"

    with open(filename, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    print(f"{len(results)} produits enregistrés dans {filename}")


if __name__ == "__main__":
    asyncio.run(scrape_rona_liquidation())
