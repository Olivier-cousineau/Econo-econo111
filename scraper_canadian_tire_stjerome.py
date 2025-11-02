"""Scraper for Canadian Tire liquidation deals specific to the St-Jérôme store."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

from playwright.sync_api import sync_playwright

URL = "https://www.canadiantire.ca/fr/promotions/liquidation.html?store=271"
OUTPUT_PATH = Path("liquidation_ct_stjerome.json")


def _extract_text(element, selector: str) -> str:
    """Safely extract text from a selector under the given element."""
    sub_el = element.query_selector(selector)
    return sub_el.inner_text().strip() if sub_el else ""


def _extract_attribute(element, selector: str, attribute: str) -> str:
    sub_el = element.query_selector(selector)
    if not sub_el:
        return ""
    value = sub_el.get_attribute(attribute)
    return value.strip() if value else ""


def scrape_liquidation_ct() -> List[Dict[str, Any]]:
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(locale="fr-CA")
        page = context.new_page()
        page.goto(URL, timeout=60_000)
        page.wait_for_selector(".product-list__item", timeout=60_000)

        results: List[Dict[str, Any]] = []
        seen_urls = set()

        while True:
            items = page.query_selector_all(".product-list__item")
            for item in items:
                titre = _extract_text(item, ".product-title")
                prix = _extract_text(item, ".price__value")
                rabais = _extract_text(item, ".badge--savings")
                relative_url = _extract_attribute(item, ".product-title a", "href")
                image = _extract_attribute(item, ".product-image img", "src")

                if not relative_url or relative_url in seen_urls:
                    continue

                seen_urls.add(relative_url)
                results.append(
                    {
                        "titre": titre,
                        "prix": prix,
                        "rabais": rabais,
                        "url": f"https://www.canadiantire.ca{relative_url}",
                        "image": image,
                    }
                )

            next_btn = page.query_selector("button[aria-label*='Suivant']")
            if next_btn and next_btn.is_enabled():
                next_btn.click()
                page.wait_for_timeout(2_500)
            else:
                break

        browser.close()

    return results


def main() -> None:
    data = scrape_liquidation_ct()
    OUTPUT_PATH.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
