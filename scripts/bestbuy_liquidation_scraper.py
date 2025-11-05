"""Headless Best Buy clearance scraper using Selenium and undetected-chromedriver.

The scraper mirrors the behaviour of the existing API based pipeline while
clicking through the public clearance catalogue to remain resilient to future
changes.  Products are grouped by their store label and exported as JSON files
in ``data/best-buy/liquidations``.

Example usage::

    python scripts/bestbuy_liquidation_scraper.py --headless

The script rotates proxies and user-agents when multiple candidates are
configured through environment variables.  See :mod:`config.settings` for the
available configuration knobs.
"""

from __future__ import annotations

import argparse
import json
import logging
import random
import re
import sys
import time
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterator, List, Optional, Sequence, Tuple

import undetected_chromedriver as uc
from selenium.common.exceptions import (
    ElementClickInterceptedException,
    TimeoutException,
    WebDriverException,
)
from selenium.webdriver import Chrome
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webelement import WebElement
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from config.settings import get_settings
from services.bestbuy import BestBuyProduct, discover_products, parse_product


LOGGER = logging.getLogger("bestbuy.scraper")

DEFAULT_TIMEOUT = 40


@dataclass
class ScraperConfig:
    url: str
    headless: bool
    delay_min: float
    delay_max: float
    max_retries: int
    output_root: Path
    user_agents: Sequence[str]
    proxy_pool: Sequence[str]
    implicit_wait: float
    page_load_timeout: float

    @property
    def random_user_agent(self) -> Optional[str]:
        if not self.user_agents:
            return None
        return random.choice(list(self.user_agents))


SHOW_MORE_XPATHS: Tuple[str, ...] = (
    "//button[contains(translate(normalize-space(.), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'show more')]",
    "//button[contains(translate(normalize-space(.), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'load more')]",
    "//button[contains(translate(normalize-space(.), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'afficher plus')]",
)


def slugify_city(label: str) -> str:
    base = label.strip().lower()
    normalised = unicodedata.normalize("NFKD", base)
    ascii_text = "".join(ch for ch in normalised if not unicodedata.combining(ch))
    cleaned = re.sub(r"[^a-z0-9]+", "-", ascii_text).strip("-")
    return cleaned or "best-buy"


def normalise_store(store: Optional[str]) -> Tuple[str, str, str]:
    if not store:
        return "Best Buy Canada", "Canada", "canada"
    label = store.strip()
    prefix = "best buy"
    lower = label.lower()
    city_label = label
    if lower.startswith(prefix):
        candidate = label[len(prefix) :].strip(" -:|")
        if candidate:
            city_label = candidate
    slug = slugify_city(city_label)
    store_label = label if lower.startswith(prefix) else f"Best Buy {city_label}".strip()
    return store_label or "Best Buy Canada", city_label or "Canada", slug


def ensure_random_delay(config: ScraperConfig) -> None:
    if config.delay_max <= 0:
        return
    lower = max(0.0, min(config.delay_min, config.delay_max))
    upper = max(config.delay_min, config.delay_max)
    sleep_for = random.uniform(lower, upper)
    LOGGER.debug("Sleeping for %.2fs", sleep_for)
    time.sleep(sleep_for)


def build_driver(config: ScraperConfig, proxy: Optional[str]) -> Chrome:
    options: Options = uc.ChromeOptions()
    if config.headless:
        options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-gpu")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--lang=en-CA")
    user_agent = config.random_user_agent
    if user_agent:
        options.add_argument(f"--user-agent={user_agent}")
    if proxy:
        options.add_argument(f"--proxy-server={proxy}")
    driver = uc.Chrome(options=options, use_subprocess=True)
    driver.implicitly_wait(config.implicit_wait)
    driver.set_page_load_timeout(config.page_load_timeout)
    return driver


def iter_proxies(pool: Sequence[str]) -> Iterator[Optional[str]]:
    unique = list(dict.fromkeys(proxy.strip() for proxy in pool if proxy.strip()))
    random.shuffle(unique)
    yield None
    for proxy in unique:
        yield proxy


def wait_for_products(driver: Chrome, timeout: int = DEFAULT_TIMEOUT) -> None:
    WebDriverWait(driver, timeout).until(
        lambda d: d.find_elements(By.CSS_SELECTOR, "a[href*='/product/']")
    )


def click_show_more(driver: Chrome, config: ScraperConfig) -> None:
    wait = WebDriverWait(driver, 15)
    while True:
        button: Optional[WebElement] = None
        for xpath in SHOW_MORE_XPATHS:
            try:
                button = wait.until(EC.element_to_be_clickable((By.XPATH, xpath)))
                if button:
                    break
            except TimeoutException:
                continue
        if not button:
            LOGGER.debug("No additional 'Show More' button detected.")
            break

        try:
            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", button)
        except WebDriverException:
            pass

        ensure_random_delay(config)

        try:
            button.click()
        except (ElementClickInterceptedException, WebDriverException) as exc:
            LOGGER.debug("Click intercepted when expanding results: %s", exc)
            break

        try:
            wait.until(EC.staleness_of(button))
        except TimeoutException:
            LOGGER.debug("Timeout waiting for the results to refresh after click.")
            break


def extract_application_state(driver: Chrome) -> Optional[Dict[str, object]]:
    script = """
    const serialise = (candidate) => {
      if (!candidate) {
        return null;
      }
      try {
        return JSON.stringify(candidate);
      } catch (err) {
        try {
          return JSON.stringify(candidate, function(key, value) {
            if (typeof value === 'bigint') {
              return Number(value);
            }
            return value;
          });
        } catch (err2) {
          return null;
        }
      }
    };

    const directCandidates = [
      window.__PRELOADED_STATE__,
      window.__INITIAL_STATE__,
      window.__NUXT__,
      window.__NEXT_DATA__,
      window.__APP_INITIAL_STATE__,
    ];

    for (const candidate of directCandidates) {
      const serialised = serialise(candidate);
      if (serialised) {
        return serialised;
      }
    }

    const scriptTag = document.querySelector('script#__NEXT_DATA__');
    if (scriptTag && scriptTag.textContent) {
      return scriptTag.textContent;
    }

    return null;
    """

    raw_json = driver.execute_script(script)
    if not raw_json or not isinstance(raw_json, str):
        return None
    try:
        return json.loads(raw_json)
    except json.JSONDecodeError:
        LOGGER.debug("Unable to decode JSON payload from application state.")
        return None


def collect_products_from_state(state: Dict[str, object]) -> List[BestBuyProduct]:
    products: List[BestBuyProduct] = []
    try:
        raw_products = discover_products(state)
    except Exception as exc:
        LOGGER.debug("Error while discovering products: %s", exc)
        raw_products = []

    for entry in raw_products:
        parsed = parse_product(entry)
        if parsed:
            products.append(parsed)
    return products


def collect_products(driver: Chrome) -> List[BestBuyProduct]:
    state = extract_application_state(driver)
    if not state:
        LOGGER.warning("Application state missing – falling back to DOM parsing.")
        return []
    products = collect_products_from_state(state)
    LOGGER.info("%s products extracted from application state", len(products))
    return products


def export_grouped_products(
    grouped: Dict[str, Dict[str, object]],
    output_root: Path,
) -> None:
    liquidations_dir = output_root / "data" / "best-buy" / "liquidations"
    summary_dir = output_root / "data" / "best-buy"
    aggregate_path = output_root / "data" / "bestbuy_liquidation.json"

    all_products: List[Dict[str, object]] = []
    summary_payload: List[Dict[str, object]] = []

    for slug in sorted(grouped):
        metadata = grouped[slug]
        products: List[BestBuyProduct] = metadata["products"]
        store_label: str = metadata["store_label"]
        city_label: str = metadata["city_label"]

        detailed_payload = [
            product.to_detailed_dict(store_label=store_label) for product in products
        ]
        summary_entries = [
            product.to_summary_dict(city_label, store_label=store_label)
            for product in products
        ]

        all_products.extend(detailed_payload)
        summary_payload.extend(summary_entries)

        output_path = liquidations_dir / f"{slug}.json"
        summary_path = summary_dir / f"{slug}.json"

        output_path.parent.mkdir(parents=True, exist_ok=True)
        summary_path.parent.mkdir(parents=True, exist_ok=True)

        output_path.write_text(
            json.dumps(detailed_payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        summary_path.write_text(
            json.dumps(summary_entries, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    aggregate_path.parent.mkdir(parents=True, exist_ok=True)
    aggregate_path.write_text(
        json.dumps(all_products, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    def _summary_sort_key(entry: Dict[str, object]) -> Tuple[str, float, str]:
        city = str(entry.get("city") or "")
        price_candidate = entry.get("salePrice") or entry.get("price")
        price_value: float
        try:
            price_value = float(price_candidate) if price_candidate is not None else float("inf")
        except (TypeError, ValueError):
            price_value = float("inf")
        title = str(entry.get("title") or "")
        return city, price_value, title

    summary_payload.sort(key=_summary_sort_key)

    (summary_dir / "liquidations.json").write_text(
        json.dumps(summary_payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def group_products_by_store(products: List[BestBuyProduct]) -> Dict[str, Dict[str, object]]:
    grouped: Dict[str, Dict[str, object]] = {}
    for product in products:
        store_label, city_label, slug = normalise_store(product.store)
        entry = grouped.setdefault(
            slug,
            {
                "store_label": store_label,
                "city_label": city_label,
                "products": [],
            },
        )
        entry["products"].append(product)

    for metadata in grouped.values():
        metadata["products"].sort(
            key=lambda item: (
                item.sale_price if item.sale_price is not None else float("inf"),
                item.name,
            )
        )

    return grouped


def parse_arguments(argv: Optional[Sequence[str]]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Scrape Best Buy clearance offers.")
    parser.add_argument(
        "--headless",
        action="store_true",
        help="Run Chrome in headless mode (default when executed in CI).",
    )
    parser.add_argument(
        "--no-headless",
        dest="headless",
        action="store_false",
        help="Disable headless mode for debugging purposes.",
    )
    parser.set_defaults(headless=True)
    parser.add_argument(
        "--delay-min",
        type=float,
        default=None,
        help="Minimum random delay between 'Show More' clicks.",
    )
    parser.add_argument(
        "--delay-max",
        type=float,
        default=None,
        help="Maximum random delay between 'Show More' clicks.",
    )
    parser.add_argument(
        "--max-retries",
        type=int,
        default=3,
        help="Maximum number of retries with proxy rotation.",
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        default=None,
        help="Override the project root used to resolve the data/ directory.",
    )
    parser.add_argument(
        "--url",
        type=str,
        default=None,
        help="Custom clearance URL to scrape.",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable debug logging.",
    )
    return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_arguments(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    settings = get_settings()

    config = ScraperConfig(
        url=args.url or settings.bestbuy_clearance_url,
        headless=args.headless,
        delay_min=args.delay_min if args.delay_min is not None else settings.bestbuy_random_delay_min,
        delay_max=args.delay_max if args.delay_max is not None else settings.bestbuy_random_delay_max,
        max_retries=max(1, args.max_retries),
        output_root=(args.output_root or settings.base_dir).resolve(),
        user_agents=settings.bestbuy_user_agents,
        proxy_pool=settings.bestbuy_proxy_pool,
        implicit_wait=settings.selenium_implicit_wait,
        page_load_timeout=settings.selenium_page_load_timeout,
    )

    LOGGER.info("Scraping Best Buy clearance from %s", config.url)

    last_error: Optional[Exception] = None
    driver: Optional[Chrome] = None

    proxy_candidates = list(iter_proxies(config.proxy_pool)) or [None]

    for attempt in range(1, config.max_retries + 1):
        proxy = proxy_candidates[(attempt - 1) % len(proxy_candidates)]
        try:
            driver = build_driver(config, proxy)
            LOGGER.debug("Attempt %s/%s with proxy %s", attempt, config.max_retries, proxy or "<none>")
            driver.get(config.url)
            wait_for_products(driver)
            click_show_more(driver, config)
            products = collect_products(driver)
            if not products:
                raise RuntimeError("No products extracted from the clearance page")
            grouped = group_products_by_store(products)
            export_grouped_products(grouped, config.output_root)
            LOGGER.info("Exported clearance data for %s locations", len(grouped))
            return 0
        except Exception as exc:
            last_error = exc
            LOGGER.warning("Scraping attempt %s failed: %s", attempt, exc)
        finally:
            if driver:
                try:
                    driver.quit()
                except Exception:
                    pass
                driver = None

    if last_error:
        LOGGER.error("Scraping failed after %s attempts: %s", config.max_retries, last_error)
    return 1


if __name__ == "__main__":  # pragma: no cover - CLI entry point
    sys.exit(main())

