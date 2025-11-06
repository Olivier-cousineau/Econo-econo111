"""Scraper Sporting Life Liquidation.

This script loads the Sporting Life liquidation page, expands the dynamic
catalogue by interacting with the "Voir plus" button and exports the products
as CSV or JSON depending on the requested output path.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
import time
from pathlib import Path
from typing import Dict, List

from selenium import webdriver
from selenium.common.exceptions import (
    ElementClickInterceptedException,
    ElementNotInteractableException,
    NoSuchElementException,
    StaleElementReferenceException,
    TimeoutException,
)
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

DEFAULT_URL = "https://www.sportinglife.ca/fr-CA/liquidation/"
PRODUCT_TILE_SELECTOR = ".product-tile"
SHOW_MORE_XPATH = "//button[contains(.,'Voir plus')]"
FIELD_NAMES = ["name", "original_price", "sale_price", "discount", "url"]


def parse_args(argv: List[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Scrape Sporting Life liquidation listings into a file."
    )
    parser.add_argument(
        "--url",
        default=DEFAULT_URL,
        help="Page de départ à analyser (défaut: %(default)s)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("sportinglife_liquidation.csv"),
        help="Chemin du fichier de sortie (CSV ou JSON).",
    )
    parser.add_argument(
        "--max-clicks",
        type=int,
        default=50,
        help="Nombre maximum de clics sur le bouton 'Voir plus'.",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=2.0,
        help="Pause (en secondes) entre chaque clic sur 'Voir plus'.",
    )
    parser.add_argument(
        "--page-timeout",
        type=int,
        default=30,
        help="Délai maximum pour l'apparition des produits (secondes).",
    )
    parser.add_argument(
        "--no-headless",
        action="store_true",
        help="Désactive le mode headless de Chrome.",
    )
    return parser.parse_args(argv)


def build_chrome_options(headless: bool) -> Options:
    options = Options()
    if headless:
        options.add_argument("--headless=new")
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--window-size=1920,1080")
    return options


def wait_for_products(driver: webdriver.Chrome, timeout: int) -> None:
    WebDriverWait(driver, timeout).until(
        EC.presence_of_all_elements_located((By.CSS_SELECTOR, PRODUCT_TILE_SELECTOR))
    )


def scroll_and_click_show_more(
    driver: webdriver.Chrome, max_clicks: int, delay: float
) -> None:
    clicks = 0
    while clicks < max_clicks:
        try:
            button = driver.find_element(By.XPATH, SHOW_MORE_XPATH)
        except NoSuchElementException:
            break

        try:
            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", button)
            button.click()
            clicks += 1
            time.sleep(delay)
        except (ElementNotInteractableException, ElementClickInterceptedException):
            # Le bouton n'est plus disponible ou cliquable.
            break


def safe_text(element, selector: str) -> str:
    try:
        value = element.find_element(By.CSS_SELECTOR, selector).text
        return value.strip()
    except (NoSuchElementException, StaleElementReferenceException):
        return ""


def safe_href(element, selector: str = "a") -> str:
    try:
        link = element.find_element(By.CSS_SELECTOR, selector)
        href = link.get_attribute("href")
        return href or ""
    except (NoSuchElementException, StaleElementReferenceException):
        return ""


def scrape_products(driver: webdriver.Chrome) -> List[Dict[str, str]]:
    products: List[Dict[str, str]] = []
    tiles = driver.find_elements(By.CSS_SELECTOR, PRODUCT_TILE_SELECTOR)
    for tile in tiles:
        product = {
            "name": safe_text(tile, ".product-name"),
            "original_price": safe_text(tile, ".original-price"),
            "sale_price": safe_text(tile, ".sale-price"),
            "discount": safe_text(tile, ".discount"),
            "url": safe_href(tile),
        }
        products.append(product)
    return products


def export_products(products: List[Dict[str, str]], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if output_path.suffix.lower() == ".json":
        output_path.write_text(
            json.dumps(products, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        return

    with output_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELD_NAMES)
        writer.writeheader()
        for product in products:
            writer.writerow(product)


def run_scraper(args: argparse.Namespace) -> int:
    options = build_chrome_options(headless=not args.no_headless)
    try:
        with webdriver.Chrome(options=options) as driver:
            driver.get(args.url)
            wait_for_products(driver, args.page_timeout)
            scroll_and_click_show_more(driver, args.max_clicks, args.delay)
            products = scrape_products(driver)
    except TimeoutException:
        print("Aucun produit trouvé avant expiration du délai.", file=sys.stderr)
        return 1

    export_products(products, args.output)
    print(f"Export de {len(products)} produits vers {args.output}")
    return 0


def main(argv: List[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    return run_scraper(args)


if __name__ == "__main__":
    raise SystemExit(main())
