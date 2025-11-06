"""Scraper for Sporting Life clearance products.

This script uses Selenium to collect the products listed on
https://www.sportinglife.ca/fr-CA/liquidation/ and stores the results
in ``sporting_life_products.json``. The scraper is intentionally built
with forgiving CSS selectors so that small visual changes on the site do
not immediately break the extraction.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from dataclasses import asdict, dataclass
from typing import Iterable, List, Optional

from selenium import webdriver
from selenium.common.exceptions import NoSuchElementException, TimeoutException
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webelement import WebElement
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from webdriver_manager.chrome import ChromeDriverManager

PRODUCT_SELECTORS: tuple[str, ...] = (
    "[data-testid='product-tile']",
    "div.product-tile",
    "div.product-card",
    "div.product-item",
    "li.product-tile",
)
TITLE_SELECTORS: tuple[str, ...] = (
    ".product-title",
    "h3",
    ".name",
    "a[aria-label]",
)
ORIGINAL_PRICE_SELECTORS: tuple[str, ...] = (
    ".original-price",
    ".price-strikethrough",
    ".price-original",
)
SALE_PRICE_SELECTORS: tuple[str, ...] = (
    ".sale-price",
    ".current-price",
    ".price",
    ".price-sales",
)
NEXT_BUTTON_SELECTORS: tuple[str, ...] = (
    "[data-testid='pagination-button-next']",
    "button[aria-label='Page suivante']",
    "a[aria-label='Page suivante']",
    "button[aria-label='Suivant']",
    "a.pagination__button--next",
    "button.pagination__button--next",
    ".pagination-next a",
)


@dataclass
class Product:
    """Simple representation of a product extracted from the listing."""

    title: str
    sale_price: str
    original_price: str
    image_url: str
    url: str


def _join_selectors(selectors: Iterable[str]) -> str:
    return ", ".join(selectors)


def _get_browser_version(chrome_binary: Optional[str]) -> Optional[str]:
    """Return the full version string of the available Chrome binary."""

    candidates = []
    if chrome_binary:
        candidates.append(chrome_binary)

    candidates.extend(
        filter(
            None,
            (
                shutil.which(name)
                for name in (
                    "google-chrome",
                    "google-chrome-stable",
                    "chromium",
                    "chromium-browser",
                )
            ),
        )
    )

    for binary in candidates:
        try:
            result = subprocess.run(
                [binary, "--version"],
                check=True,
                capture_output=True,
                text=True,
            )
        except (FileNotFoundError, subprocess.CalledProcessError):
            continue

        match = re.search(r"(\d+\.\d+\.\d+\.\d+)", result.stdout)
        if match:
            return match.group(1)

    return None


def _configure_driver() -> webdriver.Chrome:
    """Initialise a headless Chrome driver that works on CI environments."""

    chrome_options = Options()
    chrome_options.add_argument("--headless=new")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--window-size=1920,1080")

    chrome_binary = os.environ.get("CHROME_PATH")
    if chrome_binary:
        chrome_options.binary_location = chrome_binary

    browser_version = _get_browser_version(chrome_binary)
    if browser_version:
        service = Service(ChromeDriverManager(version=browser_version).install())
    else:
        service = Service(ChromeDriverManager().install())

    return webdriver.Chrome(service=service, options=chrome_options)


def _find_first_text(element: WebElement, selectors: Iterable[str]) -> Optional[str]:
    for selector in selectors:
        try:
            sub_element = element.find_element(By.CSS_SELECTOR, selector)
            text = sub_element.text.strip()
            if text:
                return text
        except NoSuchElementException:
            continue
    return None


def _find_first_attr(element: WebElement, selectors: Iterable[str], attribute: str) -> Optional[str]:
    for selector in selectors:
        try:
            sub_element = element.find_element(By.CSS_SELECTOR, selector)
            value = sub_element.get_attribute(attribute)
            if value:
                return value
        except NoSuchElementException:
            continue
    return None


def _extract_product(element: WebElement) -> Optional[Product]:
    title = _find_first_text(element, TITLE_SELECTORS)
    sale_price = _find_first_text(element, SALE_PRICE_SELECTORS)
    if not title or not sale_price:
        return None

    original_price = _find_first_text(element, ORIGINAL_PRICE_SELECTORS) or ""

    image_url = _find_first_attr(element, ("img",), "src") or ""

    url = _find_first_attr(element, ("a",), "href") or ""
    if url.startswith("/"):
        url = f"https://www.sportinglife.ca{url}"

    return Product(
        title=title,
        sale_price=sale_price,
        original_price=original_price,
        image_url=image_url,
        url=url,
    )


def _pagination_button_enabled(button: WebElement) -> bool:
    classes = (button.get_attribute("class") or "").lower()
    aria_disabled = (button.get_attribute("aria-disabled") or "").lower()
    return "disabled" not in classes and aria_disabled not in {"true", "1", "yes"}


def _go_to_next_page(driver: webdriver.Chrome, wait: WebDriverWait, reference_element: WebElement) -> bool:
    for selector in NEXT_BUTTON_SELECTORS:
        try:
            button = driver.find_element(By.CSS_SELECTOR, selector)
        except NoSuchElementException:
            continue

        if not _pagination_button_enabled(button):
            continue

        driver.execute_script("arguments[0].click();", button)
        try:
            wait.until(EC.staleness_of(reference_element))
            wait.until(
                EC.presence_of_element_located(
                    (By.CSS_SELECTOR, _join_selectors(PRODUCT_SELECTORS))
                )
            )
            return True
        except TimeoutException:
            return False
    return False


def scrape_sporting_life() -> List[Product]:
    driver = _configure_driver()
    wait = WebDriverWait(driver, 15)

    try:
        driver.get("https://www.sportinglife.ca/fr-CA/liquidation/")
        wait.until(
            EC.presence_of_element_located((By.CSS_SELECTOR, _join_selectors(PRODUCT_SELECTORS)))
        )

        products: List[Product] = []
        seen_urls: set[str] = set()

        while True:
            elements = driver.find_elements(By.CSS_SELECTOR, _join_selectors(PRODUCT_SELECTORS))
            if not elements:
                break

            for element in elements:
                product = _extract_product(element)
                if not product:
                    continue

                if product.url and product.url in seen_urls:
                    continue
                if product.url:
                    seen_urls.add(product.url)

                products.append(product)

            reference_element = elements[0]
            if not _go_to_next_page(driver, wait, reference_element):
                break

        return products
    finally:
        driver.quit()


def save_products_to_json(products: Iterable[Product], path: str = "sporting_life_products.json") -> None:
    serialisable = [asdict(product) for product in products]
    with open(path, "w", encoding="utf-8") as file:
        json.dump(serialisable, file, ensure_ascii=False, indent=2)


def main() -> None:
    try:
        products = scrape_sporting_life()
    except TimeoutException:
        print("Erreur : Timeout lors du chargement de la page.")
        return
    except Exception as exc:  # noqa: BLE001 - keep generic for CLI output
        print(f"Erreur inattendue : {exc}")
        return

    save_products_to_json(products)
    print(
        f"Scraping terminé : {len(products)} produits extraits et sauvegardés dans sporting_life_products.json"
    )


if __name__ == "__main__":
    main()
