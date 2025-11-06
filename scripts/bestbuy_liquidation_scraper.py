import asyncio
import json
import logging
from pathlib import Path

from playwright.async_api import (
    Error as PlaywrightError,
    TimeoutError as PlaywrightTimeoutError,
    async_playwright,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

URL = "https://www.bestbuy.ca/en-ca/collection/clearance-products/113065"
OUTPUT = Path("data/best-buy/liquidations/clearance.json")


async def scrape_bestbuy() -> list[dict]:
    """Collect clearance products from the dynamically rendered catalogue."""
    logging.info("🌐 Visiting %s", URL)
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=True, slow_mo=300)
        try:
            context = await browser.new_context(
                locale="en-CA", viewport={"width": 1920, "height": 1080}
            )
            page = await context.new_page()

            try:
                await page.goto(URL, timeout=180_000)
            except PlaywrightTimeoutError:
                logging.warning(
                    "Navigation timed out at %s; continuing with partial content", URL
                )

            try:
                await page.wait_for_load_state("domcontentloaded", timeout=180_000)
            except PlaywrightTimeoutError:
                logging.warning("DOM content load timed out; proceeding with available DOM")
            await asyncio.sleep(10)

            items = await page.query_selector_all(
                "li[class*='productItem'], div[class*='productItem_']"
            )
            products: list[dict] = []

            for item in items:
                name = await _safe_text(item, ("h4", "h3"))
                price = await _safe_text(item, ("div[class*='price']", "span[class*='price']"))
                link = await _safe_attribute(item, "a", "href")
                image = await _safe_attribute(item, "img", "src")

                if not link:
                    logging.debug("Skipping entry without product link")
                    continue

                products.append(
                    {
                        "product_name": (name or "Unknown").strip(),
                        "price": (price or "N/A").strip(),
                        "product_link": link,
                        "image": image,
                        "store": "Best Buy Canada Clearance",
                    }
                )

            return products
        finally:
            await browser.close()


async def main() -> None:
    products = await scrape_bestbuy()
    logging.info("✅ Extracted %d products", len(products))

    if not products:
        raise SystemExit("❌ No products found — check page structure or selector")

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT.open("w", encoding="utf-8") as file:
        json.dump(products, file, indent=2, ensure_ascii=False)
    logging.info("💾 Saved results to %s", OUTPUT)


async def _safe_text(item, selectors: tuple[str, ...]) -> str | None:
    for selector in selectors:
        text = await _query_text(item, selector)
        if text:
            return text
    return None


async def _query_text(item, selector: str) -> str | None:
    try:
        handle = await item.query_selector(selector)
    except PlaywrightError:
        return None
    if handle is None:
        return None
    try:
        value = await handle.inner_text()
    except PlaywrightError:
        return None
    return value.strip() or None


async def _safe_attribute(item, selector: str, attribute: str) -> str | None:
    try:
        handle = await item.query_selector(selector)
    except PlaywrightError:
        return None
    if handle is None:
        return None
    try:
        value = await handle.get_attribute(attribute)
    except PlaywrightError:
        return None
    if value is None:
        return None
    return value.strip() or None


if __name__ == "__main__":
    asyncio.run(main())
