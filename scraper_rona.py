"""Scrape RONA St-Jérôme liquidation listings to JSON."""

from __future__ import annotations

import json
from typing import Any, Dict, Iterable, List

from bs4 import BeautifulSoup
from playwright.sync_api import Page, TimeoutError, sync_playwright

LISTING_URL = (
    "https://www.rona.ca/fr/promotions/liquidation?catalogId=10051&storeId=10151&langId=-2"
)
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36"
)
HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept-Language": "fr-CA,fr;q=0.9,en;q=0.8",
}
NAVIGATION_WAIT_STATES: Iterable[str] = ("domcontentloaded", "load")
NAVIGATION_TIMEOUT_MS = 60_000
SELECTOR_TIMEOUT_MS = 45_000


def navigate_to_listing(page: Page) -> None:
    """Navigate to the liquidation page trying multiple load strategies."""

    last_exc: TimeoutError | None = None
    for wait_state in NAVIGATION_WAIT_STATES:
        try:
            page.goto(
                LISTING_URL,
                wait_until=wait_state,
                timeout=NAVIGATION_TIMEOUT_MS,
            )
            return
        except TimeoutError as exc:
            last_exc = exc
    assert last_exc is not None  # pragma: no cover - defensive programming
    raise last_exc


def render_listing_page() -> str:
    """Return the fully rendered HTML for the liquidation listing page."""

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent=USER_AGENT,
            extra_http_headers=HEADERS,
            locale="fr-CA",
            timezone_id="America/Toronto",
        )
        page = context.new_page()
        page.set_default_navigation_timeout(NAVIGATION_TIMEOUT_MS)
        page.set_default_timeout(SELECTOR_TIMEOUT_MS)
        try:
            navigate_to_listing(page)
            page.wait_for_selector(
                ".product-tile__wrapper",
                timeout=SELECTOR_TIMEOUT_MS,
                state="visible",
            )
            html = page.content()
        finally:
            context.close()
            browser.close()
    return html


def extract_products(soup: BeautifulSoup) -> List[Dict[str, Any]]:
    """Return product metadata extracted from the listing HTML."""

    products: List[Dict[str, Any]] = []
    for item in soup.select(".product-tile__wrapper"):
        title = item.select_one(".product-tile__title")
        price = item.select_one(".product-tile__price")
        url = item.select_one(".product-tile__title a")
        if not (title and price and url and url.has_attr("href")):
            continue
        products.append(
            {
                "name": title.get_text(strip=True),
                "price": price.get_text(strip=True),
                "url": f"https://www.rona.ca{url['href']}",
            }
        )
    return products


def main() -> None:
    try:
        html = render_listing_page()
    except TimeoutError as exc:  # pragma: no cover - defensive path for CI visibility
        raise SystemExit(f"Timed out while loading liquidation listings: {exc}") from exc

    soup = BeautifulSoup(html, "html.parser")
    products = extract_products(soup)
    with open("rona-st-jerome.json", "w", encoding="utf-8") as fp:
        json.dump(products, fp, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()
