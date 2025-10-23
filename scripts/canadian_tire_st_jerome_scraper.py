"""Canadian Tire category scraper for the Saint-Jérôme store."""
from __future__ import annotations

import argparse
import csv
import dataclasses
import json
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Sequence

from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.chrome.options import Options as ChromeOptions
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from webdriver_manager.chrome import ChromeDriverManager


DEFAULT_CATEGORY_URL = "https://www.canadiantire.ca/en/cat/tools-hardware/power-tools/saws-DC0002013.html"
DEFAULT_OUTPUT = Path("data/canadian-tire/saint-jerome.csv")
DEFAULT_STORE_ID = "046"
DEFAULT_STORE_NAME = "Saint-Jérôme"
DEFAULT_PROVINCE_CODE = "QC"

_PRODUCT_CARD_SELECTORS = (
    "div.product__list-item",
    "li.product__list-item",
    "li.product-list__item",
    "div.product-tile",
    "div.plp-product-card",
)
_TITLE_SELECTORS = (
    ".product__title",
    "[data-testid='product-name']",
    "h3",
)
_PRICE_SELECTORS = (
    ".price__value",
    ".money-price__integer",
    ".price",
)
_LINK_SELECTORS = (
    "a.product__link",
    "a[href]",
)
_IMAGE_SELECTORS = (
    "img.product__image",
    "img[data-testid='product-image']",
    "img",
)

_CONSENT_SELECTORS = (
    "button#onetrust-accept-btn-handler",
    "button[data-testid='onetrust-accept-btn']",
    "button[data-tracking-label='accept all cookies']",
    "button[data-testid='privacy-settings-accept']",
)

_LOAD_MORE_SELECTORS = (
    "button[data-testid='load-more']",
    "button.load-more__button",
    "button[data-test='load-more']",
)


@dataclass
class Product:
    name: str
    price: str
    link: str
    image: str

    @classmethod
    def from_card(cls, card: BeautifulSoup, base_url: str) -> "Product":
        def pick_text(selectors: Sequence[str]) -> str:
            for selector in selectors:
                element = card.select_one(selector)
                if element and element.get_text(strip=True):
                    return element.get_text(strip=True)
            return ""

        def pick_link(selectors: Sequence[str]) -> str:
            for selector in selectors:
                element = card.select_one(selector)
                if element and element.get("href"):
                    href = element["href"]
                    if href.startswith("http"):
                        return href
                    return base_url.rstrip("/") + href
            return ""

        def pick_image(selectors: Sequence[str]) -> str:
            for selector in selectors:
                element = card.select_one(selector)
                if element:
                    for attr in ("data-src", "data-lazy", "srcset", "src"):
                        value = element.get(attr)
                        if value:
                            return value.split()[0]
            return ""

        return cls(
            name=pick_text(_TITLE_SELECTORS),
            price=pick_text(_PRICE_SELECTORS),
            link=pick_link(_LINK_SELECTORS),
            image=pick_image(_IMAGE_SELECTORS),
        )


def build_driver(headless: bool = True) -> webdriver.Chrome:
    options = ChromeOptions()
    if headless:
        options.add_argument("--headless=new")
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--lang=fr-CA")
    options.add_argument(
        "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"
    )
    driver = webdriver.Chrome(
        service=ChromeService(ChromeDriverManager().install()), options=options
    )
    return driver


def accept_cookies(driver: webdriver.Chrome, timeout: int = 15) -> None:
    for selector in _CONSENT_SELECTORS:
        try:
            button = WebDriverWait(driver, timeout).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, selector))
            )
        except TimeoutException:
            continue
        else:
            try:
                button.click()
                time.sleep(0.5)
            except Exception:
                pass
            finally:
                break


def apply_store_preference(
    driver: webdriver.Chrome,
    store_id: str,
    store_name: str,
    province_code: str,
) -> None:
    """Prime the session with the Saint-Jérôme store preference."""

    base_url = "https://www.canadiantire.ca"
    driver.get(base_url)
    accept_cookies(driver)

    cookie_payloads = [
        {"name": "prefStore", "value": store_id},
        {"name": "preferredStore", "value": store_id},
        {"name": "prefStoreName", "value": store_name},
        {"name": "prefStoreProvince", "value": province_code},
    ]
    for payload in cookie_payloads:
        driver.delete_cookie(payload["name"])
        driver.add_cookie({**payload, "domain": ".canadiantire.ca", "path": "/"})

    store_info = {
        "id": store_id,
        "name": store_name,
        "province": province_code,
    }
    script = (
        "try {"
        "const store = arguments[0];"
        "localStorage.setItem('preferredStore', JSON.stringify(store));"
        "sessionStorage.setItem('preferredStore', JSON.stringify(store));"
        "document.cookie = `prefStore=${store.id};path=/;domain=.canadiantire.ca`;"
        "} catch (error) { console.warn('Failed to persist store preference', error); }"
    )
    driver.execute_script(script, store_info)


def _click_load_more(driver: webdriver.Chrome) -> bool:
    for selector in _LOAD_MORE_SELECTORS:
        try:
            button = WebDriverWait(driver, 3).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, selector))
            )
        except TimeoutException:
            continue
        except Exception:
            continue
        else:
            try:
                button.click()
                time.sleep(1.0)
                return True
            except Exception:
                continue
    return False


def _scroll_to_bottom(driver: webdriver.Chrome, max_rounds: int = 8) -> None:
    for _ in range(max_rounds):
        previous_height = driver.execute_script("return document.body.scrollHeight")
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(0.75)
        if not _click_load_more(driver):
            time.sleep(0.75)
        new_height = driver.execute_script("return document.body.scrollHeight")
        if new_height == previous_height:
            break


def collect_products(html: str, base_url: str) -> List[Product]:
    soup = BeautifulSoup(html, "html.parser")
    cards: List[BeautifulSoup] = []
    for selector in _PRODUCT_CARD_SELECTORS:
        cards = soup.select(selector)
        if cards:
            break
    products: List[Product] = []
    for card in cards:
        products.append(Product.from_card(card, base_url))
    if products:
        return products

    data_script = soup.select_one("script#__NEXT_DATA__")
    if data_script and data_script.string:
        try:
            payload = json.loads(data_script.string)
        except json.JSONDecodeError:
            return products
        product_entries = _extract_products_from_payload(payload)
        for entry in product_entries:
            products.append(entry)
    return products


def _extract_products_from_payload(payload: dict) -> Iterable[Product]:
    product_nodes: List[dict] = []
    potential_paths = [
        ["props", "pageProps", "initialState", "productListing", "products"],
        ["props", "pageProps", "productListing", "products"],
        ["props", "pageProps", "initialState", "results"],
    ]
    for path in potential_paths:
        node = payload
        for key in path:
            if not isinstance(node, dict):
                break
            node = node.get(key)
        else:
            if isinstance(node, list):
                product_nodes = node
                break
    for item in product_nodes:
        if not isinstance(item, dict):
            continue
        name = _safe_get(item, ("name",))
        price = _safe_get(item, ("price", "current")) or _safe_get(
            item, ("pricing", "price")
        )
        link = _safe_get(item, ("productUrl",)) or _safe_get(item, ("url",))
        image = _safe_get(item, ("image",))
        yield Product(
            name=name or "",
            price=str(price or ""),
            link=link or "",
            image=image or "",
        )


def _safe_get(node: dict, path: Sequence[str]) -> str:
    value = node
    for key in path:
        if not isinstance(value, dict):
            return ""
        value = value.get(key)
    if isinstance(value, (str, int, float)):
        return str(value)
    return ""


def scrape_category(
    url: str,
    store_id: str,
    store_name: str,
    province_code: str,
    headless: bool,
) -> List[Product]:
    driver = build_driver(headless=headless)
    try:
        apply_store_preference(driver, store_id, store_name, province_code)
        driver.get(url)
        WebDriverWait(driver, 30).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, ", ".join(_PRODUCT_CARD_SELECTORS)))
        )
        _scroll_to_bottom(driver)
        html = driver.page_source
        products = collect_products(html, base_url="https://www.canadiantire.ca")
        return products
    finally:
        driver.quit()


def write_products(products: Iterable[Product], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["name", "price", "link", "image"])
        writer.writeheader()
        for product in products:
            writer.writerow(dataclasses.asdict(product))


def parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Scrape Canadian Tire category listings for the Saint-Jérôme store"
    )
    parser.add_argument(
        "--url",
        default=DEFAULT_CATEGORY_URL,
        help="Canadian Tire category URL to scrape",
    )
    parser.add_argument(
        "--output",
        default=str(DEFAULT_OUTPUT),
        help="Destination CSV file",
    )
    parser.add_argument(
        "--store-id",
        default=DEFAULT_STORE_ID,
        help="Canadian Tire store identifier (Saint-Jérôme = 046)",
    )
    parser.add_argument(
        "--store-name",
        default=DEFAULT_STORE_NAME,
        help="Store display name",
    )
    parser.add_argument(
        "--province",
        default=DEFAULT_PROVINCE_CODE,
        help="Province code for the preferred store",
    )
    parser.add_argument(
        "--no-headless",
        action="store_true",
        help="Run Chrome with a visible window",
    )
    return parser.parse_args(list(argv))


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv if argv is not None else sys.argv[1:])
    products = scrape_category(
        url=args.url,
        store_id=args.store_id,
        store_name=args.store_name,
        province_code=args.province,
        headless=not args.no_headless,
    )
    write_products(products, Path(args.output))
    print(f"Scraping terminé. {len(products)} produits sauvegardés dans {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
