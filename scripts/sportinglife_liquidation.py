import asyncio
import csv
import sys
from playwright.async_api import async_playwright

URL = "https://www.sportinglife.ca/fr-CA/liquidation/"
OUTPUT_FILE = "sportinglife_laval_liquidation.csv"


async def scrape_sportinglife():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(locale="fr-CA")
        page = await context.new_page()

        print("\U0001F310 Ouverture de la page Sporting Life Liquidation...")
        await page.goto(URL, timeout=120000)
        await page.wait_for_load_state("networkidle")

        # Attendre que les produits apparaissent
        try:
            await page.wait_for_selector(".product-tile", timeout=45000)
        except Exception:
            print("\u26a0\ufe0f Aucun produit trouvé avant expiration du délai.")
            # Sauvegarde du HTML pour débogage
            html = await page.content()
            with open("debug_sportinglife.html", "w", encoding="utf-8") as f:
                f.write(html)
            await browser.close()
            sys.exit(0)

        print("\u2705 Produits trouvés, extraction en cours...")
        products = await page.query_selector_all(".product-tile")

        data = []
        for product in products:
            try:
                name = await product.locator(".pdp-link").inner_text()
                image = await product.locator("img").get_attribute("src")
                price_now = await product.locator(".sales").inner_text()
                try:
                    price_original = await product.locator(".was").inner_text()
                except:
                    price_original = "—"
                link = await product.locator(".pdp-link").get_attribute("href")
                if not link.startswith("http"):
                    link = "https://www.sportinglife.ca" + link

                data.append({
                    "Nom du produit": name.strip(),
                    "Prix réduit": price_now.strip(),
                    "Prix original": price_original.strip(),
                    "Image": image,
                    "Lien": link,
                })
            except Exception as e:
                print(f"Erreur sur un produit : {e}")

        # Sauvegarde CSV
        with open(OUTPUT_FILE, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=data[0].keys())
            writer.writeheader()
            writer.writerows(data)

        print(f"\U0001F4BE {len(data)} produits enregistrés dans {OUTPUT_FILE}")
        await browser.close()


if __name__ == "__main__":
    asyncio.run(scrape_sportinglife())
