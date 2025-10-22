"""Canadian Tire liquidation scraper.

This script collects clearance products from the Canadian Tire
liquidation page for a configurable store (Saint-Jérôme by default).
It mirrors the Sporting Life scraper structure so it can run in the
same automation pipeline.
"""
from __future__ import annotations

import json
import logging
import os
import re
import subprocess
import sys
import unicodedata
from pathlib import Path
from typing import Any, Dict, Iterable, Iterator, List, Optional, Sequence
from urllib.parse import parse_qs, urlencode, urljoin, urlparse, urlunparse

import requests
from bs4 import BeautifulSoup
from requests.cookies import create_cookie

try:
    from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
    from playwright.sync_api import sync_playwright
except ImportError:  # pragma: no cover - optional dependency path
    PlaywrightTimeoutError = Exception  # type: ignore[assignment]
    sync_playwright = None  # type: ignore[assignment]


BASE_DIR = Path(__file__).resolve().parent
DEFAULT_URL = "https://www.canadiantire.ca/fr/promotions/liquidation.html"
CANADIAN_TIRE_URL = os.getenv("CANADIAN_TIRE_URL", DEFAULT_URL)
STORE_ID = os.getenv("CANADIAN_TIRE_STORE_ID", "0271")
STORE_SLUG = os.getenv("CANADIAN_TIRE_STORE_SLUG", "saint-jerome")
STORE_CITY = os.getenv("CANADIAN_TIRE_CITY", "Saint-Jérôme")
STORE_NAME = os.getenv("CANADIAN_TIRE_STORE_NAME", "Canadian Tire")
REQUEST_TIMEOUT = int(os.getenv("CANADIAN_TIRE_TIMEOUT", "30"))
PLAYWRIGHT_TIMEOUT = int(
    os.getenv("CANADIAN_TIRE_PLAYWRIGHT_TIMEOUT", str(REQUEST_TIMEOUT * 1000))
)
USER_AGENT = os.getenv(
    "CANADIAN_TIRE_USER_AGENT",
    (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"
    ),
)
USE_PLAYWRIGHT = os.getenv("CANADIAN_TIRE_USE_PLAYWRIGHT", "1").lower() not in {
    "0",
    "false",
    "no",
}
STORE_COOKIE_CANDIDATES = (
    "preferredStore",
    "preferred_store",
    "preferredStoreId",
    "storeId",
    "store_id",
    "selected_store",
    "ctPreferredStore",
    "preferred_store_id",
)
API_URL = os.getenv("ECONODEAL_API_URL")
API_TOKEN = os.getenv("ECONODEAL_API_TOKEN")


NAME_KEY_CANDIDATES = (
    "title",
    "name",
    "productName",
    "productTitle",
    "ctaText",
)
URL_KEY_CANDIDATES = (
    "url",
    "link",
    "productUrl",
    "pdpUrl",
    "canonicalUrl",
    "href",
)
IMAGE_KEY_CANDIDATES = (
    "image",
    "imageUrl",
    "imageSrc",
    "imageHref",
    "primaryImage",
    "featuredImage",
    "thumbnail",
    "imageLink",
)
SALE_PRICE_KEYS = {
    "saleprice",
    "sale",
    "salesprice",
    "salepricevalue",
    "clearanceprice",
    "promoprice",
}
REGULAR_PRICE_KEYS = {
    "regularprice",
    "listprice",
    "regprice",
    "originalprice",
    "regularpricevalue",
    "pricewithoutdiscount",
}
GENERIC_PRICE_KEYS = {"price", "pricevalue", "currentprice", "pricing"}

_PLAYWRIGHT_BROWSERS_READY = False


def slugify(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    ascii_value = normalized.encode("ascii", "ignore").decode("ascii")
    ascii_value = re.sub(r"[^a-zA-Z0-9]+", "-", ascii_value)
    ascii_value = ascii_value.strip("-")
    return ascii_value.lower() or "store"



def _normalize_key(key: str) -> str:
    return re.sub(r"[^a-z]", "", key.lower())


def _coerce_to_string(value: Any) -> Optional[str]:
    if isinstance(value, str):
        cleaned = value.strip()
        return cleaned or None
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, list):
        for item in value:
            candidate = _coerce_to_string(item)
            if candidate:
                return candidate
        return None
    if isinstance(value, dict):
        for key in ("url", "value", "raw", "text", "label"):
            if key in value:
                candidate = _coerce_to_string(value[key])
                if candidate:
                    return candidate
        return None
    return None


def _coerce_price(value: Any) -> Optional[float]:
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        return parse_price(value)
    if isinstance(value, list):
        for item in value:
            candidate = _coerce_price(item)
            if candidate is not None:
                return candidate
        return None
    if isinstance(value, dict):
        for key in ("value", "amount", "price", "sale", "regular", "current"):
            if key in value:
                candidate = _coerce_price(value[key])
                if candidate is not None:
                    return candidate
        return None
    return None


def _find_string(data: Any, candidates: Sequence[str]) -> Optional[str]:
    target_keys = {_normalize_key(key) for key in candidates}
    queue: List[Any] = [data]
    seen: set[int] = set()
    while queue:
        node = queue.pop(0)
        if isinstance(node, dict):
            node_id = id(node)
            if node_id in seen:
                continue
            seen.add(node_id)
            for key, value in node.items():
                normalized_key = _normalize_key(key)
                if normalized_key in target_keys:
                    result = _coerce_to_string(value)
                    if result:
                        return result
                if isinstance(value, (dict, list)):
                    queue.append(value)
        elif isinstance(node, list):
            queue.extend(node)
    return None


def _find_price(data: Any, prefer_sale: bool) -> Optional[float]:
    queue: List[Any] = [data]
    seen: set[int] = set()
    generic_candidates: List[float] = []
    while queue:
        node = queue.pop(0)
        if isinstance(node, dict):
            node_id = id(node)
            if node_id in seen:
                continue
            seen.add(node_id)
            for key, value in node.items():
                normalized_key = _normalize_key(key)
                if normalized_key in SALE_PRICE_KEYS:
                    price = _coerce_price(value)
                    if price is not None:
                        if prefer_sale:
                            return price
                        generic_candidates.append(price)
                elif normalized_key in REGULAR_PRICE_KEYS:
                    price = _coerce_price(value)
                    if price is not None:
                        if not prefer_sale:
                            return price
                        generic_candidates.append(price)
                elif normalized_key in GENERIC_PRICE_KEYS:
                    price = _coerce_price(value)
                    if price is not None:
                        generic_candidates.append(price)
                if isinstance(value, (dict, list)):
                    queue.append(value)
        elif isinstance(node, list):
            queue.extend(node)
    if generic_candidates:
        return generic_candidates[0]
    return None


def _product_score(data: Dict[str, Any]) -> int:
    score = 0
    if _find_string(data, NAME_KEY_CANDIDATES):
        score += 2
    if _find_string(data, URL_KEY_CANDIDATES):
        score += 2
    if _find_price(data, prefer_sale=True) is not None:
        score += 1
    if _find_string(data, IMAGE_KEY_CANDIDATES):
        score += 1
    return score


def ensure_playwright_browsers_installed() -> None:
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


def _load_store_metadata(
    store_id: Optional[str],
    store_slug: Optional[str],
    store_city: Optional[str],
    store_name: str,
) -> tuple[str, str, str]:
    slug = store_slug or None
    city = store_city or None
    name = store_name or "Canadian Tire"
    stores_path = BASE_DIR / "data" / "canadian-tire" / "stores.json"
    stores_data: list[dict[str, Any]] = []
    if stores_path.exists():
        try:
            stores_data = json.loads(stores_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):  # pragma: no cover - best effort
            stores_data = []

    selected_entry: Optional[dict[str, Any]] = None
    if store_id:
        selected_entry = next(
            (entry for entry in stores_data if entry.get("store_id") == store_id),
            None,
        )
    if selected_entry is None and slug:
        selected_entry = next(
            (entry for entry in stores_data if entry.get("slug") == slug),
            None,
        )

    if selected_entry:
        slug = slug or selected_entry.get("slug")
        if not city:
            city = selected_entry.get("nickname") or selected_entry.get("city")
        label = selected_entry.get("label") or selected_entry.get("nickname")
        if label:
            name = re.sub(r"^Canadian Tire\s*", "Canadian Tire ", label).strip()

    if not slug:
        slug = slugify(city or name)
    if not city:
        city = "online"
    return name or "Canadian Tire", city, slug


STORE_NAME, STORE_CITY, STORE_SLUG = _load_store_metadata(
    STORE_ID, STORE_SLUG, STORE_CITY, STORE_NAME
)
DEFAULT_OUTPUT_PATH = (
    BASE_DIR / "data" / "canadian-tire" / f"{STORE_SLUG or 'canadian-tire'}.json"
)
OUTPUT_PATH = Path(os.getenv("CANADIAN_TIRE_OUTPUT", str(DEFAULT_OUTPUT_PATH)))



def format_url(template: str, store_id: Optional[str], store_slug: Optional[str]) -> str:
    values = {
        "store_id": store_id or "",
        "storeId": store_id or "",
        "store_slug": store_slug or "",
        "storeSlug": store_slug or "",
    }
    try:
        formatted = template.format(**values)
    except KeyError:
        formatted = template

    parsed = urlparse(formatted)
    query = parse_qs(parsed.query, keep_blank_values=True)
    if store_id:
        if not any(key in query for key in ("storeId", "store", "store_id")):
            query["storeId"] = [store_id]
            formatted = urlunparse(
                parsed._replace(query=urlencode(query, doseq=True))
            )
    return formatted


def build_target_url() -> str:
    return format_url(CANADIAN_TIRE_URL, STORE_ID, STORE_SLUG)


def _add_store_cookies(session: requests.Session) -> None:
    if not STORE_ID:
        return
    for name in STORE_COOKIE_CANDIDATES:
        cookie = create_cookie(name=name, value=STORE_ID, domain=".canadiantire.ca", path="/")
        session.cookies.set_cookie(cookie)


def fetch_html_with_requests(url: str) -> str:
    logging.info("Fetching Canadian Tire liquidation page via requests: %s", url)
    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": USER_AGENT,
            "Accept-Language": "fr-CA,fr;q=0.9,en;q=0.8",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Connection": "keep-alive",
        }
    )
    _add_store_cookies(session)
    response = session.get(url, timeout=REQUEST_TIMEOUT)
    response.raise_for_status()
    return response.text


def _build_store_storage_payload() -> str:
    payload = {
        "storeNumber": STORE_ID,
        "storeId": STORE_ID,
        "id": STORE_ID,
        "city": STORE_CITY,
        "nickname": STORE_CITY,
        "slug": STORE_SLUG,
        "storeName": STORE_NAME,
    }
    return json.dumps(payload, ensure_ascii=False)


def fetch_html_with_playwright(url: str) -> str:
    if sync_playwright is None:  # pragma: no cover - optional dependency path
        raise RuntimeError("Playwright is not installed")

    ensure_playwright_browsers_installed()

    logging.info("Fetching Canadian Tire liquidation page via Playwright: %s", url)
    browser = None
    context = None
    content: Optional[str] = None
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            context = browser.new_context(
                user_agent=USER_AGENT,
                locale="fr-CA",
                extra_http_headers={
                    "Accept-Language": "fr-CA,fr;q=0.9,en;q=0.8",
                },
            )
            if STORE_ID:
                storage_payload = _build_store_storage_payload()
                context.add_init_script(
                    """
                    (storeJson) => {
                        try {
                            window.localStorage.setItem('preferredStore', storeJson);
                            window.localStorage.setItem('selectedStore', storeJson);
                            window.localStorage.setItem('preferredStoreId', JSON.parse(storeJson).storeId || '');
                            window.sessionStorage.setItem('preferredStore', storeJson);
                            window.sessionStorage.setItem('preferredStoreId', JSON.parse(storeJson).storeId || '');
                        } catch (err) {
                            console.debug('Unable to seed store localStorage', err);
                        }
                    }
                    """,
                    storage_payload,
                )
                cookies = [
                    {
                        "name": name,
                        "value": STORE_ID,
                        "domain": ".canadiantire.ca",
                        "path": "/",
                    }
                    for name in STORE_COOKIE_CANDIDATES
                ]
                context.add_cookies(cookies)
            page = context.new_page()
            page.goto(url, wait_until="networkidle", timeout=PLAYWRIGHT_TIMEOUT)
            try:
                page.wait_for_load_state("networkidle", timeout=PLAYWRIGHT_TIMEOUT)
            except PlaywrightTimeoutError:
                logging.debug("Network idle state timeout for %s", url)

            load_all_products(page)

            tile_selector = (
                "article[data-product-id], li[data-product-id], li[data-productid], "
                "div[data-product-id], div[data-productid], div[data-testid=\"product-card\"], "
                "div[data-testid=\"product-tile\"], div.product-tile"
            )
            try:
                page.wait_for_selector(tile_selector, timeout=PLAYWRIGHT_TIMEOUT)
            except PlaywrightTimeoutError:
                logging.warning("Timed out waiting for product tiles on %s", url)

            try:
                tile_count = page.evaluate(
                    """(selector) => document.querySelectorAll(selector).length""",
                    tile_selector,
                )
            except Exception:
                tile_count = 0
                logging.debug(
                    "Unable to count product tiles after loading Canadian Tire page",
                    exc_info=True,
                )
            logging.info("Playwright collected %s product tiles", tile_count)
            content = page.content()
    except PlaywrightTimeoutError as exc:
        logging.error("Playwright timed out fetching %s: %s", url, exc)
        raise
    finally:
        try:
            if context:
                context.close()
        except Exception:  # pragma: no cover - best effort cleanup
            pass
        try:
            if browser:
                browser.close()
        except Exception:  # pragma: no cover - best effort cleanup
            pass
    if content is None:
        raise RuntimeError("Playwright did not return any page content")
    return content


def load_all_products(page, max_clicks: int = 400) -> None:
    try:
        cookie_btn = page.locator(
            "button:has-text('Accepter'), button:has-text('J'accepte'), button:has-text('Accept')"
        )
        if cookie_btn.count() > 0:
            cookie_btn.first.click(timeout=3000)
    except Exception:
        pass

    tile_selector = (
        "article[data-product-id], li[data-product-id], li[data-productid], "
        "div[data-product-id], div[data-productid], div[data-testid=\"product-card\"], "
        "div[data-testid=\"product-tile\"], div.product-tile"
    )

    def tiles_count() -> int:
        try:
            return int(
                page.evaluate(
                    "(selector) => document.querySelectorAll(selector).length",
                    tile_selector,
                )
            )
        except Exception:
            return 0

    last_count = tiles_count()
    logging.debug("Initial product tile count: %s", last_count)

    for _ in range(max_clicks):
        button = page.locator(
            "button:has-text('Afficher plus'), button:has-text('Voir plus'), "
            "button:has-text('Load more'), button:has-text('Show more'), "
            "button.load-more, [role='button']:has-text('Afficher plus'), "
            "[role='button']:has-text('Show more')"
        )
        count = button.count()
        if count == 0:
            break
        candidate = None
        for index in range(count):
            current = button.nth(index)
            try:
                if current.is_visible() and current.is_enabled():
                    candidate = current
                    break
            except Exception:
                continue
        if candidate is None:
            break
        candidate.scroll_into_view_if_needed()
        candidate.click()
        try:
            page.wait_for_timeout(400)
        except Exception:
            pass
        try:
            page.wait_for_function(
                """(selector, previous) => {
                    return document.querySelectorAll(selector).length > previous;
                }""",
                tile_selector,
                last_count,
                timeout=15000,
            )
        except PlaywrightTimeoutError:
            try:
                page.wait_for_load_state("networkidle", timeout=8000)
            except PlaywrightTimeoutError:
                pass
        current_count = tiles_count()
        logging.debug("Product tile count after load more: %s", current_count)
        if current_count <= last_count:
            break
        last_count = current_count


def fetch_html(url: str) -> str:
    if USE_PLAYWRIGHT:
        try:
            return fetch_html_with_playwright(url)
        except Exception:
            logging.exception("Playwright fetch failed, falling back to requests")
    return fetch_html_with_requests(url)


def parse_price(text: Optional[str]) -> Optional[float]:
    if text is None:
        return None
    normalized = (
        text.replace("\xa0", " ")
        .replace("\u202f", " ")
        .replace("CAD", "")
        .replace("$", "")
    )
    normalized = normalized.strip()
    if not normalized:
        return None
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



def _load_json_safely(candidate: str) -> Optional[Any]:
    text = candidate.strip()
    if not text:
        return None
    if text.startswith("window") or text.startswith("var "):
        brace_index = min(
            (index for index in (text.find("{"), text.find("[")) if index >= 0),
            default=-1,
        )
        if brace_index >= 0:
            text = text[brace_index:]
        semicolon_index = text.rfind(";")
        if semicolon_index > text.rfind("}") and semicolon_index > text.rfind("]"):
            text = text[:semicolon_index]
    attempts = [text, text.rstrip(";"), text.replace("\n", "\n")]  # best effort
    for attempt in attempts:
        try:
            return json.loads(attempt)
        except json.JSONDecodeError:
            continue
    return None


def iter_embedded_json_strings(html: str, soup: Optional[BeautifulSoup] = None) -> Iterator[str]:
    if soup is None:
        soup = BeautifulSoup(html, "html.parser")
    if soup:
        script = soup.find("script", id="__NEXT_DATA__")
        if script and script.string:
            yield script.string.strip()
        for script_tag in soup.find_all("script"):
            if script_tag.get("type") == "application/json" and script_tag.string:
                yield script_tag.string.strip()
    patterns = [
        re.compile(r"window\.__NUXT__\s*=\s*(\{.*?\})\s*;", re.DOTALL),
        re.compile(r"window\.__INITIAL_STATE__\s*=\s*(\{.*?\})\s*;", re.DOTALL),
        re.compile(r"window\.__APOLLO_STATE__\s*=\s*(\{.*?\})\s*;", re.DOTALL),
        re.compile(r"window\.__NEXT_DATA__\s*=\s*(\{.*?\})\s*;", re.DOTALL),
    ]
    for pattern in patterns:
        for match in pattern.finditer(html):
            yield match.group(1)


def search_product_dicts(data: Any) -> Iterator[Dict[str, Any]]:
    seen: set[int] = set()

    def _walk(node: Any) -> Iterator[Dict[str, Any]]:
        if isinstance(node, dict):
            node_id = id(node)
            if node_id in seen:
                return
            seen.add(node_id)
            if _product_score(node) >= 3:
                yield node
            for value in node.values():
                yield from _walk(value)
        elif isinstance(node, list):
            for item in node:
                yield from _walk(item)

    yield from _walk(data)


def normalize_product(raw: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    name = _find_string(raw, NAME_KEY_CANDIDATES)
    url_value = _find_string(raw, URL_KEY_CANDIDATES)
    image_value = _find_string(raw, IMAGE_KEY_CANDIDATES)
    sale_price = _find_price(raw, prefer_sale=True)
    regular_price = _find_price(raw, prefer_sale=False)

    if regular_price is None and sale_price is not None:
        regular_price = sale_price
    if sale_price is None and regular_price is not None:
        sale_price = regular_price

    if not name or not url_value:
        return None

    try:
        full_url = urljoin(CANADIAN_TIRE_URL, url_value)
    except Exception:
        full_url = url_value
    image_url: Optional[str] = None
    if image_value:
        try:
            image_url = urljoin(CANADIAN_TIRE_URL, image_value)
        except Exception:
            image_url = image_value

    return {
        "title": name,
        "store": STORE_NAME,
        "city": STORE_CITY,
        "image": image_url,
        "price": regular_price,
        "salePrice": sale_price,
        "url": full_url,
    }


def parse_json_ld_products(soup: BeautifulSoup) -> List[Dict[str, Any]]:
    products: List[Dict[str, Any]] = []

    def _iter_json_ld_entities(payload: Any) -> Iterator[Dict[str, Any]]:
        if isinstance(payload, list):
            for element in payload:
                yield from _iter_json_ld_entities(element)
        elif isinstance(payload, dict):
            types = payload.get("@type")
            if isinstance(types, str):
                type_names = {types.lower()}
            elif isinstance(types, list):
                type_names = {str(item).lower() for item in types}
            else:
                type_names = set()
            if "product" in type_names:
                yield payload
            if "itemlist" in type_names:
                items = payload.get("itemListElement") or payload.get("item")
                if isinstance(items, list):
                    for element in items:
                        if isinstance(element, dict):
                            target = element.get("item") or element.get("@item") or element
                            yield from _iter_json_ld_entities(target)
            for value in payload.values():
                if isinstance(value, (dict, list)):
                    yield from _iter_json_ld_entities(value)

    for script in soup.select('script[type="application/ld+json"]'):
        text = script.string or script.get_text()
        if not text:
            continue
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            # Some JSON-LD payloads might contain multiple objects without wrapping
            text = text.strip()
            if text.endswith("}") and text.count("}") > text.count("{"):
                closing_index = text.rfind("}")
                text = text[: closing_index + 1]
            try:
                data = json.loads(text)
            except json.JSONDecodeError:
                continue
        for entity in _iter_json_ld_entities(data):
            normalized = normalize_product(entity)
            if normalized:
                products.append(normalized)
    return products


def parse_state_products(html: str, soup: Optional[BeautifulSoup] = None) -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    for candidate in iter_embedded_json_strings(html, soup):
        data = _load_json_safely(candidate)
        if data is None:
            continue
        for product_dict in search_product_dicts(data):
            normalized = normalize_product(product_dict)
            if normalized:
                items.append(normalized)
    return items


def get_text(element) -> Optional[str]:
    if element is None:
        return None
    text = element.get_text(" ", strip=True)
    return text or None


def extract_image_url(tile) -> Optional[str]:
    if tile is None:
        return None
    image_tag = tile.select_one("img")
    if not image_tag:
        return None
    for attribute in ("data-src", "data-original", "data-srcset", "srcset", "src"):
        value = image_tag.get(attribute)
        if not value:
            continue
        if attribute.endswith("srcset"):
            value = value.split(",")[0].strip().split(" ")[0]
        return urljoin(CANADIAN_TIRE_URL, value)
    return None


def parse_dom_products(soup: BeautifulSoup) -> List[Dict[str, Any]]:
    selectors = [
        "[data-testid='product-card']",
        "[data-test='product-card']",
        "article[data-product-id]",
        "li[data-product-id]",
        "li[data-productid]",
        "div[data-product-id]",
        "div[data-productid]",
        "div.product-tile",
        "li.product-tile",
    ]
    products: List[Dict[str, Any]] = []
    seen_tiles: set[int] = set()
    for selector in selectors:
        for tile in soup.select(selector):
            tile_id = id(tile)
            if tile_id in seen_tiles:
                continue
            seen_tiles.add(tile_id)
            name = get_text(
                tile.select_one(
                    "a[title], a .product-name, .product-name, h2, h3, h4, .product__title"
                )
            )
            if not name:
                name = get_text(tile.select_one("a"))
            link_tag = tile.select_one("a[href]")
            url_value = urljoin(CANADIAN_TIRE_URL, link_tag["href"]) if link_tag else None
            sale_text = get_text(
                tile.select_one(
                    ".price__sale, .sale-price, .price--sale, [data-testid='sale-price']"
                )
            )
            regular_text = get_text(
                tile.select_one(
                    ".price__regular, .regular-price, .price--regular, [data-testid='regular-price']"
                )
            )
            price_text = get_text(
                tile.select_one(
                    ".price, .product-price, .price__value, [data-testid='price'], .pricing"
                )
            )
            image_url = extract_image_url(tile)
            sale_price = parse_price(sale_text or price_text)
            regular_price = parse_price(regular_text or price_text)
            if sale_price is None and regular_price is not None:
                sale_price = regular_price
            if regular_price is None and sale_price is not None:
                regular_price = sale_price
            if not name or not url_value:
                continue
            products.append(
                {
                    "title": name,
                    "store": STORE_NAME,
                    "city": STORE_CITY,
                    "image": image_url,
                    "price": regular_price,
                    "salePrice": sale_price,
                    "url": url_value,
                }
            )
    return products


def parse_products(html: str) -> List[Dict[str, Any]]:
    soup = BeautifulSoup(html, "html.parser")
    products = parse_json_ld_products(soup)
    state_products = parse_state_products(html, soup)
    dom_products = parse_dom_products(soup)
    combined = products + state_products + dom_products
    return deduplicate_products(combined)


def deduplicate_products(items: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    seen: set[str] = set()
    result: List[Dict[str, Any]] = []
    for item in items:
        url = item.get("url") or ""
        key = url or item.get("title") or ""
        if not key:
            continue
        if key in seen:
            continue
        seen.add(key)
        result.append(item)
    return result


def write_json(items: Iterable[Dict[str, Any]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = list(items)
    logging.info("Writing %s products to %s", len(data), path)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def post_to_api(items: Iterable[Dict[str, Any]]) -> None:
    if not API_URL:
        logging.info("No API endpoint configured; skipping upload.")
        return

    payload = list(items)
    headers = {"Content-Type": "application/json"}
    if API_TOKEN:
        headers["Authorization"] = f"Bearer {API_TOKEN}"

    logging.info("Posting %s products to %s", len(payload), API_URL)
    response = requests.post(API_URL, json=payload, headers=headers, timeout=REQUEST_TIMEOUT)
    response.raise_for_status()
    logging.info("Upload successful with status %s", response.status_code)


def configure_logging() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")



def main() -> None:
    configure_logging()
    target_url = build_target_url()
    logging.info(
        "Scraping Canadian Tire liquidation for store %s (%s)",
        STORE_NAME,
        STORE_CITY,
    )
    html = fetch_html(target_url)
    products = parse_products(html)
    if not products:
        debug_path = BASE_DIR / "debug_canadiantire.html"
        debug_path.write_text(html, encoding="utf-8")
        print(
            "⚠️ Aucun produit trouvé. Le HTML a été sauvegardé dans debug_canadiantire.html pour inspection."
        )
        logging.warning("No products were found on %s", target_url)
    write_json(products, OUTPUT_PATH)
    post_to_api(products)


if __name__ == "__main__":
    main()
