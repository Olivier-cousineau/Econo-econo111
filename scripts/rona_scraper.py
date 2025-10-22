import asyncio
from playwright.async_api import async_playwright
import json
import os
from datetime import datetime


async def scrape_rona_liquidation():
    url = "https://www.rona.ca/fr/promotions/liquidation"
    results = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.goto(url, timeout=60000)
        await page.wait_for_selector(".product__description")

        products = await page.query_selector_all(".product__info")

        for product in products:
            title = await product.query_selector(".product__description")
            price = await product.query_selector(".price__value")
            discount = await product.query_selector(".price__discount")

            title_text = await title.inner_text() if title else None
            price_text = await price.inner_text() if price else None
            discount_text = await discount.inner_text() if discount else None

            results.append({
                "title": title_text,
                "price": price_text,
                "discount": discount_text,
            })

        await browser.close()

    os.makedirs("data/rona", exist_ok=True)
    filename = f"data/rona/rona_liquidation_{datetime.now().strftime('%Y%m%d_%H%M')}.json"

    with open(filename, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    print(f"{len(results)} produits enregistrés dans {filename}")


if __name__ == "__main__":
    asyncio.run(scrape_rona_liquidation())
