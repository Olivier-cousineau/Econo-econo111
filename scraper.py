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
import random
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Iterable, List, Optional, Tuple
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

try:
    from selenium import webdriver
    from selenium.common.exceptions import TimeoutException as SeleniumTimeoutError
    from selenium.webdriver.chrome.service import Service as ChromeService
    from selenium.webdriver.common.by import By
    from selenium.webdriver.common.keys import Keys
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.webdriver.support.ui import WebDriverWait
    from webdriver_manager.chrome import ChromeDriverManager
except ImportError:  # pragma: no cover - dependency is optional at runtime
    By = None  # type: ignore[assignment]
    ChromeDriverManager = None  # type: ignore[assignment]
    ChromeService = None  # type: ignore[assignment]
    EC = None  # type: ignore[assignment]
    Keys = None  # type: ignore[assignment]
    SeleniumTimeoutError = Exception  # type: ignore[assignment]
    WebDriverWait = None  # type: ignore[assignment]
    webdriver = None  # type: ignore[assignment]

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
BRANCH_MIRRORS = (
    ("montreal", "Montréal"),
    ("laval", "Laval"),
    ("saint-jerome", "Saint-Jérôme"),
)
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
USE_SELENIUM = os.getenv("SPORTING_LIFE_USE_SELENIUM", "0").lower() not in {
    "0",
    "false",
    "no",
}
SELENIUM_HEADLESS = os.getenv(
    "SPORTING_LIFE_SELENIUM_HEADLESS", "1"
).lower() not in {"0", "false", "no"}
SELENIUM_WAIT_TIMEOUT = int(os.getenv("SPORTING_LIFE_SELENIUM_WAIT", "30"))
SELENIUM_DELAY_RANGE = (
    float(os.getenv("SPORTING_LIFE_SELENIUM_DELAY_MIN", "0.35")),
    float(os.getenv("SPORTING_LIFE_SELENIUM_DELAY_MAX", "1.1")),
)
SELENIUM_SCROLL_RANGE = (
    int(os.getenv("SPORTING_LIFE_SELENIUM_SCROLL_MIN", "200")),
    int(os.getenv("SPORTING_LIFE_SELENIUM_SCROLL_MAX", "600")),
)

PRODUCT_TILE_SELECTOR = "div.plp-product-tile, div.product-tile, li.product-grid__item"


def _clamp_delay_bounds(bounds: Tuple[float, float]) -> Tuple[float, float]:
    low, high = bounds
    if high < low:
        return (high, low)
    if low == high:
        # évite les valeurs nulles qui stopperaient la simulation humaine
        adjusted = low or 0.2
        return (adjusted, adjusted + 0.01)
    return bounds


SELENIUM_DELAY_RANGE = _clamp_delay_bounds(SELENIUM_DELAY_RANGE)


def _clamp_scroll_bounds(bounds: Tuple[int, int]) -> Tuple[int, int]:
    low, high = bounds
    if high < low:
        return (high, low)
    if low == high:
        adjusted = max(low, 50)
        return (adjusted, adjusted + 10)
    return bounds


SELENIUM_SCROLL_RANGE = _clamp_scroll_bounds(SELENIUM_SCROLL_RANGE)


def _normalize_purge_method(value: Optional[str]) -> str:
    if not value:
        return "DELETE"
    normalized = value.strip().upper()
    return normalized or "DELETE"


def human_pause(min_delay: Optional[float] = None, max_delay: Optional[float] = None) -> None:
    """Pause execution for a human-like delay."""

    low, high = SELENIUM_DELAY_RANGE
    min_delay = low if min_delay is None else min_delay
    max_delay = high if max_delay is None else max_delay
    if max_delay < min_delay:
        min_delay, max_delay = max_delay, min_delay
    time.sleep(random.uniform(min_delay, max_delay))


def human_scroll(driver) -> None:
    """Scroll doucement pour simuler un comportement humain."""

    if not SELENIUM_SCROLL_RANGE:
        return
    low, high = SELENIUM_SCROLL_RANGE
    distance = random.randint(low, high)
    driver.execute_script("window.scrollBy(0, arguments[0]);", distance)
    human_pause(0.15, 0.45)


def parse_display_counters(text: str) -> Tuple[Optional[int], Optional[int]]:
    """Extraire les compteurs « affichés / total » d'un bloc de texte."""

    numbers = re.findall(r"\d[\d\s\u00a0,\.]*", text)
    if len(numbers) < 2:
        return None, None

    def _to_int(value: str) -> Optional[int]:
        normalized = re.sub(r"[^0-9]", "", value)
        if not normalized:
            return None
        try:
            return int(normalized)
        except ValueError:
            return None

    current = _to_int(numbers[0])
    total = _to_int(numbers[1])
    return current, total

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


def load_all_products_playwright(page, max_clicks=500):
    """Charge progressivement tous les produits via le bouton « SHOW MORE ».

    Cette routine tente d'imiter un défilement manuel en cliquant
    automatiquement sur le bouton d'expansion tant qu'il est visible. En plus
    de vérifier l'augmentation du nombre de cartes, elle inspecte les messages
    du type « Showing X out of Y items » ou « Affichage de X sur Y articles ».
    Dès que le compteur indique que tout l'inventaire est affiché, on arrête la
    boucle pour éviter des clics superflus.
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
            PRODUCT_TILE_SELECTOR,
        )

    count_selectors = [
        "text=/Showing\\s+\\d+[\\s\\u00a0,\\.]*out of\\s+\\d+/i",
        "text=/Affichage\\s+de\\s+\\d+[\\s\\u00a0,\\.]*sur\\s+\\d+/i",
        ".count-info",
        ".product-count",
    ]

    last = tiles_count()
    print(f"DEBUG: initial tiles = {last}")

    for i in range(max_clicks):
        btn = page.locator(
            "button:has-text('SHOW MORE'), button:has-text('Show More'), "
            "button:has-text('VOIR PLUS'), button:has-text('Voir plus'), "
            "button.load-more, [role='button']:has-text('Show More'), "
            "[role='button']:has-text('Voir plus')"
        )
        btn_count = btn.count()
        if btn_count == 0:
            print("DEBUG: no more button or disabled -> stop.")
            break

        candidate = None
        for index in range(btn_count):
            current = btn.nth(index)
            try:
                if current.is_visible() and current.is_enabled():
                    candidate = current
                    break
            except Exception:
                continue

        if candidate is None:
            print("DEBUG: no more button or disabled -> stop.")
            break

        # amener le bouton en vue et cliquer
        candidate.scroll_into_view_if_needed()
        candidate.click()
        try:
            page.wait_for_timeout(500)
        except Exception:
            pass

        # attendre que le nombre d’items augmente
        increased = False
        try:
            page.wait_for_function(
                f"""(prev) => {{
                    const sel = \"{PRODUCT_TILE_SELECTOR}\";
                    return document.querySelectorAll(sel).length > prev;
                }}""",
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
            try:
                page.wait_for_timeout(2000)
            except Exception:
                pass

        new_count = tiles_count()
        print(f"DEBUG: click {i+1}: {new_count} tiles")

        counter_reached_total = False
        for selector in count_selectors:
            locator = page.locator(selector)
            try:
                if locator.count() == 0:
                    continue
                text_value = locator.first.inner_text().strip()
            except Exception:
                continue

            current, total = parse_display_counters(text_value)
            if current is None or total is None:
                continue
            if total > 0 and current >= total:
                counter_reached_total = True
                print(
                    "DEBUG: count-info indicates all items loaded -> stop.",
                    f"({current}/{total})",
                )
                last = max(last, current, new_count)
                break

        if counter_reached_total:
            break

        if new_count > last:
            last = new_count
            continue

        if not increased or new_count <= last:
            print("DEBUG: tiles did not increase -> stop.")
            break


def load_all_products_selenium(driver, max_clicks: int = 500) -> None:
    """Utilise Selenium pour charger progressivement tous les produits."""

    if WebDriverWait is None or By is None or EC is None:
        raise RuntimeError("Selenium n'est pas disponible dans cet environnement")

    wait = WebDriverWait(driver, SELENIUM_WAIT_TIMEOUT)

    def tiles_count() -> int:
        try:
            return len(driver.find_elements(By.CSS_SELECTOR, PRODUCT_TILE_SELECTOR))
        except Exception:
            return 0

    # fermer la bannière cookies si possible
    cookie_locators = [
        (
            By.XPATH,
            "//button[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'accepter')]",
        ),
        (
            By.XPATH,
            "//button[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'accept')]",
        ),
    ]
    for locator in cookie_locators:
        try:
            button = WebDriverWait(driver, 5).until(EC.element_to_be_clickable(locator))
        except SeleniumTimeoutError:
            continue
        except Exception:
            break
        try:
            button.click()
            human_pause()
            break
        except Exception:
            continue

    count_locators = [
        (
            By.XPATH,
            "//*[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'showing') "
            "and contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'out of')]",
        ),
        (
            By.XPATH,
            "//*[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'affichage') "
            "and contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'sur')]",
        ),
        (By.CSS_SELECTOR, ".count-info"),
        (By.CSS_SELECTOR, ".product-count"),
    ]

    last = tiles_count()
    print(f"DEBUG: initial tiles (selenium) = {last}")

    for index in range(max_clicks):
        button_locators = [
            (
                By.XPATH,
                "//button[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'show more')]",
            ),
            (
                By.XPATH,
                "//button[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'voir plus')]",
            ),
            (
                By.XPATH,
                "//*[@role='button' and contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'show more')]",
            ),
            (
                By.XPATH,
                "//*[@role='button' and contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'voir plus')]",
            ),
        ]

        candidate = None
        for locator in button_locators:
            try:
                candidate = wait.until(EC.element_to_be_clickable(locator))
                if candidate:
                    break
            except SeleniumTimeoutError:
                continue
            except Exception:
                continue

        if candidate is None:
            print("DEBUG: no more button or disabled -> stop (selenium).")
            break

        try:
            driver.execute_script(
                "arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});",
                candidate,
            )
        except Exception:
            pass

        human_pause()

        clicked = False
        try:
            candidate.click()
            clicked = True
        except Exception:
            try:
                driver.execute_script("arguments[0].click();", candidate)
                clicked = True
            except Exception:
                pass

        if not clicked:
            print("DEBUG: unable to click show more button -> stop (selenium).")
            break

        human_pause()
        try:
            body = driver.find_element(By.TAG_NAME, "body")
            if Keys is not None:
                body.send_keys(Keys.PAGE_DOWN)
        except Exception:
            pass
        human_scroll(driver)

        increased = False
        try:
            wait.until(
                lambda d: len(d.find_elements(By.CSS_SELECTOR, PRODUCT_TILE_SELECTOR)) > last
            )
            increased = True
        except SeleniumTimeoutError:
            try:
                wait.until(EC.presence_of_all_elements_located((By.CSS_SELECTOR, PRODUCT_TILE_SELECTOR)))
            except SeleniumTimeoutError:
                pass
            human_pause(0.8, 1.6)

        new_count = tiles_count()
        print(f"DEBUG: click {index + 1} (selenium): {new_count} tiles")

        counter_reached_total = False
        for locator in count_locators:
            try:
                elements = driver.find_elements(*locator)
            except Exception:
                continue
            if not elements:
                continue
            text_value = elements[0].text.strip()
            current, total = parse_display_counters(text_value)
            if current is None or total is None:
                continue
            if total > 0 and current >= total:
                counter_reached_total = True
                print(
                    "DEBUG: count-info indicates all items loaded -> stop (selenium).",
                    f"({current}/{total})",
                )
                last = max(last, current, new_count)
                break

        if counter_reached_total:
            break

        if new_count > last:
            last = new_count
            continue

        if not increased or new_count <= last:
            print("DEBUG: tiles did not increase -> stop (selenium).")
            break

API_URL = os.getenv("ECONODEAL_API_URL")
API_TOKEN = os.getenv("ECONODEAL_API_TOKEN")
API_PURGE_URL = os.getenv("ECONODEAL_API_PURGE_URL") or API_URL
API_PURGE_METHOD = _normalize_purge_method(os.getenv("ECONODEAL_API_PURGE_METHOD"))
API_PURGE_ENABLED = os.getenv("ECONODEAL_API_PURGE", "1").lower() not in {
    "0",
    "false",
    "no",
}
API_PURGE_SUCCESS_STATUSES = {200, 201, 202, 204, 205}


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

            load_all_products_playwright(page)

            try:
                page.wait_for_selector(PRODUCT_TILE_SELECTOR, timeout=PLAYWRIGHT_TIMEOUT)
            except PlaywrightTimeoutError:
                logging.warning("Timed out waiting for product tiles on %s", url)

            try:
                tile_count = page.evaluate(
                    """(selector) => document.querySelectorAll(selector).length""",
                    PRODUCT_TILE_SELECTOR,
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


def fetch_html_with_selenium(url: str) -> str:
    """Return the rendered HTML payload for *url* using Selenium."""

    if (
        webdriver is None
        or ChromeDriverManager is None
        or ChromeService is None
        or By is None
        or EC is None
    ):
        raise RuntimeError("Selenium is not installed")
    if WebDriverWait is None:
        raise RuntimeError("Selenium wait helpers are not available")

    logging.info("Fetching Sporting Life clearance page via Selenium: %s", url)
    driver = None
    try:
        options = webdriver.ChromeOptions()
        options.add_argument(f"--user-agent={USER_AGENT}")
        options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--no-sandbox")
        options.add_argument("--lang=fr-FR")
        options.add_argument("--window-size=1280,1080")
        options.add_argument("--disable-gpu")
        if SELENIUM_HEADLESS:
            options.add_argument("--headless=new")
        options.add_experimental_option("excludeSwitches", ["enable-automation"])
        options.add_experimental_option("useAutomationExtension", False)

        service = ChromeService(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=options)
        try:
            driver.execute_cdp_cmd(
                "Page.addScriptToEvaluateOnNewDocument",
                {
                    "source": "Object.defineProperty(navigator, 'webdriver', {get: () => undefined});",
                },
            )
        except Exception:
            pass

        driver.set_page_load_timeout(REQUEST_TIMEOUT)
        driver.get(url)
        human_pause(0.8, 1.6)
        human_scroll(driver)

        wait = WebDriverWait(driver, SELENIUM_WAIT_TIMEOUT)
        try:
            wait.until(EC.presence_of_all_elements_located((By.CSS_SELECTOR, PRODUCT_TILE_SELECTOR)))
        except SeleniumTimeoutError:
            logging.debug("Initial Selenium wait for product tiles timed out on %s", url)

        load_all_products_selenium(driver)
        human_pause(0.4, 1.0)

        try:
            tile_count = len(driver.find_elements(By.CSS_SELECTOR, PRODUCT_TILE_SELECTOR))
        except Exception:
            tile_count = 0
        logging.info("Selenium collected %s product tiles", tile_count)

        content = driver.page_source
        if not content:
            raise RuntimeError("Selenium did not return any page content")
        return content
    finally:
        if driver is not None:
            try:
                driver.quit()
            except Exception:  # pragma: no cover - best effort cleanup
                pass


def fetch_html(url: str) -> str:
    """Return the HTML payload for *url* using Selenium, Playwright or requests."""

    if USE_SELENIUM:
        try:
            return fetch_html_with_selenium(url)
        except Exception:
            logging.exception("Selenium fetch failed, falling back to alternate strategies")

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
        sale_tag = tile.select_one(".price-sales, .product-sales-price, .price__sale")
        regular_tag = tile.select_one(".price-standard, .product-standard-price, .price__regular")

        name = extract_text(name_tag)
        sale_text = extract_text(sale_tag)
        regular_text = extract_text(regular_tag)
        link = name_tag.get("href") if name_tag else None
        image = extract_image_url(tile)

        if link:
            link = urljoin(SPORTING_LIFE_URL, link)

        if name:
            products.append(
                {
                    "nom": name,
                    "prix": sale_text,
                    "prix_original": regular_text,
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


def normalize_price_value(value) -> Optional[float]:
    """Return a ``float`` price when possible.

    Handles strings formatted in the Canadian locale as well as numeric values.
    """

    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        try:
            return float(value)
        except (TypeError, ValueError):
            return None
    if isinstance(value, str):
        return parse_price(value)
    return None


def enrich_products(items: Iterable[dict]) -> List[dict]:
    """Augment raw product dictionaries with Econodeal-friendly fields.

    The scraper historically emitted keys such as ``nom`` and ``prix`` for
    backwards compatibility. This helper keeps these original fields while
    also providing the normalized structure expected by the front-end and
    API clients (``title``, ``price``, ``salePrice``, etc.).
    """

    enriched: List[dict] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        name = item.get("nom") or item.get("title")
        if not name:
            continue
        link = item.get("lien") or item.get("url")
        image = item.get("image")
        sale_text = item.get("prix") or item.get("sale_price") or item.get("salePrice")
        regular_text = item.get("prix_original") or item.get("original_price_text") or item.get("original_price") or item.get("originalPrice")

        sale_value = normalize_price_value(sale_text)
        regular_value = normalize_price_value(item.get("price"))
        parsed_regular_text = normalize_price_value(regular_text)
        if parsed_regular_text is not None:
            regular_value = parsed_regular_text
        if sale_value is None:
            sale_value = normalize_price_value(item.get("sale_price")) or normalize_price_value(item.get("salePrice"))
        if regular_value is None and sale_value is not None:
            regular_value = sale_value
        if sale_value is None and regular_value is not None:
            sale_value = regular_value

        baseline_price = regular_value if regular_value is not None else sale_value

        normalized = {
            "nom": name,
            "prix": sale_text,
            "prix_original": regular_text,
            "image": image,
            "lien": link,
            "title": name,
            "url": link,
            "store": item.get("store") or STORE_NAME,
            "city": item.get("city") or DEFAULT_CITY,
            "currency": item.get("currency") or "CAD",
        }

        if baseline_price is not None:
            normalized["price"] = baseline_price
            normalized.setdefault("original_price", baseline_price)
            normalized.setdefault("originalPrice", baseline_price)
        else:
            normalized["price"] = None

        if regular_value is not None:
            normalized["original_price"] = regular_value
            normalized["originalPrice"] = regular_value

        final_sale = sale_value if sale_value is not None else baseline_price
        normalized["salePrice"] = final_sale
        normalized["sale_price"] = final_sale

        if sale_text:
            normalized.setdefault("priceDisplay", sale_text)
            normalized.setdefault("salePriceDisplay", sale_text)
        if regular_text:
            normalized.setdefault("originalPriceDisplay", regular_text)

        for optional_key in ("brand", "model", "sku", "asin", "branch", "branchSlug"):
            if optional_key in item and item[optional_key] is not None:
                normalized[optional_key] = item[optional_key]

        enriched.append(normalized)

    return enriched


def write_json(items: Iterable[dict], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = list(items)
    temp_path = path.with_suffix(path.suffix + ".tmp")

    try:
        if temp_path.exists():
            temp_path.unlink()
        temp_path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    except OSError as exc:
        logging.error("Unable to write temporary Sporting Life dataset: %s", exc)
        raise

    if path.exists():
        try:
            path.unlink()
            logging.info("Removed previous Sporting Life dataset at %s", path)
        except OSError as exc:
            logging.warning(
                "Unable to remove existing Sporting Life dataset at %s: %s", path, exc
            )

    logging.info("Writing %s products to %s", len(data), path)
    temp_path.replace(path)


def mirror_branch_datasets(items: Iterable[dict], base_path: Path) -> None:
    """Write mirrored JSON files for each tracked Sporting Life branch.

    The front-end expects one JSON payload per branch (Montréal, Laval,
    Saint-Jérôme). Sporting Life publishes a single clearance catalogue, so we
    mirror the unified dataset into these branch-specific filenames while
    adjusting the ``city`` and ``branch`` metadata for display purposes.
    """

    if not BRANCH_MIRRORS:
        logging.debug("No Sporting Life branch mirrors configured; skipping export.")
        return

    for slug, label in BRANCH_MIRRORS:
        branch_items: List[dict] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            cloned = dict(item)
            cloned.setdefault("store", STORE_NAME)
            cloned["city"] = label
            cloned.setdefault("branch", label)
            cloned.setdefault("branchSlug", slug)
            branch_items.append(cloned)

        branch_path = base_path / f"{slug}.json"
        write_json(branch_items, branch_path)


def copy_liquidation_snapshot(
    source: Path, destination: Path = Path("liquidation.json")
) -> None:
    """Copy the generated Sporting Life JSON file to the project root.

    A few legacy workflows expect ``liquidation.json`` to live at the
    repository root. The scraper now writes to ``data/sporting-life`` by
    default, so we opportunistically mirror the file when available.
    """

    if not source.exists():
        logging.error("Fichier introuvable : %s", source)
        return

    try:
        if source.resolve() == destination.resolve():
            logging.debug("Source et destination identiques; copie ignorée.")
            return

        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(source, destination)
        logging.info("Copié %s → %s", source, destination)
    except OSError as exc:
        logging.error("Impossible de copier %s vers %s : %s", source, destination, exc)


def purge_remote_dataset(auth_headers: dict[str, str]) -> None:
    if not API_PURGE_ENABLED or not API_PURGE_URL:
        logging.debug("No purge endpoint configured; skipping remote dataset purge.")
        return

    headers = dict(auth_headers)
    method = API_PURGE_METHOD or "DELETE"
    logging.info(
        "Clearing remote Sporting Life dataset via %s %s", method, API_PURGE_URL
    )

    try:
        response = requests.request(
            method,
            API_PURGE_URL,
            headers=headers,
            timeout=REQUEST_TIMEOUT,
        )
    except requests.RequestException as exc:
        logging.warning("Unable to purge remote Sporting Life dataset: %s", exc)
        return

    if response.status_code == 404:
        logging.info(
            "Purge endpoint %s returned 404; assuming dataset already empty.",
            API_PURGE_URL,
        )
        return

    if response.status_code not in API_PURGE_SUCCESS_STATUSES:
        try:
            response.raise_for_status()
        except requests.HTTPError as exc:
            logging.warning(
                "Unexpected response while purging Sporting Life dataset (%s %s): %s",
                method,
                API_PURGE_URL,
                exc,
            )
        else:
            logging.info(
                "Purge request completed with status %s; continuing with upload.",
                response.status_code,
            )
        return

    logging.info("Remote Sporting Life dataset cleared (status %s)", response.status_code)


def post_to_api(items: Iterable[dict]) -> None:
    if not API_URL:
        logging.info("No API endpoint configured; skipping upload.")
        return

    payload = list(items)
    auth_headers: dict[str, str] = {}
    if API_TOKEN:
        auth_headers["Authorization"] = f"Bearer {API_TOKEN}"

    purge_remote_dataset(auth_headers)

    headers = {"Content-Type": "application/json", **auth_headers}
    if not payload:
        logging.info(
            "Uploading an empty Sporting Life dataset to %s after purge.", API_URL
        )
    else:
        logging.info("Posting %s products to %s", len(payload), API_URL)

    response = requests.post(
        API_URL,
        json=payload,
        headers=headers,
        timeout=REQUEST_TIMEOUT,
    )
    response.raise_for_status()
    logging.info("Upload successful with status %s", response.status_code)


def configure_logging() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")


def main() -> None:
    configure_logging()
    html = fetch_html(SPORTING_LIFE_URL)
    raw_products = parse_products(html)
    deduped_products = deduplicate_products(raw_products)
    if not deduped_products:
        with open("debug_sportinglife.html", "w", encoding="utf-8") as f:
            f.write(html)
        print(
            "⚠️ Aucun produit trouvé. Le code HTML a été sauvegardé dans debug_sportinglife.html pour inspection."
        )
        logging.warning("No products were found on %s", SPORTING_LIFE_URL)
    enriched_products = enrich_products(deduped_products)
    write_json(enriched_products, OUTPUT_PATH)
    mirror_branch_datasets(enriched_products, OUTPUT_PATH.parent)
    copy_liquidation_snapshot(OUTPUT_PATH)
    post_to_api(enriched_products)


if __name__ == "__main__":
    main()
