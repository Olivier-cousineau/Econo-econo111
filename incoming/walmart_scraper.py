"""Scraper Walmart liquidation pages and export JSON feeds for the static site.

Le script ouvre la page liquidation de chaque magasin Walmart défini dans
``magasins`` (ou ``walmart_stores.json``) et extrait les produits en solde.
Chaque exécution génère:

* ``data/walmart/<ville>.json`` – utilisable directement par le site statique
* ``liquidations_walmart_qc.json`` – agrégat de toutes les liquidations

L'extraction repose sur Playwright et tente d'abord de lire les données exposées
dans ``window.__NEXT_DATA__`` / ``window.__PRELOADED_STATE__`` avant de
retomber sur un parcours du DOM. Le script reste tolérant aux échecs (un magasin
en erreur n'empêche pas les autres d'être traités).
"""

from __future__ import annotations

import asyncio
import json
import os
import random
import re
import time
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional
from urllib.parse import urljoin

from playwright.async_api import Browser, BrowserContext, Page, TimeoutError, async_playwright

BASE_URL = "https://www.walmart.ca/fr/store/{store_id}/liquidation"
DEFAULT_HEADLESS = True
MAX_CONCURRENT_BROWSERS = 3
THROTTLE_SECONDS = (2.0, 5.0)
DEFAULT_USER_AGENTS = [
    # Desktop Chrome-like UA strings (rotated pour limiter la détection bot)
    (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/122.0 Safari/537.36"
    ),
    (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_4_1) AppleWebKit/605.1.15 "
        "(KHTML, like Gecko) Version/17.4 Safari/605.1.15"
    ),
    (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/121.0 Safari/537.36"
    ),
]


@dataclass(slots=True)
class Store:
    """Metadata describing a Walmart store."""

    id_store: str
    ville: str
    adresse: str = ""
    slug: Optional[str] = None

    def __post_init__(self) -> None:
        if not self.slug:
            self.slug = slugify(self.ville)

    @property
    def url(self) -> str:
        return BASE_URL.format(store_id=self.id_store)


@dataclass(slots=True)
class Deal:
    """Normalized representation of a liquidation product."""

    title: str
    price: float
    sale_price: float
    url: str
    image: Optional[str] = None

    def to_payload(self, store: Store) -> Dict[str, Any]:
        return {
            "title": self.title,
            "image": self.image or "",
            "price": round(self.price, 2),
            "salePrice": round(self.sale_price, 2),
            "store": "Walmart",
            "city": store.ville,
            "url": self.url,
        }


# Liste des 73 magasins Walmart au Québec (ID, nom, ville, etc.)
# Complétez cette liste avec les identifiants officiels. Vous pouvez aussi créer
# un fichier JSON ``incoming/walmart_stores.json`` avec le même format pour
# personnaliser la configuration sans modifier le code source.
magasins: List[Dict[str, str]] = [
    {"id_store": "1001", "ville": "Montréal", "adresse": "Adresse..."},
    {"id_store": "1002", "ville": "Laval", "adresse": "Adresse..."},
    {"id_store": "1003", "ville": "Saint-Jérôme", "adresse": "Adresse..."},
]

# Liste de proxies résidentiels à utiliser par défaut. L'environnement peut
# aussi fournir une variable ``WALMART_PROXIES`` contenant un JSON (liste de
# chaînes) pour surcharger cette configuration.
PROXIES: List[str] = []


def slugify(value: str) -> str:
    """Return an ASCII slug from a city name (e.g. "Saint-Jérôme" -> "saint-jerome")."""

    normalized = unicodedata.normalize("NFKD", value)
    ascii_only = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    ascii_only = ascii_only.lower()
    ascii_only = re.sub(r"[^a-z0-9]+", "-", ascii_only).strip("-")
    return ascii_only or "store"


def load_proxies() -> List[str]:
    """Load proxy list from ``WALMART_PROXIES`` env var or fall back to defaults."""

    env_value = os.environ.get("WALMART_PROXIES")
    if env_value:
        try:
            parsed = json.loads(env_value)
        except json.JSONDecodeError as exc:
            raise ValueError(
                "WALMART_PROXIES doit contenir une liste JSON (ex: ['http://user:pass@proxy:port'])."
            ) from exc
        if not isinstance(parsed, list) or not all(isinstance(item, str) for item in parsed):
            raise ValueError("WALMART_PROXIES doit être une liste JSON de chaînes de caractères.")
        return parsed

    return PROXIES


def load_stores() -> List[Store]:
    """Return the list of stores declared in the code or in ``walmart_stores.json``."""

    config_path = Path(__file__).with_name("walmart_stores.json")
    if config_path.exists():
        with config_path.open("r", encoding="utf-8") as fh:
            payload = json.load(fh)
        if not isinstance(payload, list):
            raise ValueError("walmart_stores.json doit contenir une liste d'objets magasin.")
        return [Store(**item) for item in payload]

    return [Store(**item) for item in magasins]


def ensure_output_paths() -> Path:
    """Ensure ``data/walmart`` exists and return its path."""

    data_dir = Path(__file__).resolve().parents[1] / "data" / "walmart"
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir


async def throttle() -> None:
    """Sleep asynchronously for a random duration to avoid rate limiting."""

    await asyncio.sleep(random.uniform(*THROTTLE_SECONDS))


def pick_proxy(proxy_pool: List[str]) -> Optional[str]:
    if not proxy_pool:
        return None
    return random.choice(proxy_pool)


def pick_user_agent() -> str:
    return random.choice(DEFAULT_USER_AGENTS)


async def create_browser(playwright, proxy: Optional[str]) -> Browser:
    launch_kwargs: Dict[str, Any] = {
        "headless": DEFAULT_HEADLESS,
        "args": [
            "--disable-blink-features=AutomationControlled",
            "--disable-web-security",
        ],
    }
    if proxy:
        launch_kwargs["proxy"] = {"server": proxy}

    return await playwright.chromium.launch(**launch_kwargs)


async def prepare_context(browser: Browser) -> BrowserContext:
    context = await browser.new_context(
        user_agent=pick_user_agent(),
        locale="fr-CA",
        viewport={"width": 1280, "height": 720},
    )
    await context.add_init_script(
        "Object.defineProperty(navigator, 'webdriver', {get: () => undefined});"
    )
    return context


async def load_store_page(page: Page, url: str) -> None:
    await page.goto(url, wait_until="domcontentloaded", timeout=30_000)
    try:
        await page.wait_for_load_state("networkidle", timeout=10_000)
    except TimeoutError:
        # Certaines pages chargent de manière infinie: on se contente du DOM actuel
        pass


def parse_price(text: Optional[str]) -> Optional[float]:
    if not text:
        return None
    clean = (
        text.replace("\u00a0", " ")
        .replace("$", "")
        .replace("CAD", "")
        .replace("cda", "")
        .strip()
    )
    clean = clean.replace(" ", "")
    match = re.search(r"[0-9]+(?:[.,][0-9]{1,2})?", clean)
    if not match:
        return None
    value = match.group(0).replace(",", ".")
    try:
        return float(value)
    except ValueError:
        return None


def deduplicate_deals(deals: Iterable[Deal]) -> List[Deal]:
    seen: set[str] = set()
    unique: List[Deal] = []
    for deal in deals:
        key = deal.url
        if key in seen:
            continue
        seen.add(key)
        unique.append(deal)
    return unique


async def query_text(handle, selectors: Iterable[str]) -> Optional[str]:
    for selector in selectors:
        element = await handle.query_selector(selector)
        if element is None:
            continue
        text = (await element.inner_text()).strip()
        if text:
            return text
    return None


async def query_attribute(handle, selectors: Iterable[str], attribute: str) -> Optional[str]:
    for selector in selectors:
        element = await handle.query_selector(selector)
        if element is None:
            continue
        value = await element.get_attribute(attribute)
        if value:
            return value
    return None


def extract_from_state(raw_state: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Try to discover product dictionaries within ``raw_state`` recursively."""

    candidates: List[Dict[str, Any]] = []

    def walk(obj: Any) -> None:
        if isinstance(obj, dict):
            if {"name", "price", "productId"}.issubset(obj.keys()):
                candidates.append(obj)
            for value in obj.values():
                walk(value)
        elif isinstance(obj, list):
            for item in obj:
                walk(item)

    walk(raw_state)
    return candidates


def build_deal_from_dict(data: Dict[str, Any]) -> Optional[Deal]:
    title = data.get("name") or data.get("title")
    if not title:
        return None
    url = data.get("productUrl") or data.get("url") or data.get("canonicalUrl")
    if not url:
        return None

    regular_price = data.get("price") or data.get("listPrice") or data.get("regularPrice")
    current_price = data.get("salePrice") or data.get("price") or data.get("offerPrice")

    if isinstance(regular_price, dict):
        regular_price = (
            regular_price.get("price")
            or regular_price.get("amount")
            or regular_price.get("value")
        )
    if isinstance(current_price, dict):
        current_price = (
            current_price.get("price")
            or current_price.get("amount")
            or current_price.get("value")
        )

    price = parse_price(str(regular_price)) if regular_price is not None else None
    sale_price = parse_price(str(current_price)) if current_price is not None else None

    if price is None and sale_price is None:
        return None
    if price is None:
        price = sale_price
    if sale_price is None:
        sale_price = price

    image = None
    images = data.get("image") or data.get("images") or []
    if isinstance(images, list) and images:
        image = images[0]
    elif isinstance(images, dict):
        image = images.get("main") or images.get("large") or images.get("thumbnail")
    elif isinstance(images, str):
        image = images

    return Deal(title=title.strip(), price=price, sale_price=sale_price, url=url, image=image)


async def extract_products_from_dom(page: Page) -> List[Deal]:
    selectors = [
        "[data-automation='product']",
        "div.product",
        "article",
    ]
    cards = []
    for selector in selectors:
        cards = await page.query_selector_all(selector)
        if cards:
            break
    deals: List[Deal] = []
    for card in cards:
        title = await query_text(card, ["h2", "h3", "a[title]"])
        price_text = await query_text(card, [".price", "[data-automation='price']", "span.price"])
        sale_text = await query_text(
            card,
            [
                "[data-automation='secondary-price']",
                ".price-secondary",
                "[data-automation='sale-price']",
            ],
        )
        link = await query_attribute(card, ["a[href]", "[data-automation='product-link']"], "href")
        image = await query_attribute(
            card,
            ["img[data-automation='product-image']", "img"],
            "src",
        )

        if not title or not link:
            continue

        regular_price = parse_price(price_text)
        sale_price = parse_price(sale_text) if sale_text else None
        if regular_price is None and sale_price is None:
            continue
        if regular_price is None:
            regular_price = sale_price
        if sale_price is None:
            sale_price = regular_price

        deals.append(
            Deal(
                title=title.strip(),
                price=regular_price,
                sale_price=sale_price,
                url=urljoin(page.url, link),
                image=image,
            )
        )

    return deals


async def extract_products(page: Page) -> List[Deal]:
    state = await page.evaluate(
        "() => ({nextData: window.__NEXT_DATA__ || null, preloaded: window.__PRELOADED_STATE__ || null})"
    )
    deals: List[Deal] = []

    for key in ("nextData", "preloaded"):
        raw_state = state.get(key)
        if not raw_state:
            continue
        for candidate in extract_from_state(raw_state):
            deal = build_deal_from_dict(candidate)
            if deal:
                deals.append(deal)

    if not deals:
        deals = await extract_products_from_dom(page)

    return deduplicate_deals(deals)


@dataclass(slots=True)
class ScrapeResult:
    store: Store
    deals: List[Deal]
    error: Optional[str] = None


async def scrape_store(playwright, store: Store, proxy_pool: List[str], semaphore: asyncio.Semaphore) -> ScrapeResult:
    proxy = pick_proxy(proxy_pool)
    start_time = time.monotonic()
    browser: Optional[Browser] = None
    context: Optional[BrowserContext] = None
    page: Optional[Page] = None

    try:
        async with semaphore:
            browser = await create_browser(playwright, proxy)
            context = await prepare_context(browser)
            page = await context.new_page()
            await load_store_page(page, store.url)
            await throttle()
            deals = await extract_products(page)
    except Exception as exc:  # noqa: BLE001 - on loggue l'erreur pour le magasin concerné
        return ScrapeResult(store=store, deals=[], error=str(exc))
    finally:
        if page is not None:
            await page.close()
        if context is not None:
            await context.close()
        if browser is not None:
            await browser.close()

    duration = time.monotonic() - start_time
    print(f"✔ {store.ville}: {len(deals)} produits – {duration:.1f}s")
    return ScrapeResult(store=store, deals=deals)


def serialize_deals(results: List[ScrapeResult]) -> Dict[str, List[Dict[str, Any]]]:
    payload: Dict[str, List[Dict[str, Any]]] = {}
    for result in results:
        payload[result.store.slug] = [deal.to_payload(result.store) for deal in result.deals]
    return payload


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2)


async def run() -> None:
    proxy_pool = load_proxies()
    stores = load_stores()
    if not stores:
        raise ValueError("Aucun magasin Walmart n'a été configuré.")

    ensure_output_paths()

    async with async_playwright() as playwright:
        semaphore = asyncio.Semaphore(MAX_CONCURRENT_BROWSERS)
        tasks = [
            scrape_store(playwright, store, proxy_pool, semaphore) for store in stores
        ]
        results = await asyncio.gather(*tasks)

    aggregated: List[Dict[str, Any]] = []
    per_store_data = serialize_deals(results)

    for result in results:
        if result.error:
            print(f"⚠️  {result.store.ville}: {result.error}")
            continue
        store_path = Path(__file__).resolve().parents[1] / "data" / "walmart" / f"{result.store.slug}.json"
        store_payload = per_store_data.get(result.store.slug, [])
        write_json(store_path, store_payload)
        aggregated.extend(store_payload)

    write_json(Path("liquidations_walmart_qc.json"), aggregated)
    print(f"🗂️  Export terminé: {len(aggregated)} produits sur {len(results)} magasins configurés.")


def main() -> None:
    asyncio.run(run())


if __name__ == "__main__":
    main()
