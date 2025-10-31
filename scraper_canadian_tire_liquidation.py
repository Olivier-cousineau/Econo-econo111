import asyncio
from playwright.async_api import async_playwright

SCRAPE_DO_TOKEN = "79806d0a26a2413fb4a1c33f14dda9743940a7548ba"
SCRAPE_DO_PROXY = f"http://api.scrape.do:8080?x-api-key={SCRAPE_DO_TOKEN}"


async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            proxy={"server": SCRAPE_DO_PROXY},
            args=["--no-sandbox", "--disable-dev-shm-usage"],
        )
        context = await browser.new_context(locale="fr-CA")
        page = await context.new_page()
        await page.goto(
            "https://www.canadiantire.ca/fr/promotions/liquidation.html",
            timeout=120000,
        )
        print(await page.title())
        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
