"""Browser-based scraper for Best Buy Canada's clearance catalogue.

This script automates Chrome via Selenium to progressively load the
clearance listing (by pressing the "Show More" button) and exports the
resulting catalogue in the same JSON structure used across the project.

It complements :mod:`services.bestbuy`, which interacts with the public
collection API directly.  Some regions of the Best Buy website expose
more products on the client side than in the documented API, therefore a
browser-driven fallback is provided for parity with the storefront.
"""

from __future__ import annotations

import argparse
import contextlib
import logging
import os
import random
import sys
import time
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Iterable, List, Optional, Sequence, Tuple

import undetected_chromedriver as uc
from selenium.common.exceptions import (
    ElementClickInterceptedException,
    StaleElementReferenceException,
    TimeoutException,
)
from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webelement import WebElement
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

# Ensure the repository root is importable even when the script is executed
# directly (e.g. via ``python path/to/script.py``) so that sibling packages such
# as :mod:`config` can be resolved without relying on the current working
# directory.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from config.settings import get_settings
from services.bestbuy import (
    BestBuyProduct,
    ensure_absolute_url,
    load_store_metadata,
    mirror_to_city_files,
    normalise_price,
)

LOGGER = logging.getLogger(__name__)

DEFAULT_COLLECTION_URL = (
    "https://www.bestbuy.ca/en-ca/collection/clearance-products/113065"
    "?path=soldandshippedby0enrchstring%253ABest+Buy%253Bcurrentoffers0enrchstring%253AOn+Clearance"
)
DEFAULT_WAIT_SECONDS = 25
DEFAULT_CLICK_DELAY = 1.5
DEFAULT_MAX_PAGINATION = 120
CLICK_DELAY_RANGE: Tuple[float, float] = (1.2, 3.7)
SCROLL_PAUSE_RANGE: Tuple[float, float] = (0.8, 1.6)
NAVIGATION_PAUSE_RANGE: Tuple[float, float] = (1.2, 2.8)
SCROLL_DISTANCE_RANGE: Tuple[int, int] = (300, 620)


@dataclass(frozen=True)
class ScrapedProduct:
    sku: str
    title: str
    url: str
    image: Optional[str]
    regular_price: Optional[str]
    sale_price: Optional[str]
    availability: Optional[str]

    @classmethod
    def from_card(cls, card: WebElement) -> Optional["ScrapedProduct"]:
        sku_candidates = (
            card.get_attribute("data-sku"),
            card.get_attribute("data-product-sku"),
            cls._find_text(card, "[data-automation='sku']"),
        )
        sku_value = _first_non_empty(sku_candidates)
        if not sku_value:
            return None
        sku = str(sku_value).strip()
        if not sku:
            return None

        title = cls._find_text(
            card,
            "[data-testid='customer-product-title']",
            "[data-automation='customer-product-title']",
            "h3",
        )
        if not title:
            return None

        link = cls._find_attribute(
            card,
            "a[data-testid='link-element']",
            "href",
        )
        if not link:
            link = cls._find_attribute(card, "a", "href")
        if not link:
            return None
        url = ensure_absolute_url(link) or link

        image = cls._find_attribute(
            card,
            "img[data-testid='product-image']",
            "src",
        )
        if not image:
            image = cls._find_attribute(card, "img", "src")
        image = ensure_absolute_url(image) if image else None

        price_text = cls._find_price_text(
            card,
            "[data-testid='medium-customer-price']",
            "[data-testid='medium-sale-price']",
            "[data-testid='customer-price']",
            "[data-automation='product-price']",
        )
        regular_price_text = cls._find_price_text(
            card,
            "[data-testid='medium-regular-price']",
            "[data-testid='regular-price']",
            "[data-automation='regular-price']",
        )

        # Some cards expose the regular price only once; attempt to derive both
        # values by inspecting all price badges if the previous lookups failed.
        if not price_text or not regular_price_text:
            texts = cls._all_price_texts(
                card,
                "[data-testid$='price']",
                "[class*='price']",
            )
            if texts:
                if not price_text:
                    price_text = texts[0]
                if len(texts) > 1 and not regular_price_text:
                    regular_price_text = texts[1]

        availability = cls._find_text(
            card,
            "[data-automation='fulfillment-message']",
            "[data-automation='availability']",
            "[data-testid='fulfillment-info']",
        )

        return cls(
            sku=sku,
            title=title,
            url=url,
            image=image,
            regular_price=regular_price_text,
            sale_price=price_text,
            availability=availability,
        )

    @staticmethod
    def _find_text(card: WebElement, *selectors: str) -> Optional[str]:
        for selector in selectors:
            for element in card.find_elements(By.CSS_SELECTOR, selector):
                text = element.text.strip()
                if text:
                    return text
        return None

    @staticmethod
    def _clean_price_text(text: str) -> Optional[str]:
        cleaned = text.strip()
        if not cleaned:
            return None
        lowered = cleaned.lower()
        if "save" in lowered or "eco" in lowered or "ehf" in lowered:
            return None
        if not any(char.isdigit() for char in cleaned):
            return None
        return cleaned

    @classmethod
    def _find_price_text(cls, card: WebElement, *selectors: str) -> Optional[str]:
        for selector in selectors:
            for element in card.find_elements(By.CSS_SELECTOR, selector):
                candidate = cls._clean_price_text(element.text)
                if candidate:
                    return candidate
        return None

    @classmethod
    def _all_price_texts(cls, card: WebElement, *selectors: str) -> List[str]:
        texts: List[str] = []
        for selector in selectors:
            for element in card.find_elements(By.CSS_SELECTOR, selector):
                candidate = cls._clean_price_text(element.text)
                if candidate and candidate not in texts:
                    texts.append(candidate)
        return texts

    @staticmethod
    def _find_attribute(
        card: WebElement, selector: str, attribute: str
    ) -> Optional[str]:
        for element in card.find_elements(By.CSS_SELECTOR, selector):
            value = element.get_attribute(attribute)
            if value:
                return value
        return None


def _first_non_empty(values: Iterable[Optional[str]]) -> Optional[str]:
    for value in values:
        if not value:
            continue
        text = str(value).strip()
        if text:
            return text
    return None


def _random_user_agent(candidates: Sequence[str]) -> Optional[str]:
    usable = [candidate.strip() for candidate in candidates if candidate and str(candidate).strip()]
    if not usable:
        return None
    return random.choice(usable)


def _random_proxy(candidates: Sequence[str]) -> Optional[str]:
    usable = [candidate.strip() for candidate in candidates if candidate and str(candidate).strip()]
    if not usable:
        return None
    return random.choice(usable)


def _human_delay(base: float, bounds: Tuple[float, float]) -> float:
    minimum, maximum = bounds
    lower = max(minimum, base * 0.6 if base else minimum)
    upper = max(maximum, base * 1.6 if base else maximum)
    return random.uniform(lower, upper)


def _pause(bounds: Tuple[float, float]) -> None:
    time.sleep(random.uniform(*bounds))


def _scroll_distance() -> int:
    return random.randint(*SCROLL_DISTANCE_RANGE)


def parse_arguments(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Scrape the Best Buy liquidation listing via Selenium.",
    )
    parser.add_argument(
        "--url",
        default=DEFAULT_COLLECTION_URL,
        help="Liquidation collection URL to visit.",
    )
    parser.add_argument(
        "--data-root",
        type=Path,
        default=None,
        help="Root directory containing the data/ folder (defaults to project base dir).",
    )
    parser.add_argument(
        "--headless",
        action="store_true",
        help="Force headless mode. Enabled by default in CI.",
    )
    parser.add_argument(
        "--no-headless",
        dest="headless",
        action="store_false",
        help="Disable headless mode (useful for local debugging).",
    )
    parser.set_defaults(headless=True)
    parser.add_argument(
        "--wait-time",
        type=float,
        default=DEFAULT_WAIT_SECONDS,
        help="Maximum wait time (seconds) for the product grid to appear.",
    )
    parser.add_argument(
        "--click-delay",
        type=float,
        default=DEFAULT_CLICK_DELAY,
        help="Delay (seconds) to wait after clicking 'Show More'.",
    )
    parser.add_argument(
        "--max-pages",
        type=int,
        default=DEFAULT_MAX_PAGINATION,
        help="Maximum number of Show More interactions to attempt.",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable debug logging for troubleshooting.",
    )
    return parser.parse_args(argv)


def configure_logging(verbose: bool) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


def create_driver(
    headless: bool,
    user_agents: Sequence[str],
    proxies: Sequence[str],
) -> WebDriver:
    options = uc.ChromeOptions()
    if headless:
        options.add_argument("--headless=new")
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("--lang=en-CA")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--disable-extensions")
    options.add_argument("--disable-infobars")

    user_agent = _random_user_agent(user_agents)
    if user_agent:
        options.add_argument(f"--user-agent={user_agent}")
        LOGGER.debug("User-Agent sélectionné: %s", user_agent)

    proxy = _random_proxy(proxies)
    if proxy:
        options.add_argument(f"--proxy-server={proxy}")
        masked_proxy = proxy.split("@")[-1]
        LOGGER.info("Proxy activé pour la session (%s)", masked_proxy)

    binary = os.environ.get("CHROME_BIN") or os.environ.get("CHROME_PATH")
    if binary:
        options.binary_location = binary

    driver = uc.Chrome(options=options, headless=headless)
    driver.set_window_size(1920, 1080)
    return driver


def wait_for_grid(driver: WebDriver, wait_time: float) -> None:
    LOGGER.debug("Waiting for the product grid to be visible")
    WebDriverWait(driver, wait_time).until(
        EC.presence_of_element_located((By.CSS_SELECTOR, "[data-testid='product-card']"))
    )


def _show_more_xpath() -> str:
    return (
        "//button[contains(translate(normalize-space(.), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ',"
        " 'abcdefghijklmnopqrstuvwxyz'), 'show more')]"
    )


def click_show_more(driver: WebDriver, wait_time: float, delay: float, max_pages: int) -> None:
    wait = WebDriverWait(driver, wait_time)
    previous_count = len(driver.find_elements(By.CSS_SELECTOR, "[data-testid='product-card']"))
    for index in range(max_pages):
        try:
            button = wait.until(EC.element_to_be_clickable((By.XPATH, _show_more_xpath())))
        except TimeoutException:
            LOGGER.debug("No further 'Show More' button detected (timeout)")
            break
        if not button.is_enabled():
            LOGGER.debug("Pagination button disabled – stopping after %s clicks", index)
            break

        LOGGER.debug("Clicking 'Show More' (%s/%s)", index + 1, max_pages)
        try:
            driver.execute_script("window.scrollBy(0, arguments[0]);", _scroll_distance())
            _pause(SCROLL_PAUSE_RANGE)
            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", button)
            _pause(SCROLL_PAUSE_RANGE)
            try:
                button.click()
            except ElementClickInterceptedException:
                driver.execute_script("arguments[0].click();", button)
        except StaleElementReferenceException:
            LOGGER.debug("Stale pagination button, retrying")
            continue

        time.sleep(_human_delay(delay, CLICK_DELAY_RANGE))
        try:
            wait.until(lambda d: _product_count(d) > previous_count)
        except TimeoutException:
            LOGGER.debug("Product count did not increase after click")
            # Still re-compute the count to decide whether to continue.
        new_count = _product_count(driver)
        LOGGER.debug("Product cards loaded: %s", new_count)
        if new_count <= previous_count:
            LOGGER.debug("No new products detected – stopping pagination")
            break
        previous_count = new_count


def _product_count(driver: WebDriver) -> int:
    return len(driver.find_elements(By.CSS_SELECTOR, "[data-testid='product-card']"))


def collect_products(driver: WebDriver) -> List[BestBuyProduct]:
    cards = driver.find_elements(By.CSS_SELECTOR, "[data-testid='product-card']")
    LOGGER.info("Parsing %s product cards", len(cards))
    products: List[BestBuyProduct] = []
    seen: set[str] = set()
    for card in cards:
        with contextlib.suppress(StaleElementReferenceException):
            parsed = ScrapedProduct.from_card(card)
            if not parsed:
                continue
            if parsed.sku in seen:
                continue
            seen.add(parsed.sku)
            regular_price = normalise_price(parsed.regular_price)
            sale_price = normalise_price(parsed.sale_price)
            if sale_price is None and regular_price is not None:
                sale_price = regular_price
            products.append(
                BestBuyProduct(
                    sku=parsed.sku,
                    name=parsed.title,
                    url=ensure_absolute_url(parsed.url) or parsed.url,
                    regular_price=regular_price,
                    sale_price=sale_price,
                    image=parsed.image,
                    availability=parsed.availability,
                    store="Best Buy",
                )
            )
    products.sort(
        key=lambda item: (
            item.sale_price if item.sale_price is not None else Decimal("Infinity"),
            item.name,
        )
    )
    return products


def scrape_bestbuy(
    url: str,
    headless: bool,
    wait_time: float,
    delay: float,
    max_pages: int,
    user_agents: Sequence[str],
    proxies: Sequence[str],
) -> List[BestBuyProduct]:
    LOGGER.info("Opening %s", url)
    driver = create_driver(headless=headless, user_agents=user_agents, proxies=proxies)
    try:
        driver.get(url)
        _pause(NAVIGATION_PAUSE_RANGE)
        wait_for_grid(driver, wait_time)
        click_show_more(driver, wait_time, delay, max_pages)
        return collect_products(driver)
    finally:
        with contextlib.suppress(Exception):
            driver.quit()


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_arguments(argv)
    configure_logging(args.verbose)

    settings = get_settings()
    root = args.data_root or settings.base_dir
    root = root.resolve()

    user_agents = tuple(settings.bestbuy_user_agents)
    proxies = tuple(settings.bestbuy_proxies)
    LOGGER.debug(
        "Configuration réseau: %s proxies, %s user-agents",
        len(proxies),
        len(user_agents),
    )

    products = scrape_bestbuy(
        url=args.url,
        headless=args.headless,
        wait_time=args.wait_time,
        delay=args.click_delay,
        max_pages=args.max_pages,
        user_agents=user_agents,
        proxies=proxies,
    )

    if not products:
        LOGGER.warning("Aucun produit n'a été trouvé sur la page de liquidation %s", args.url)
        return 0

    LOGGER.info("%s produits collectés", len(products))
    city_metadata = load_store_metadata(root)
    mirror_to_city_files(products, root, city_metadata=city_metadata)
    LOGGER.info("Catalogues Best Buy mis à jour dans %s", root / 'data' / 'best-buy')
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
