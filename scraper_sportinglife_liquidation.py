"""Utility script to export Sporting Life liquidation listings to CSV.

The retailer renders liquidation listings client side, so the script relies on
Selenium driving a headless Chrome instance. By default it collects the product
name, the current price, the original price and the displayed discount for each
product tile rendered on https://www.sportinglife.ca/fr-CA/liquidation/ and
writes the result to ``data/sporting-life/liquidation.csv``.

Example usage
-------------

Run the scraper with its defaults and override the output file::

    python scraper_sportinglife_liquidation.py --output sportinglife.csv

Disable headless mode to watch the browser session::

    python scraper_sportinglife_liquidation.py --no-headless

The script is intentionally small so it can be scheduled via ``cron`` or the
Windows Task Scheduler. Install ``selenium`` and ensure a compatible Chrome
Driver is accessible in your ``PATH`` before running the script.
"""

from __future__ import annotations

import argparse
import csv
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Sequence, Tuple

from selenium import webdriver
from selenium.common.exceptions import NoSuchElementException, WebDriverException
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By

LISTING_URL = "https://www.sportinglife.ca/fr-CA/liquidation/"
DEFAULT_OUTPUT = Path("data/sporting-life/liquidation.csv")


@dataclass
class ProductRow:
    """Lightweight container for the fields exported to CSV."""

    title: str
    price: str
    old_price: str
    discount: str

    def as_csv_row(self) -> Sequence[str]:
        return (self.title, self.price, self.old_price, self.discount)


PRODUCT_SELECTORS = {
    "title": ".product-name",
    "price": ".product-sales-price",
    "old_price": ".product-standard-price",
    "discount": ".product-savings-percent",
}

LOAD_MORE_LOCATORS: Sequence[Tuple[By, str]] = (
    (By.CSS_SELECTOR, "button.load-more"),
    (By.CSS_SELECTOR, "button[data-action='load-more']"),
    (By.CSS_SELECTOR, "button[data-testid='load-more']"),
    # Sporting Life sometimes renders the control with a French label "Voir plus".
    (By.XPATH, "//button[normalize-space()='Voir plus']"),
    (By.XPATH, "//button[contains(normalize-space(.), 'Voir plus')"]),
    (By.XPATH, "//a[normalize-space()='Voir plus']"),
    (By.XPATH, "//a[contains(normalize-space(.), 'Voir plus')"]),
    # English fallbacks observed on the site.
    (By.XPATH, "//button[normalize-space()='Show more']"),
    (By.XPATH, "//button[normalize-space()='SHOW MORE']"),
    (By.XPATH, "//button[contains(translate(normalize-space(.), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'show more')"]),
    (By.XPATH, "//a[normalize-space()='Show more']"),
    (By.XPATH, "//a[normalize-space()='SHOW MORE']"),
    (By.XPATH, "//a[contains(translate(normalize-space(.), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'show more')"]),
)


def create_driver(*, headless: bool = True) -> webdriver.Chrome:
    """Return a configured Chrome WebDriver instance."""

    options = Options()
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    if headless:
        # ``--headless=new`` is preferred when available, fallback otherwise.
        options.add_argument("--headless=new")
    try:
        return webdriver.Chrome(options=options)
    except WebDriverException as exc:  # pragma: no cover - requires runtime env
        raise SystemExit(f"Failed to initialise Chrome WebDriver: {exc}")


def wait_for_products(driver: webdriver.Chrome, *, wait_seconds: float) -> None:
    """Allow client-side scripts time to populate the product listing."""

    end_time = time.time() + wait_seconds
    while time.time() < end_time:
        tiles = driver.find_elements(By.CSS_SELECTOR, ".product-tile-inner")
        if tiles:
            return
        time.sleep(0.5)


def click_load_more(driver: webdriver.Chrome, *, wait_seconds: float) -> bool:
    """Attempt to click a "load more" control present on the page."""

    for by, selector in LOAD_MORE_LOCATORS:
        try:
            button = driver.find_element(by, selector)
        except NoSuchElementException:
            continue

        if not (button.is_displayed() and button.is_enabled()):
            continue

        previous_count = len(driver.find_elements(By.CSS_SELECTOR, ".product-tile-inner"))
        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", button)
        time.sleep(0.25)
        driver.execute_script("arguments[0].click();", button)

        end_time = time.time() + wait_seconds
        while time.time() < end_time:
            time.sleep(0.5)
            current_count = len(
                driver.find_elements(By.CSS_SELECTOR, ".product-tile-inner")
            )
            if current_count > previous_count:
                return True
        return False

    return False


def load_all_products(driver: webdriver.Chrome, *, wait_seconds: float) -> None:
    """Keep clicking the "load more" control until it disappears."""

    while click_load_more(driver, wait_seconds=wait_seconds):
        continue


def extract_products(driver: webdriver.Chrome) -> List[ProductRow]:
    """Return all product rows found on the listing page."""

    rows: List[ProductRow] = []
    tiles = driver.find_elements(By.CSS_SELECTOR, ".product-tile-inner")
    for tile in tiles:
        fields = {}
        for key, selector in PRODUCT_SELECTORS.items():
            try:
                element = tile.find_element(By.CSS_SELECTOR, selector)
                fields[key] = element.text.strip()
            except NoSuchElementException:
                fields[key] = ""
        rows.append(
            ProductRow(
                title=fields["title"],
                price=fields["price"],
                old_price=fields["old_price"],
                discount=fields["discount"],
            )
        )
    return rows


def write_csv(rows: Iterable[ProductRow], output_path: Path) -> None:
    """Write the collected rows to ``output_path`` in UTF-8 CSV format."""

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["Produit", "Prix", "Ancien Prix", "Rabais"])
        for row in rows:
            writer.writerow(row.as_csv_row())


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help="Chemin du fichier CSV de sortie (défaut: data/sporting-life/liquidation.csv)",
    )
    parser.add_argument(
        "--wait",
        type=float,
        default=5.0,
        help="Temps d'attente maximum (en secondes) pour le chargement initial des produits.",
    )
    parser.add_argument(
        "--no-headless",
        dest="headless",
        action="store_false",
        help="Désactive le mode headless pour observer le navigateur.",
    )
    parser.set_defaults(headless=True)
    parser.add_argument(
        "--click-load-more",
        action="store_true",
        help="Tente de cliquer sur le bouton 'Charger plus' si disponible.",
    )
    return parser.parse_args(list(argv) if argv is not None else None)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)

    driver = create_driver(headless=args.headless)
    try:
        driver.get(LISTING_URL)
        wait_for_products(driver, wait_seconds=args.wait)
        if args.click_load_more:
            load_all_products(driver, wait_seconds=args.wait)
        products = extract_products(driver)
    finally:
        driver.quit()

    if not products:
        print(
            "Aucun produit n'a été détecté. Vérifiez les sélecteurs CSS ou le temps d'attente.",
            file=sys.stderr,
        )
        return 1

    write_csv(products, args.output)
    print(f"Écriture de {len(products)} produits dans {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
