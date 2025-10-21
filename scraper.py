"""Sporting Life clearance scraper.

This script retrieves product data from the Sporting Life clearance
collection and stores it in ``data/sporting-life/liquidation.json``.

If ``ECONODEAL_API_URL`` is defined, the collected items are also sent to
that endpoint as JSON. Optionally, an ``ECONODEAL_API_TOKEN`` can be
provided to populate an ``Authorization`` header using the ``Bearer``
scheme. This makes the script compatible with a Vercel serverless
function or any other lightweight API the site exposes.
"""
from __future__ import annotations

import datetime as _dt
import json
import logging
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Iterable, List, Optional
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

try:
    from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError
except ImportError:  # pragma: no cover - dependency is optional at runtime
    PlaywrightTimeoutError = Exception  # type: ignore[assignment]
    sync_playwright = None  # type: ignore[assignment]

SPORTING_LIFE_URL = os.getenv(
    "SPORTING_LIFE_URL", "https://www.sportinglife.ca/fr-CA/liquidation/"
)
DEFAULT_OUTPUT_PATH = (
    Path(__file__).resolve().parent / "data" / "sporting-life" / "liquidation.json"
)
OUTPUT_PATH = Path(os.getenv("SPORTING_LIFE_OUTPUT", str(DEFAULT_OUTPUT_PATH)))
STORE_NAME = os.getenv("SPORTING_LIFE_STORE", "Sporting Life")
DEFAULT_CITY = os.getenv("SPORTING_LIFE_CITY", "online")
USER_AGENT = os.getenv(
    "SPORTING_LIFE_USER_AGENT",
    (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"
    ),
)
REQUEST_TIMEOUT = int(os.getenv("SPORTING_LIFE_TIMEOUT", "30"))
PLAYWRIGHT_TIMEOUT = int(
    os.getenv("SPORTING_LIFE_PLAYWRIGHT_TIMEOUT", str(REQUEST_TIMEOUT * 1000))
)
USE_PLAYWRIGHT = os.getenv("SPORTING_LIFE_USE_PLAYWRIGHT", "1").lower() not in {
    "0",
    "false",
    "no",
}

_PLAYWRIGHT_BROWSERS_READY = False


def ensure_playwright_browsers_installed() -> None:
    """Ensure Playwright browsers are available locally.

    The command ``python -m playwright install --with-deps`` installs both the
    browser binaries and the system dependencies required on Linux runners.
    When run outside CI this flag may fail (for example without ``sudo``
    privileges), so we fall back to ``python -m playwright install`` which only
    downloads the browser binaries. Both commands are idempotent and cheap to
    re-run, so this helper keeps a module-level flag to avoid redundant calls in
    a single process.
    """

    global _PLAYWRIGHT_BROWSERS_READY

    if _PLAYWRIGHT_BROWSERS_READY:
        return

    if sync_playwright is None:  # pragma: no cover - optional dependency path
        raise RuntimeError("Playwright is not installed")

    commands = [
        [sys.executable, "-m", "playwright", "install", "--with-deps"],
        [sys.executable, "-m", "playwright", "install"],
    ]

    last_error: Optional[subprocess.CalledProcessError] = None
    for command in commands:
        try:
            logging.info("Ensuring Playwright browsers are installed: %s", " ".join(command))
            result = subprocess.run(
                command,
                check=True,
                capture_output=True,
                text=True,
            )
            if result.stdout:
                logging.debug(result.stdout)
            if result.stderr:
                logging.debug(result.stderr)
            _PLAYWRIGHT_BROWSERS_READY = True
            return
        except FileNotFoundError as exc:  # pragma: no cover - dependency path
            raise RuntimeError(
                "Unable to find the Playwright executable. Did you install the package?"
            ) from exc
        except subprocess.CalledProcessError as exc:
            last_error = exc
            logging.warning(
                "Playwright installation command failed (%s).", " ".join(command)
            )
            if exc.stdout:
                logging.debug(exc.stdout)
            if exc.stderr:
                logging.debug(exc.stderr)

    raise RuntimeError("Playwright browsers could not be installed") from last_error


def load_all_products(page, max_clicks=500):
    """
    Clique 'SHOW MORE' en boucle jusqu'à disparition/disabled du bouton
    ou jusqu'à ce que le nombre de tuiles n'augmente plus.
    """
    # ferme le bandeau cookies si présent (FR/EN)
    try:
        cookie_btn = page.locator("button:has-text('Accepter'), button:has-text('Accept')")
        if cookie_btn.count() > 0:
            cookie_btn.first.click(timeout=3000)
    except Exception:
        pass

    # helper: compter les tuiles de produits
    def tiles_count():
        return page.evaluate(
            "sel => document.querySelectorAll(sel).length",
            "div.plp-product-tile, div.product-tile, li.product-grid__item"
        )

    last = tiles_count()
    print(f"DEBUG: initial tiles = {last}")

    for i in range(max_clicks):
        btn = page.locator(
            "button:has-text('SHOW MORE'), button:has-text('Show More'), "
            "button.load-more, [role='button']:has-text('Show More')"
        )
        if btn.count() == 0 or (btn.first.is_enabled() is False):
            print("DEBUG: no more button or disabled -> stop.")
            break

        # amener le bouton en vue et cliquer
        btn.first.scroll_into_view_if_needed()
        btn.first.click()

        # attendre que le nombre d’items augmente
        increased = False
        try:
            page.wait_for_function(
                """(prev) => {
                    const sel = "div.plp-product-tile, div.product-tile, li.product-grid__item";
                    return document.querySelectorAll(sel).length > prev;
                }""",
                arg=last,
                timeout=15000
            )
            increased = True
        except PlaywrightTimeoutError:
            # si c'est juste lent, on attend le calme réseau et on re-vérifie
            try:
                page.wait_for_load_state("networkidle", timeout=10000)
            except PlaywrightTimeoutError:
                pass

        new_count = tiles_count()
        print(f"DEBUG: click {i+1}: {new_count} tiles")

        if new_count > last:
            last = new_count
            continue

        if not increased or new_count <= last:
            print("DEBUG: tiles did not increase -> stop.")
            break


API_URL = os.getenv("ECONODEAL_API_URL")
API_TOKEN = os.getenv("ECONODEAL_API_TOKEN")


def fetch_html_with_requests(url: str) -> str:
    """Return the HTML payload for *url* using a direct HTTP request."""
    logging.info("Fetching Sporting Life clearance page via requests: %s", url)
    response = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=REQUEST_TIMEOUT)
    response.raise_for_status()
    return response.text


def fetch_html_with_playwright(url: str) -> str:
    """Return the rendered HTML payload for *url* using Playwright."""

    if sync_playwright is None:  # pragma: no cover - optional dependency path
        raise RuntimeError("Playwright is not installed")

    ensure_playwright_browsers_installed()

    logging.info("Fetching Sporting Life clearance page via Playwright: %s", url)
    browser = None
    context = None
    content: Optional[str] = None
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            context = browser.new_context(user_agent=USER_AGENT)
            page = context.new_page()
            page.goto(url, wait_until="networkidle", timeout=PLAYWRIGHT_TIMEOUT)
            try:
                page.wait_for_load_state("networkidle", timeout=PLAYWRIGHT_TIMEOUT)
            except PlaywrightTimeoutError:
                logging.debug("Network idle state timeout for %s", url)

            load_all_products(page)

            product_tile_selector = (
                "div.plp-product-tile, div.product-tile, li.product-grid__item"
            )

            try:
                page.wait_for_selector(product_tile_selector, timeout=PLAYWRIGHT_TIMEOUT)
            except PlaywrightTimeoutError:
                logging.warning("Timed out waiting for product tiles on %s", url)

            try:
                tile_count = page.evaluate(
                    """(selector) => document.querySelectorAll(selector).length""",
                    product_tile_selector,
                )
            except Exception:
                tile_count = 0
                logging.debug(
                    "Unable to count product tiles after loading Sporting Life page",
                    exc_info=True,
                )

            logging.info("Playwright collected %s product tiles", tile_count)
            content = page.content()
    except PlaywrightTimeoutError as exc:
        logging.error("Playwright timed out fetching %s: %s", url, exc)
        raise
    finally:
        try:
            context.close()
        except Exception:  # pragma: no cover - best effort cleanup
            pass
        try:
            browser.close()
        except Exception:  # pragma: no cover - best effort cleanup
            pass
    if content is None:
        raise RuntimeError("Playwright did not return any page content")
    return content


def fetch_html(url: str) -> str:
    """Return the HTML payload for *url*, attempting to use Playwright if available."""

    if USE_PLAYWRIGHT:
        try:
            return fetch_html_with_playwright(url)
        except Exception:
            logging.exception("Playwright fetch failed, falling back to requests")
    return fetch_html_with_requests(url)


def parse_price(text: Optional[str]) -> Optional[float]:
    """Convert a price string to a ``float``.

    The Sporting Life markup uses the Canadian locale with commas as decimal
    separators. This helper normalizes the value into a Python ``float``.
    """
    if not text:
        return None

    normalized = text.replace("\xa0", "").replace(" ", "")
    normalized = normalized.replace(",", ".")
    normalized = re.sub(r"[^0-9.]+", "", normalized)
    if normalized.count(".") > 1:
        whole, decimal = normalized.rsplit(".", 1)
        normalized = f"{whole.replace('.', '')}.{decimal}"
    try:
        return float(normalized)
    except ValueError:
        logging.debug("Unable to parse price from %r", text)
        return None


def extract_text(element) -> Optional[str]:
    if element is None:
        return None
    text = element.get_text(strip=True)
    return text or None


def extract_image_url(product) -> Optional[str]:
    image_tag = product.select_one("img")
    if not image_tag:
        return None
    for attribute in ("data-src", "data-original", "data-srcset", "src"):
        value = image_tag.get(attribute)
        if value:
            # If the image uses ``srcset`` we take the first candidate.
            if attribute.endswith("srcset"):
                value = value.split(",")[0].strip().split(" ")[0]
            return urljoin(SPORTING_LIFE_URL, value)
    return None


def parse_products(html):
    soup = BeautifulSoup(html, "html.parser")
    tiles = soup.select("div.product-tile, div.plp-product-tile, li.product-grid__item")

    print(f"DEBUG: {len(tiles)} raw tiles found")  # pour diagnostic
    products = []

    for tile in tiles:
        name_tag = tile.select_one("a.pdp-link, a.name-link, a.product-name")
        price_tag = tile.select_one(".price-sales, .product-sales-price, .price__sale")

        name = name_tag.get_text(strip=True) if name_tag else None
        price = price_tag.get_text(strip=True) if price_tag else None
        link = name_tag.get("href") if name_tag else None
        image = extract_image_url(tile)

        if link:
            link = urljoin(SPORTING_LIFE_URL, link)

        if name:
            products.append(
                {
                    "nom": name,
                    "prix": price,
                    "image": image,
                    "lien": link,
                }
            )

    print(f"DEBUG: {len(products)} products extracted")
    return products


def deduplicate_products(items: Iterable[dict]) -> List[dict]:
    seen: set[str] = set()
    deduped: List[dict] = []
    for item in items:
        link = item.get("lien") or ""
        key = link or item.get("nom") or ""
        if not key:
            continue
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    return deduped


def write_json(items: Iterable[dict], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = list(items)
    logging.info("Writing %s products to %s", len(data), path)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def post_to_api(items: Iterable[dict]) -> None:
    if not API_URL:
        logging.info("No API endpoint configured; skipping upload.")
        return

    headers = {"Content-Type": "application/json"}
    if API_TOKEN:
        headers["Authorization"] = f"Bearer {API_TOKEN}"

    payload = list(items)
    logging.info("Posting %s products to %s", len(payload), API_URL)
    response = requests.post(API_URL, json=payload, headers=headers, timeout=REQUEST_TIMEOUT)
    response.raise_for_status()
    logging.info("Upload successful with status %s", response.status_code)


def configure_logging() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")


def main() -> None:
    configure_logging()
    html = fetch_html(SPORTING_LIFE_URL)
    products = parse_products(html)
    products = deduplicate_products(products)
    if not products:
        with open("debug_sportinglife.html", "w", encoding="utf-8") as f:
            f.write(html)
        print(
            "⚠️ Aucun produit trouvé. Le code HTML a été sauvegardé dans debug_sportinglife.html pour inspection."
        )
        logging.warning("No products were found on %s", SPORTING_LIFE_URL)
    write_json(products, OUTPUT_PATH)
    post_to_api(products)


if __name__ == "__main__":
    main()
