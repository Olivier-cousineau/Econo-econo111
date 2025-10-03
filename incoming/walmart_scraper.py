"""Scraper Walmart liquidation pages and export JSON feeds for the static site.

Le script ouvre la page liquidation de chaque magasin Walmart défini dans
``walmart_stores.json`` et extrait les produits en solde. Chaque exécution
génère:

* ``data/walmart/<ville>.json`` – utilisable directement par le site statique
* ``liquidations_walmart_qc.json`` – agrégat de toutes les liquidations

L'extraction repose sur Playwright et tente d'abord de lire les données exposées
dans ``window.__NEXT_DATA__`` / ``window.__PRELOADED_STATE__`` avant de
retomber sur un parcours du DOM. Le script reste tolérant aux échecs (un magasin
en erreur n'empêche pas les autres d'être traités).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import random
import time
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set
from urllib.parse import urljoin

from playwright.async_api import Browser, BrowserContext, Page, TimeoutError, async_playwright

try:  # Support exécution directe et import en tant que module
    from incoming.walmart_common import (
        Deal,
        Store,
        build_deal_from_dict,
        deduplicate_deals,
        extract_from_state,
        parse_price,
        slugify,
    )
except ImportError:  # pragma: no cover - fallback pour exécution directe
    from walmart_common import (
        Deal,
        Store,
        build_deal_from_dict,
        deduplicate_deals,
        extract_from_state,
        parse_price,
        slugify,
    )
DEFAULT_HEADLESS = True
MAX_CONCURRENT_BROWSERS = 3
DEFAULT_AGGREGATED_FILENAME = "liquidations_walmart_qc.json"
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


# Chemin du fichier contenant la liste exhaustive des magasins Walmart. Le
# fichier ``incoming/walmart_stores.json`` est généré à partir de la source
# ``incoming/walmart_stores_raw.tsv`` et doit être gardé à jour lorsque de
# nouveaux magasins sont ajoutés.
STORES_JSON = Path(__file__).with_name("walmart_stores.json")

# Liste de proxies résidentiels à utiliser par défaut. L'environnement peut
# aussi fournir une variable ``WALMART_PROXIES`` contenant un JSON (liste de
# chaînes) pour surcharger cette configuration.
PROXIES: List[str] = []


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


def _normalise_store_payload(item: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(item, dict):
        raise ValueError("Chaque magasin doit être un objet JSON.")

    if "id_store" not in item:
        raise ValueError("Un magasin du fichier JSON est dépourvu de 'id_store'.")
    if "ville" not in item:
        raise ValueError("Un magasin du fichier JSON est dépourvu de 'ville'.")

    normalised = dict(item)
    normalised["id_store"] = str(normalised["id_store"])
    normalised["ville"] = str(normalised["ville"])
    if "slug" in normalised and normalised["slug"] is not None:
        normalised["slug"] = str(normalised["slug"])
    if "adresse" in normalised and normalised["adresse"] is not None:
        normalised["adresse"] = str(normalised["adresse"])

    return normalised


def _validate_unique_slugs(stores: Sequence[Store]) -> None:
    slugs = [store.slug for store in stores if store.slug]
    duplicates = [slug for slug, count in Counter(slugs).items() if count > 1]
    if duplicates:
        raise ValueError(
            "Plusieurs magasins partagent le même slug: " + ", ".join(sorted(duplicates))
        )


def load_stores() -> List[Store]:
    """Charge la liste des magasins Walmart à partir de ``walmart_stores.json``."""

    if not STORES_JSON.exists():
        raise FileNotFoundError(
            "Le fichier walmart_stores.json est introuvable. Générer le fichier via "
            "incoming/walmart_stores_raw.tsv avant d'exécuter le scraper."
        )

    with STORES_JSON.open("r", encoding="utf-8") as fh:
        payload = json.load(fh)

    if not isinstance(payload, list):
        raise ValueError("walmart_stores.json doit contenir une liste d'objets magasin.")

    stores = [Store(**_normalise_store_payload(item)) for item in payload]
    _validate_unique_slugs(stores)
    return stores


def ensure_output_paths(base_dir: Optional[Path] = None) -> Path:
    """Ensure the per-store output directory exists and return its path."""

    if base_dir is None:
        data_dir = Path(__file__).resolve().parents[1] / "data" / "walmart"
    else:
        data_dir = base_dir
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


async def create_browser(playwright, proxy: Optional[str], *, headless: bool) -> Browser:
    launch_kwargs: Dict[str, Any] = {
        "headless": headless,
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


async def scrape_store(
    playwright,
    store: Store,
    proxy_pool: List[str],
    semaphore: asyncio.Semaphore,
    *,
    headless: bool,
) -> ScrapeResult:
    proxy = pick_proxy(proxy_pool)
    start_time = time.monotonic()
    browser: Optional[Browser] = None
    context: Optional[BrowserContext] = None
    page: Optional[Page] = None

    try:
        async with semaphore:
            browser = await create_browser(playwright, proxy, headless=headless)
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


def normalize_store_token(value: str) -> Set[str]:
    """Return potential identifiers for a store token (slug, lowercase, id)."""

    cleaned = value.strip().lower()
    if not cleaned:
        return set()
    return {cleaned, slugify(cleaned)}


def store_matches_filters(store: Store, filters: Set[str]) -> bool:
    """Check if a ``Store`` matches any of the provided filters."""

    if not filters:
        return True

    candidates: Set[str] = set()
    candidates.add(store.id_store.lower())
    if store.slug:
        candidates.add(store.slug.lower())
    candidates.add(slugify(store.ville))
    candidates.add(store.ville.lower())

    return bool(candidates & filters)


async def run(
    *,
    headless: bool = DEFAULT_HEADLESS,
    store_filters: Optional[Set[str]] = None,
    output_dir: Optional[Path] = None,
    aggregated_path: Optional[Path] = None,
    max_concurrent_browsers: int = MAX_CONCURRENT_BROWSERS,
) -> None:
    proxy_pool = load_proxies()
    stores = load_stores()
    if not stores:
        raise ValueError("Aucun magasin Walmart n'a été configuré.")

    normalized_filters: Set[str] = set()
    if store_filters:
        for item in store_filters:
            normalized_filters.update(normalize_store_token(item))

    if normalized_filters:
        stores = [store for store in stores if store_matches_filters(store, normalized_filters)]
        if not stores:
            raise ValueError("Aucun magasin ne correspond aux filtres fournis.")

    per_store_dir = ensure_output_paths(output_dir)
    aggregated_target = aggregated_path or Path(DEFAULT_AGGREGATED_FILENAME)

    async with async_playwright() as playwright:
        semaphore = asyncio.Semaphore(max_concurrent_browsers)
        tasks = [
            scrape_store(
                playwright,
                store,
                proxy_pool,
                semaphore,
                headless=headless,
            )
            for store in stores
        ]
        results = await asyncio.gather(*tasks)

    aggregated: List[Dict[str, Any]] = []
    per_store_data = serialize_deals(results)

    for result in results:
        if result.error:
            print(f"⚠️  {result.store.ville}: {result.error}")
            continue
        store_path = per_store_dir / f"{result.store.slug}.json"
        store_payload = per_store_data.get(result.store.slug, [])
        write_json(store_path, store_payload)
        aggregated.extend(store_payload)

    write_json(aggregated_target, aggregated)
    processed_stores = len([result for result in results if not result.error])
    print(
        "🗂️  Export terminé: "
        f"{len(aggregated)} produits sur {processed_stores}/{len(results)} magasins traités."
    )


def parse_arguments(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    """Parse CLI arguments for the scraper."""

    parser = argparse.ArgumentParser(description="Scraper les liquidations Walmart au Québec.")
    parser.add_argument(
        "--store",
        "-s",
        action="append",
        dest="stores",
        help="Filtrer les magasins par ID, ville ou slug (utilisable plusieurs fois).",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Dossier de sortie pour les fichiers JSON par magasin (défaut: data/walmart).",
    )
    parser.add_argument(
        "--aggregated-path",
        type=Path,
        default=None,
        help="Chemin du fichier JSON agrégé (défaut: liquidations_walmart_qc.json).",
    )
    parser.add_argument(
        "--max-concurrent-browsers",
        type=int,
        default=MAX_CONCURRENT_BROWSERS,
        help="Nombre maximum de navigateurs Playwright exécutés en parallèle.",
    )
    parser.add_argument(
        "--no-headless",
        dest="headless",
        action="store_false",
        help="Désactive le mode headless pour déboguer le navigateur.",
    )
    parser.set_defaults(headless=DEFAULT_HEADLESS)
    return parser.parse_args(argv)


def main() -> None:
    args = parse_arguments()
    store_filters = set(args.stores) if args.stores else None
    asyncio.run(
        run(
            headless=args.headless,
            store_filters=store_filters,
            output_dir=args.output_dir,
            aggregated_path=args.aggregated_path,
            max_concurrent_browsers=args.max_concurrent_browsers,
        )
    )


if __name__ == "__main__":
    main()
