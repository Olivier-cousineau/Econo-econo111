import asyncio
from playwright.async_api import async_playwright


async def main() -> None:
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=False)
        page = await browser.new_page()
        await page.goto("https://www.rona.ca/fr/promotions/liquidation", timeout=90_000)

        await page.wait_for_load_state("networkidle")
        await page.evaluate("window.scrollBy(0, document.body.scrollHeight)")
        await asyncio.sleep(5)

        products = await page.query_selector_all(".product-tile.js-product-tile")
        print(f"Nombre de produits trouvés : {len(products)}")

        if not products:
            html = await page.content()
            with open("rona_debug.html", "w", encoding="utf-8") as debug_file:
                debug_file.write(html)
            print("❌ Aucun produit trouvé – vérifie le fichier rona_debug.html.")
        else:
            print("✅ OK produits trouvés")

        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
