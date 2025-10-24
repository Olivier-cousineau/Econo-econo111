"""Scrape Canadian Tire liquidation listings for a specific store.

The scraper opens ``https://www.canadiantire.ca/fr/promotions/liquidation.html``
with the store preference primed (default: Blainville, QC) and extracts the
product payload exposed on the page by Next.js. The resulting items are stored
as JSON at ``data/canadian-tire/blainville.json`` by default.

The script is intentionally defensive: the Canadian Tire front-end changes
frequently and exposes product information in slightly different shapes.  The
extraction helpers therefore try multiple fallbacks for every field to keep the
scraper resilient.
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Iterator, List, Optional, Sequence, Tuple
from urllib.parse import urljoin

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright


DEFAULT_URL = "https://www.canadiantire.ca/fr/promotions/liquidation.html"
DEFAULT_OUTPUT = Path("data/canadian-tire/blainville.json")
DEFAULT_STORE_ID = "041"
DEFAULT_STORE_NAME = "Blainville"
DEFAULT_PROVINCE = "QC"
DEFAULT_STORE_BRAND = "Canadian Tire"
DEFAULT_CITY = "Blainville"

_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

_CONSENT_SELECTORS = (
    "button#onetrust-accept-btn-handler",
    "button[data-testid='onetrust-accept-btn']",
    "button[data-tracking-label='accept all cookies']",
    "button:has-text(\"Accepter\")",
    "button:has-text(\"Tout accepter\")",
)

_LOAD_MORE_SELECTORS = (
    "button[data-testid='load-more']",
    "button.load-more__button",
    "button:has-text(\"Charger plus\")",
    "button:has-text(\"Afficher plus\")",
)

_PRODUCT_SCORE_KEYS = {
    "productNumber",
    "productId",
    "productCode",
    "productUrl",
    "sku",
    "name",
}


@dataclass
class Product:
    title: str
    url: str
    image: str
    brand: str
    sku: str
    price: Optional[float]
    salePrice: Optional[float]
    store: str
    city: str
    badges: List[str]
    cta: str
    rating: Optional[float]
    ratingCount: Optional[int]
    availability: Optional[str]
    stockNotice: Optional[str]
    badgeImage: Optional[str]
    checkboxLabel: Optional[str]
    colourOptions: Optional[List[str]]
    rebate: Optional[str]
    rebateDetails: Optional[str]


def _coerce_price(value: object) -> Optional[float]:
    if value in (None, "", "N/A"):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        cleaned = (
            value.replace("$", "")
            .replace("\u00a0", "")
            .replace("\xa0", "")
            .replace(" ", "")
            .replace(",", ".")
        )
        try:
            return float(cleaned)
        except ValueError:
            digits = "".join(ch for ch in cleaned if ch.isdigit() or ch == ".")
            if digits:
                try:
                    return float(digits)
                except ValueError:
                    return None
    return None


def _coerce_int(value: object) -> Optional[int]:
    if value in (None, ""):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        digits = "".join(ch for ch in value if ch.isdigit())
        if digits:
            try:
                return int(digits)
            except ValueError:
                return None
    return None


def _coerce_str(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, str):
        return value.strip()
    return ""


def _ensure_list(value: object) -> List[object]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def _first(*values: object) -> object:
    for value in values:
        if value:
            return value
    return None


def _extract_badges(node: dict) -> Tuple[List[str], Optional[str]]:
    badges: List[str] = []
    badge_image: Optional[str] = None
    for key in ("badges", "badgeList", "badge", "badgeImages", "badgesList"):
        raw_list = node.get(key)
        if not raw_list:
            continue
        for badge in _ensure_list(raw_list):
            if isinstance(badge, str):
                text = badge.strip()
                if text and text not in badges:
                    badges.append(text)
            elif isinstance(badge, dict):
                text = _coerce_str(
                    _first(
                        badge.get("text"),
                        badge.get("label"),
                        badge.get("name"),
                        badge.get("title"),
                    )
                )
                if text and text not in badges:
                    badges.append(text)
                if not badge_image:
                    candidate = _first(
                        badge.get("image"),
                        badge.get("icon"),
                        badge.get("badgeImage"),
                        badge.get("url"),
                    )
                    if isinstance(candidate, dict):
                        candidate = _first(
                            candidate.get("src"),
                            candidate.get("url"),
                        )
                    if isinstance(candidate, str) and candidate:
                        badge_image = candidate
    return badges, badge_image


def _extract_colour_options(node: dict) -> Optional[List[str]]:
    colours: List[str] = []
    for key in ("swatchColours", "colourOptions", "colours", "colorOptions"):
        raw = node.get(key)
        if not raw:
            continue
        for option in _ensure_list(raw):
            if isinstance(option, str):
                text = option.strip()
                if text and text not in colours:
                    colours.append(text)
            elif isinstance(option, dict):
                text = _coerce_str(
                    _first(option.get("label"), option.get("name"), option.get("color"))
                )
                if text and text not in colours:
                    colours.append(text)
    return colours or None


def _resolve_image(node: dict) -> str:
    candidate = _first(
        node.get("image"),
        node.get("imageUrl"),
        node.get("imageURL"),
        node.get("imageSrc"),
        node.get("primaryImage"),
        node.get("thumbnailUrl"),
    )
    if isinstance(candidate, dict):
        candidate = _first(
            candidate.get("src"),
            candidate.get("url"),
            candidate.get("image"),
        )
    return _coerce_str(candidate)


def _resolve_url(base_url: str, node: dict) -> str:
    candidate = _first(
        node.get("productUrl"),
        node.get("pdpUrl"),
        node.get("canonicalUrl"),
        node.get("url"),
    )
    url = _coerce_str(candidate)
    if url.startswith("http"):
        return url
    return urljoin(base_url, url)


def _resolve_brand(node: dict) -> str:
    brand = node.get("brand")
    if isinstance(brand, dict):
        return _coerce_str(
            _first(
                brand.get("name"),
                brand.get("label"),
                brand.get("title"),
            )
        )
    return _coerce_str(_first(brand, node.get("brandName"), node.get("brandLabel")))


def _resolve_sku(node: dict) -> str:
    return _coerce_str(
        _first(
            node.get("sku"),
            node.get("productNumber"),
            node.get("productCode"),
            node.get("id"),
        )
    )


def _resolve_price(node: dict) -> Tuple[Optional[float], Optional[float]]:
    price_candidates = [
        ("price", "regular"),
        ("price", "original"),
        ("pricing", "regular"),
        ("pricing", "price"),
        ("wasPrice",),
        ("regularPrice",),
    ]
    sale_candidates = [
        ("price", "current"),
        ("price", "sale"),
        ("pricing", "current"),
        ("pricing", "sale"),
        ("salePrice",),
        ("currentPrice",),
        ("price", "value"),
    ]

    def pick(paths: Sequence[Tuple[str, ...]]) -> Optional[float]:
        for path in paths:
            node_ref: object = node
            for key in path:
                if not isinstance(node_ref, dict):
                    break
                node_ref = node_ref.get(key)
            else:
                price = _coerce_price(node_ref)
                if price is not None:
                    return price
        return None

    price = pick(price_candidates)
    sale = pick(sale_candidates)
    if price is None and sale is not None:
        price = sale
    return price, sale


def _resolve_rating(node: dict) -> Tuple[Optional[float], Optional[int]]:
    rating_candidates = [
        ("rating",),
        ("averageRating",),
        ("reviews", "averageRating"),
        ("reviewSummary", "averageRating"),
    ]
    count_candidates = [
        ("ratingCount",),
        ("reviews", "totalReviewCount"),
        ("reviewSummary", "totalReviewCount"),
        ("reviews", "reviewCount"),
    ]

    def pick_float(paths: Sequence[Tuple[str, ...]]) -> Optional[float]:
        for path in paths:
            node_ref: object = node
            for key in path:
                if not isinstance(node_ref, dict):
                    break
                node_ref = node_ref.get(key)
            else:
                value = node_ref
                if isinstance(value, (int, float)):
                    return float(value)
                if isinstance(value, str):
                    try:
                        return float(value.replace(",", "."))
                    except ValueError:
                        continue
        return None

    def pick_int(paths: Sequence[Tuple[str, ...]]) -> Optional[int]:
        for path in paths:
            node_ref: object = node
            for key in path:
                if not isinstance(node_ref, dict):
                    break
                node_ref = node_ref.get(key)
            else:
                return _coerce_int(node_ref)
        return None

    return pick_float(rating_candidates), pick_int(count_candidates)


def _resolve_availability(node: dict) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    availability = _coerce_str(
        _first(
            node.get("availability"),
            node.get("availabilityMessage"),
            node.get("inventoryMessage"),
            node.get("availabilityText"),
        )
    )
    stock_notice = _coerce_str(
        _first(
            node.get("stockNotice"),
            node.get("stockMessage"),
            node.get("availabilitySubText"),
        )
    )
    checkbox = _coerce_str(node.get("checkboxLabel")) or None
    return availability or None, stock_notice or None, checkbox


def _resolve_rebate(node: dict) -> Tuple[Optional[str], Optional[str]]:
    rebate = _coerce_str(
        _first(
            node.get("rebate"),
            node.get("rebateText"),
            node.get("promotionText"),
            node.get("promoText"),
        )
    )
    rebate_details = _coerce_str(
        _first(
            node.get("rebateDetails"),
            node.get("promotionSubText"),
        )
    )
    return rebate or None, rebate_details or None


def _score_node(node: dict) -> int:
    return sum(1 for key in _PRODUCT_SCORE_KEYS if key in node)


def _iter_product_nodes(payload: object) -> Iterator[dict]:
    stack: List[object] = [payload]
    seen: set[int] = set()
    while stack:
        node = stack.pop()
        if isinstance(node, dict):
            node_id = id(node)
            if node_id in seen:
                continue
            seen.add(node_id)
            if _score_node(node) >= 2 and node.get("name"):
                yield node
            stack.extend(node.values())
        elif isinstance(node, list):
            stack.extend(node)


def extract_products(payload: dict, base_url: str, store: str, city: str) -> List[Product]:
    products: List[Product] = []
    seen_keys: set[Tuple[str, str]] = set()
    for node in _iter_product_nodes(payload):
        title = _coerce_str(node.get("name") or node.get("title"))
        url = _resolve_url(base_url, node)
        if not title or not url:
            continue
        sku = _resolve_sku(node)
        dedupe_key = (sku or "", url)
        if dedupe_key in seen_keys:
            continue
        seen_keys.add(dedupe_key)
        brand = _resolve_brand(node)
        price, sale = _resolve_price(node)
        rating, rating_count = _resolve_rating(node)
        availability, stock_notice, checkbox = _resolve_availability(node)
        badges, badge_image = _extract_badges(node)
        colour_options = _extract_colour_options(node)
        rebate, rebate_details = _resolve_rebate(node)
        cta = _coerce_str(
            _first(
                node.get("cta"),
                node.get("ctaLabel"),
                node.get("ctaText"),
                node.get("primaryCta"),
                node.get("buttonText"),
            )
        )
        image = _resolve_image(node)
        products.append(
            Product(
                title=title,
                url=url,
                image=image,
                brand=brand,
                sku=sku,
                price=price,
                salePrice=sale,
                store=store,
                city=city,
                badges=badges,
                cta=cta,
                rating=rating,
                ratingCount=rating_count,
                availability=availability,
                stockNotice=stock_notice,
                badgeImage=badge_image,
                checkboxLabel=checkbox,
                colourOptions=colour_options,
                rebate=rebate,
                rebateDetails=rebate_details,
            )
        )
    return products


def _apply_store_preference(context, store_id: str, store_name: str, province: str) -> None:
    store_blob = {
        "id": store_id,
        "name": store_name,
        "province": province,
    }
    cookies = [
        {"name": "prefStore", "value": store_id},
        {"name": "preferredStore", "value": store_id},
        {"name": "prefStoreName", "value": store_name},
        {"name": "prefStoreProvince", "value": province},
    ]
    for cookie in cookies:
        context.add_cookies(
            [
                {
                    "name": cookie["name"],
                    "value": cookie["value"],
                    "domain": ".canadiantire.ca",
                    "path": "/",
                    "secure": True,
                }
            ]
        )
    context.add_init_script(
        "store => { try { localStorage.setItem('preferredStore', JSON.stringify(store)); "
        "sessionStorage.setItem('preferredStore', JSON.stringify(store)); } catch (error) { console.warn(error); } }",
        store_blob,
    )


def _accept_cookies(page) -> None:
    for selector in _CONSENT_SELECTORS:
        try:
            locator = page.locator(selector)
            locator.first.wait_for(state="visible", timeout=2000)
        except PlaywrightTimeoutError:
            continue
        except Exception:
            continue
        else:
            try:
                locator.first.click()
                page.wait_for_timeout(500)
                break
            except Exception:
                continue


def _auto_scroll(page, max_rounds: int = 12) -> None:
    last_height = 0
    for _ in range(max_rounds):
        page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        page.wait_for_timeout(800)
        for selector in _LOAD_MORE_SELECTORS:
            locator = page.locator(selector)
            try:
                locator.first.wait_for(state="visible", timeout=1000)
            except PlaywrightTimeoutError:
                continue
            except Exception:
                continue
            else:
                try:
                    locator.first.click()
                    page.wait_for_timeout(1200)
                    break
                except Exception:
                    continue
        new_height = page.evaluate("() => document.body.scrollHeight")
        if new_height == last_height:
            break
        last_height = new_height


def scrape_liquidations(
    url: str,
    output: Path,
    store_id: str,
    store_name: str,
    province: str,
    city: str,
    store_brand: str,
    headless: bool = True,
) -> List[Product]:
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=headless)
        context = browser.new_context(locale="fr-CA", user_agent=_USER_AGENT)
        _apply_store_preference(context, store_id, store_name, province)
        page = context.new_page()
        page.goto("https://www.canadiantire.ca", wait_until="load")
        _accept_cookies(page)
        page.goto(url, wait_until="networkidle")
        _accept_cookies(page)
        page.wait_for_selector("script#__NEXT_DATA__", timeout=30000)
        _auto_scroll(page)
        payload = page.evaluate("() => window.__NEXT_DATA__")
        if not isinstance(payload, dict):
            raise RuntimeError("Unexpected payload structure; received type %s" % type(payload))
        products = extract_products(payload, base_url="https://www.canadiantire.ca", store=store_brand, city=city)
        page.close()
        context.close()
        browser.close()
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8") as handle:
        json.dump([asdict(product) for product in products], handle, ensure_ascii=False, indent=2)
    return products


def parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Scrape Canadian Tire liquidation listings")
    parser.add_argument("--url", default=DEFAULT_URL, help="Canadian Tire liquidation page URL")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT), help="Destination JSON file")
    parser.add_argument("--store-id", default=DEFAULT_STORE_ID, help="Preferred store identifier")
    parser.add_argument("--store-name", default=DEFAULT_STORE_NAME, help="Preferred store name")
    parser.add_argument("--province", default=DEFAULT_PROVINCE, help="Province code for the store")
    parser.add_argument("--store-brand", default=DEFAULT_STORE_BRAND, help="Store brand label to store in JSON")
    parser.add_argument("--city", default=DEFAULT_CITY, help="City name to store in JSON")
    parser.add_argument("--no-headless", action="store_true", help="Run the browser in headed mode")
    return parser.parse_args(list(argv))


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv if argv is not None else sys.argv[1:])
    try:
        products = scrape_liquidations(
            url=args.url,
            output=Path(args.output),
            store_id=args.store_id,
            store_name=args.store_name,
            province=args.province,
            city=args.city,
            store_brand=args.store_brand,
            headless=not args.no_headless,
        )
    except PlaywrightTimeoutError as exc:
        print(f"Échec du chargement de la page: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:  # pragma: no cover - runtime safeguard
        print(f"Erreur inattendue: {exc}", file=sys.stderr)
        return 1
    print(f"{len(products)} produits enregistrés dans {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
