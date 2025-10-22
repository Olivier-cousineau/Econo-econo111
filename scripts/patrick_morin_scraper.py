"""Scrape clearance deals from Patrick Morin for the Prévost branch.

The scraper collects the rendered HTML (using Playwright when available) for
https://patrickmorin.com/en/clearance, extracts the visible products and keeps
only the information required by the static site (`title`, `image`, `price`,
`salePrice`, `store`, `city`, `url`). The resulting dataset is stored in
``data/patrick-morin/prevost.json`` and can optionally be pushed to the
EconoDeal ingestion API when ``ECONODEAL_API_URL`` is configured.

A manual confirmation step is enforced before writing or uploading any data so
that an operator can visually validate the collected results before they are
published on the site. The prompt can be bypassed with ``--yes`` or the
``PATRICK_MORIN_AUTO_CONFIRM=1`` environment variable when running the scraper
inside a trusted automation pipeline.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sys
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Optional
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

try:  # pragma: no cover - optional dependency in production
    from playwright.sync_api import (  # type: ignore
        TimeoutError as PlaywrightTimeoutError,
        sync_playwright,
    )
except ImportError:  # pragma: no cover - optional dependency in production
    PlaywrightTimeoutError = Exception  # type: ignore
    sync_playwright = None  # type: ignore

DEFAULT_CLEARANCE_URL = "https://patrickmorin.com/en/clearance"
DEFAULT_OUTPUT_PATH = Path("data/patrick-morin/prevost.json")
DEFAULT_STORE_NAME = "Patrick Morin"
DEFAULT_CITY = "Prevost"
USER_AGENT = os.getenv(
    "PATRICK_MORIN_USER_AGENT",
    (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"
    ),
)
REQUEST_TIMEOUT = int(os.getenv("PATRICK_MORIN_TIMEOUT", "60"))
SCROLL_STEPS = int(os.getenv("PATRICK_MORIN_SCROLL_STEPS", "10"))
AUTO_CONFIRM_ENV = os.getenv("PATRICK_MORIN_AUTO_CONFIRM", "0").lower() in {
    "1",
    "true",
    "yes",
    "y",
}
USE_PLAYWRIGHT = os.getenv("PATRICK_MORIN_USE_PLAYWRIGHT", "1").lower() not in {
    "0",
    "false",
    "no",
}
PLAYWRIGHT_HEADLESS = os.getenv("PATRICK_MORIN_HEADLESS", "1").lower() not in {
    "0",
    "false",
    "no",
}
STORE_QUERY = os.getenv("PATRICK_MORIN_STORE_QUERY", "Prevost")

PRICE_PATTERN = re.compile(
    r"(?:CAD\s*)\d[\d\s,.]*|\$\s*\d[\d\s,.]*|\d[\d\s,.]*\s*(?:CAD|\$)",
    re.IGNORECASE,
)
CURRENCY_PATTERN = re.compile(r"[^0-9,.-]+")

API_URL = os.getenv("ECONODEAL_API_URL")
API_TOKEN = os.getenv("ECONODEAL_API_TOKEN")


@dataclass
class Product:
    title: str
    url: str
    image: Optional[str]
    price: Optional[float]
    sale_price: Optional[float]

    def to_payload(self, store: str, city: str) -> dict:
        return {
            "title": self.title,
            "image": self.image,
            "price": self.price,
            "salePrice": self.sale_price,
            "store": store,
            "city": city,
            "url": self.url,
        }


def parse_args(argv: Optional[Iterable[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Confirm writing/uploading without prompting (manual action bypass).",
    )
    parser.add_argument(
        "--no-upload",
        action="store_true",
        help="Skip the API upload step even when ECONODEAL_API_URL is configured.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT_PATH,
        help="Destination JSON file (default: data/patrick-morin/prevost.json)",
    )
    parser.add_argument(
        "--url",
        default=DEFAULT_CLEARANCE_URL,
        help="Clearance page URL to scrape (default: %(default)s)",
    )
    parser.add_argument(
        "--store",
        default=DEFAULT_STORE_NAME,
        help="Store label to use in the generated JSON (default: %(default)s)",
    )
    parser.add_argument(
        "--city",
        default=DEFAULT_CITY,
        help="City label to use in the generated JSON (default: %(default)s)",
    )
    parser.add_argument(
        "--store-query",
        default=STORE_QUERY,
        help="Text used to locate the branch in the store selector (default: %(default)s)",
    )
    return parser.parse_args(list(argv) if argv is not None else None)


def fetch_with_requests(url: str) -> str:
    logging.info("Fetching %s via requests", url)
    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT})
    session.trust_env = False
    response = session.get(url, timeout=REQUEST_TIMEOUT)
    response.raise_for_status()
    return response.text


def try_click(page, selector: str, *, timeout: int = 3000) -> bool:
    if page is None:
        return False
    try:
        locator = page.locator(selector)
        locator.first.wait_for(state="visible", timeout=timeout)
        locator.first.click()
        logging.debug("Clicked selector %s", selector)
        return True
    except PlaywrightTimeoutError:
        return False
    except Exception:  # pragma: no cover - defensive path
        logging.debug("Failed to click selector %s", selector, exc_info=True)
        return False


def try_fill(page, selector: str, value: str, *, timeout: int = 3000) -> bool:
    if page is None:
        return False
    try:
        locator = page.locator(selector)
        locator.first.wait_for(state="visible", timeout=timeout)
        locator.first.fill("", timeout=timeout)
        locator.first.type(value, delay=60)
        logging.debug("Filled selector %s with %s", selector, value)
        return True
    except PlaywrightTimeoutError:
        return False
    except Exception:  # pragma: no cover - defensive path
        logging.debug("Failed to fill selector %s", selector, exc_info=True)
        return False


def ensure_store_selected(page, store_query: str) -> None:
    candidate_texts = [
        "Choose store",
        "Choose your store",
        "Select store",
        "Change store",
        "Store",
        "Pick up in store",
        "Select a store",
        "Magasin",
        "Choisir un magasin",
        "Sélectionner un magasin",
    ]
    for text in candidate_texts:
        if try_click(page, f"button:has-text('{text}')"):
            break
    search_selectors = [
        "input[type='search']",
        "input[role='searchbox']",
        "input[role='combobox']",
        "input[placeholder*='store']",
        "input[placeholder*='magasin']",
        "input[placeholder*='city']",
    ]
    for selector in search_selectors:
        if try_fill(page, selector, store_query):
            break
    for variant in {store_query, "Prévost", "Prevost"}:
        if try_click(page, f"text=/{variant}/i"):
            break
    confirm_texts = [
        "Confirm",
        "Confirmer",
        "Set store",
        "Select store",
        "Use this store",
        "Apply",
        "Continuer",
    ]
    for text in confirm_texts:
        if try_click(page, f"button:has-text('{text}')"):
            break


def dismiss_banners(page) -> None:
    if page is None:
        return
    buttons = [
        "button:has-text('Accept all')",
        "button:has-text('Accept all cookies')",
        "button:has-text('Allow all')",
        "button:has-text('J'accepte')",
        "button:has-text('OK')",
        "button:has-text('Continue')",
        "button:has-text('Fermer')",
    ]
    for selector in buttons:
        try_click(page, selector, timeout=2000)


def scroll_page(page) -> None:
    if page is None:
        return
    for step in range(max(SCROLL_STEPS, 1)):
        try:
            page.mouse.wheel(0, 1600)
            page.wait_for_timeout(350)
        except PlaywrightTimeoutError:
            break
        except Exception:  # pragma: no cover - defensive path
            logging.debug("Scrolling step %s failed", step, exc_info=True)
            break


def fetch_with_playwright(url: str, store_query: str) -> str:
    if sync_playwright is None:
        raise RuntimeError("Playwright is not installed. Install playwright to enable dynamic scraping.")
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=PLAYWRIGHT_HEADLESS)
        context = browser.new_context(user_agent=USER_AGENT)
        page = context.new_page()
        logging.info("Fetching %s via Playwright", url)
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=REQUEST_TIMEOUT * 1000)
        except PlaywrightTimeoutError as exc:
            logging.warning("Initial navigation timeout: %s", exc)
        dismiss_banners(page)
        ensure_store_selected(page, store_query)
        with suppress(PlaywrightTimeoutError):
            page.wait_for_load_state("networkidle", timeout=REQUEST_TIMEOUT * 1000)
        scroll_page(page)
        with suppress(PlaywrightTimeoutError):
            page.wait_for_load_state("networkidle", timeout=REQUEST_TIMEOUT * 1000)
        content = page.content()
        browser.close()
    return content


def fetch_html(url: str, store_query: str) -> str:
    if USE_PLAYWRIGHT:
        try:
            return fetch_with_playwright(url, store_query)
        except Exception:
            logging.exception("Playwright scraping failed, falling back to requests")
    return fetch_with_requests(url)


def extract_image_url(container, base_url: str) -> Optional[str]:
    if container is None:
        return None
    image_tag = container.find("img")
    if not image_tag:
        return None
    for attribute in ("data-src", "data-original", "data-srcset", "data-lazy", "srcset", "src"):
        value = image_tag.get(attribute)
        if not value:
            continue
        if "srcset" in attribute:
            candidate = value.split(",")[0].strip().split(" ")[0]
        else:
            candidate = value
        if candidate:
            return urljoin(base_url, candidate)
    return None


def find_price_candidates(container) -> List[str]:
    texts: List[str] = []
    if container is None:
        return texts
    selectors = [
        "[class*='price']",
        "[class*='Price']",
        "[data-price]",
        "[data-testid*='price']",
        "[itemprop='price']",
    ]
    for selector in selectors:
        for element in container.select(selector):
            text = element.get_text(" ", strip=True)
            if text and any(char.isdigit() for char in text):
                texts.append(text)
    if not texts:
        fallback_text = container.get_text(" ", strip=True)
        if fallback_text and any(
            "$" in fragment or "CAD" in fragment.upper() or "C$" in fragment
            for fragment in fallback_text.split()
        ):
            texts.append(fallback_text)
    return texts


def to_float(value: str) -> Optional[float]:
    cleaned = CURRENCY_PATTERN.sub("", value)
    if not cleaned:
        return None
    cleaned = cleaned.replace(",", ".")
    if cleaned.count(".") > 1:
        whole, decimal = cleaned.rsplit(".", 1)
        cleaned = f"{whole.replace('.', '')}.{decimal}"
    try:
        return float(cleaned)
    except ValueError:
        return None


def parse_price_values(texts: Iterable[str]) -> tuple[Optional[float], Optional[float]]:
    values: List[float] = []
    for text in texts:
        for match in PRICE_PATTERN.findall(text):
            amount = to_float(match)
            if amount is not None:
                values.append(amount)
    if not values:
        return None, None
    if len(values) == 1:
        return values[0], values[0]
    highest = max(values)
    lowest = min(values)
    if highest == lowest:
        return highest, lowest
    return highest, lowest


def parse_products(html: str, base_url: str) -> List[Product]:
    soup = BeautifulSoup(html, "html.parser")
    candidates = soup.select("a[href*='/products/']")
    products: List[Product] = []
    seen_urls: set[str] = set()
    for anchor in candidates:
        href = anchor.get("href")
        if not href:
            continue
        full_url = urljoin(base_url, href)
        if full_url in seen_urls:
            continue
        title = anchor.get_text(" ", strip=True)
        if not title:
            continue
        container = anchor
        # Walk up a few levels to capture the full product card (heuristic).
        for _ in range(4):
            parent = container.parent
            if parent is None:
                break
            classes = parent.get("class") or []
            if parent.name in {"li", "article", "div", "section"} and any(
                "product" in cls.lower() or "card" in cls.lower() for cls in classes
            ):
                container = parent
                break
            container = parent
        price_texts = find_price_candidates(container)
        regular, sale = parse_price_values(price_texts)
        image = extract_image_url(container, base_url)
        products.append(Product(title=title, url=full_url, image=image, price=regular, sale_price=sale))
        seen_urls.add(full_url)
    logging.info("Extracted %s potential products", len(products))
    return products


def write_json(items: Iterable[dict], destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    data = list(items)
    destination.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    logging.info("Saved %s products to %s", len(data), destination)


def post_to_api(items: Iterable[dict]) -> None:
    if not API_URL:
        logging.info("ECONODEAL_API_URL is not configured; skipping upload.")
        return
    headers = {"Content-Type": "application/json"}
    if API_TOKEN:
        headers["Authorization"] = f"Bearer {API_TOKEN}"
    payload = list(items)
    response = requests.post(API_URL, json=payload, headers=headers, timeout=REQUEST_TIMEOUT)
    response.raise_for_status()
    logging.info("Uploaded %s products to %s (status %s)", len(payload), API_URL, response.status_code)


def confirm_action(count: int, *, auto_confirm: bool) -> bool:
    if auto_confirm:
        logging.info("Auto confirmation enabled – proceeding without manual prompt.")
        return True
    if not sys.stdin.isatty():
        logging.warning("Interactive confirmation required but stdin is not a TTY.")
        return False
    prompt = f"Proceed with saving and uploading {count} products for Prevost? [y/N]: "
    try:
        answer = input(prompt)
    except EOFError:
        return False
    normalized = answer.strip().lower()
    return normalized in {"y", "yes", "o", "oui"}


def main(argv: Optional[Iterable[str]] = None) -> int:
    args = parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    html = fetch_html(args.url, args.store_query)
    products = parse_products(html, args.url)
    products = [product for product in products if product.title and product.url]
    if not products:
        logging.error("No products were extracted from %s", args.url)
        return 1

    payload = [product.to_payload(args.store, args.city) for product in products]
    logging.info("Prepared payload with %s products", len(payload))

    auto_confirm = AUTO_CONFIRM_ENV or args.yes
    if not confirm_action(len(payload), auto_confirm=auto_confirm):
        logging.warning("Operation aborted by the operator. No data was written or uploaded.")
        return 2

    write_json(payload, args.output)
    if not args.no_upload:
        try:
            post_to_api(payload)
        except requests.RequestException as exc:
            logging.error("API upload failed: %s", exc)
            return 3
    return 0


if __name__ == "__main__":
    sys.exit(main())
