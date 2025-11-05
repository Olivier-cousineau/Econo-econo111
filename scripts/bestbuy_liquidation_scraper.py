import asyncio
import json
import logging
from pathlib import Path

from playwright.async_api import TimeoutError as PlaywrightTimeoutError, async_playwright

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

URL = "https://www.bestbuy.ca/en-ca/collection/clearance-products/113065"
OUTPUT = Path("data/best-buy/liquidations/clearance.json")


async def scrape_bestbuy() -> list[dict]:
    """Collect clearance products from the dynamically rendered catalogue."""
    logging.info("🌐 Visiting %s", URL)
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=True, slow_mo=300)
        context = await browser.new_context(
            locale="en-CA", viewport={"width": 1920, "height": 1080}
        )
        page = await context.new_page()

        await page.goto(URL, timeout=180_000)
        await page.wait_for_load_state("domcontentloaded", timeout=180_000)
        try:
            await page.wait_for_load_state("networkidle", timeout=120_000)
        except PlaywrightTimeoutError:
            logging.warning("Network idle wait timed out; continuing with collected DOM")
        await asyncio.sleep(10)

        items = await page.query_selector_all(
            "li[class*='productItem'], div[class*='productItem_']"
        )
        products: list[dict] = []

        for item in items:
            try:
                name = await item.query_selector_eval("h4", "el => el.innerText") or "Unknown"
                price = await item.query_selector_eval("div[class*='price']", "el => el.innerText") or "N/A"
                link = await item.query_selector_eval("a", "el => el.href")
                image = await item.query_selector_eval("img", "el => el.src")

                products.append(
                    {
                        "product_name": name.strip(),
                        "price": price.strip(),
                        "product_link": link,
                        "image": image,
                        "store": "Best Buy Canada Clearance",
                    }
                )
            except Exception as exc:  # pragma: no cover - defensive logging only
                logging.debug("Skipping product due to error: %s", exc)
                continue

        await browser.close()
        return products


async def main() -> None:
    products = await scrape_bestbuy()
    logging.info("✅ Extracted %d products", len(products))

    if not products:
        raise SystemExit("❌ No products found — check page structure or selector")

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT.open("w", encoding="utf-8") as file:
        json.dump(products, file, indent=2, ensure_ascii=False)
    logging.info("💾 Saved results to %s", OUTPUT)


if __name__ == "__main__":
    asyncio.run(main())
