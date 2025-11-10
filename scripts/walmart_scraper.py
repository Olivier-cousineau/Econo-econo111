import asyncio
import csv
import json
import os
import random
import re
import sys
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse
from typing import Dict, List, Set, Tuple

from playwright.async_api import TimeoutError as PWTimeout
from playwright.async_api import async_playwright
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

# --- Réglages magasin Saint-Jérôme
POSTAL_CODE = "J7Z 5T3"  # on peut remplacer via VAR d'env si tu veux
CITY_QUERY = "Saint-Jérôme, QC"
CITY_LABEL = "Saint-Jérôme"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

# Sélecteurs "robustes" Walmart (peuvent bouger – on a des fallback)
CARD = ", ".join(
    [
        "div[data-automation='product']",
        "li[data-automation='product']",
        "div[class*='product-tile']",
        "div[data-automation='product-card']",
        "li[data-testid*='product']",
        "div[data-testid*='product']",
    ]
)

NAME = "a, h2, h3, [data-automation*='title']"
PRICE_CURR = "[data-automation*='current-price'], .price-current, [class*='sale']"
PRICE_WAS = "[data-automation*='was-price'], .price-was, s, del, [class*='was']"
IMG = "img"
LINK = "a[href]"


def parse_price(txt: str | None) -> float | None:
    if not txt:
        return None
    cleaned = txt.replace("\xa0", " ").replace(",", ".")
    match = re.search(r"(\d+(?:\.\d{1,2})?)", cleaned)
    if match:
        try:
            return float(match.group(1))
        except ValueError:
            return None
    return None


def ensure_clearance_query(raw_url: str) -> str:
    if not raw_url:
        return raw_url

    parsed = urlparse(raw_url)
    query_pairs = parse_qsl(parsed.query, keep_blank_values=True)
    params: Dict[str, List[str]] = {}
    for key, value in query_pairs:
        params.setdefault(key, []).append(value)

    def _set_param(key: str, value: str):
        params[key] = [value]

    # Normalise les variations Liquidation → Clearance
    if "facet" in params:
        normalized = [v.replace("Liquidation", "Clearance") for v in params["facet"]]
        params["facet"] = normalized

    if "special_offers" in params:
        params["special_offers"] = [v.replace("Liquidation", "Clearance") for v in params["special_offers"]]

    # Force les paramètres attendus
    _set_param("special_offers", "Clearance")
    _set_param("postalCode", POSTAL_CODE.replace(" ", ""))

    new_query = urlencode([(k, val) for k, values in params.items() for val in values])
    return urlunparse(parsed._replace(query=new_query))


def money_from_text(txt: str) -> float | None:
    if not txt:
        return None
    m = re.search(r"\$ ?([0-9]+(?:[.,][0-9]{2})?)", txt.replace("\xa0", " "))
    if m:
        return float(m.group(1).replace(",", "."))
    return None


async def human_pause(min_ms: int = 300, max_ms: int = 900) -> None:
    await asyncio.sleep(random.uniform(min_ms / 1000, max_ms / 1000))


async def accept_cookies(page) -> None:
    try:
        await page.locator("button:has-text('Accepter tout')").first.click(timeout=4000)
        await human_pause()
    except Exception:
        pass


async def ensure_store(page):
    """Sélectionne le magasin via code postal; robuste aux variantes UI."""
    try:
        await page.goto("https://www.walmart.ca/", timeout=90000)
        await accept_cookies(page)
        await page.wait_for_load_state("networkidle")
        await human_pause()
        # Ouvre le sélecteur de localisation (plusieurs variantes)
        candidates = [
            "[data-automation='header-location-button']",
            "button:has-text('Votre magasin')",
            "button:has-text('Choisir un magasin')",
            "button[aria-label*='magasin']",
        ]
        for sel in candidates:
            locator = page.locator(sel).first
            if await locator.count() and await locator.is_visible():
                await locator.click()
                await human_pause()
                break

        # Champ de recherche d’emplacement
        search_sel = "input[type='search'], input[aria-label*='code postal'], input[placeholder*='code postal']"
        await page.locator(search_sel).first.fill(POSTAL_CODE)
        await page.keyboard.press("Enter")
        # Choisit le premier magasin proposé
        await page.locator("button:has-text('Sélectionner')").first.click()
        await human_pause()
        # Petite pause pour laisser appliquer le magasin
        await page.wait_for_timeout(2000)
    except PWTimeout:
        # Pas bloquant : si la sélection échoue, on continue (les pages clearance fonctionnent souvent sans magasin)
        pass


def _price_from_item(item: Dict, *paths: Tuple[str, ...]) -> float | None:
    """Utility pour extraire les prix numériques d’un dict Walmart."""

    def _dig(data: Dict, keys: Tuple[str, ...]) -> object:
        cur = data
        for key in keys:
            if not isinstance(cur, dict) or key not in cur:
                return None
            cur = cur[key]
        return cur

    for path in paths:
        value = _dig(item, path)
        if value is None:
            continue
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, str):
            money = money_from_text(value)
            if money is not None:
                return money
        if isinstance(value, dict):
            for key in ("price", "amount", "value"):
                if key in value and value[key] is not None:
                    nested = value[key]
                    if isinstance(nested, (int, float)):
                        return float(nested)
                    if isinstance(nested, str):
                        money = money_from_text(nested)
                        if money is not None:
                            return money
    return None


def _iter_dicts(payload):
    stack = [payload]
    while stack:
        current = stack.pop()
        if isinstance(current, dict):
            yield current
            stack.extend(current.values())
        elif isinstance(current, list):
            stack.extend(current)


def _extract_items_from_json(payload: Dict) -> List[Dict]:
    items: List[Dict] = []
    seen_urls: Set[str] = set()

    for raw in _iter_dicts(payload):
        if not isinstance(raw, dict):
            continue

        title = raw.get("name") or raw.get("productName") or ""
        url = raw.get("canonicalUrl") or raw.get("productPageUrl") or ""
        if not title or not url:
            continue

        # La plupart des objets non produits n'ont pas d'offres/prix
        if not any(
            key in raw
            for key in (
                "priceInfo",
                "primaryOffer",
                "availabilityStatus",
                "imageInfo",
            )
        ):
            continue

        title = " ".join(str(title).split())
        if url.startswith("/"):
            url = "https://www.walmart.ca" + url

        if url in seen_urls:
            continue

        image = ""
        image_info = raw.get("imageInfo") or {}
        if isinstance(image_info, dict):
            for key in ("thumbnailUrl", "allImages", "images"):
                value = image_info.get(key)
                if isinstance(value, str) and value:
                    image = value
                    break
                if isinstance(value, list) and value:
                    first = value[0]
                    if isinstance(first, dict):
                        image = (
                            first.get("url")
                            or first.get("assetSizeUrls", {}).get("large")
                            or ""
                        )
                    elif isinstance(first, str):
                        image = first
                    if image:
                        break
            if not image:
                image = image_info.get("primaryImageUrl", "")

        current_price = _price_from_item(
            raw,
            ("priceInfo", "currentPrice"),
            ("priceInfo", "currentPrice", "price"),
            ("priceInfo", "currentPrice", "amount"),
            ("priceInfo", "currentPrice", "value"),
            ("primaryOffer", "offerPrice"),
            ("primaryOffer", "offerPrice", "price"),
            ("primaryOffer", "offerPrice", "value"),
            ("primaryOffer", "prices", "current"),
            ("primaryOffer", "prices", "current", "price"),
        )

        was_price = _price_from_item(
            raw,
            ("priceInfo", "wasPrice"),
            ("priceInfo", "wasPrice", "price"),
            ("priceInfo", "previousPrice"),
            ("primaryOffer", "prices", "was"),
            ("primaryOffer", "prices", "was", "price"),
        )

        discount = None
        if current_price and was_price and was_price > 0:
            discount = round(100.0 * (was_price - current_price) / was_price, 1)

        items.append(
            {
                "title": title,
                "category": raw.get("category") or raw.get("department") or "",
                "price": was_price,
                "sale_price": current_price,
                "discount_pct": discount,
                "url": url,
                "image": image,
                "store": "Walmart",
                "city": CITY_LABEL,
            }
        )
        seen_urls.add(url)

    return items


def _build_page_url(base_url: str, page_num: int) -> str:
    if page_num <= 1:
        return base_url

    parts = urlsplit(base_url)
    query_pairs = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True) if k.lower() != "page"]
    query_pairs.append(("page", str(page_num)))
    query = urlencode(query_pairs, doseq=True)
    return urlunsplit(parts._replace(query=query))


async def _extract_from_dom(cards, category: str) -> List[Dict]:
    items: List[Dict] = []
    for card in cards:
        try:
            locator = card.locator(NAME).first
            title = (await locator.text_content()) if await locator.count() else ""
        except Exception:
            try:
                title = await card.text_content()
            except Exception:
                title = ""

        title = " ".join(title.split()) if title else ""

        try:
            link_loc = card.locator(LINK).first
            href = await link_loc.get_attribute("href") if await link_loc.count() else None
        except Exception:
            href = None

        if href and href.startswith("/"):
            href = f"https://www.walmart.ca{href}"

        try:
            img_loc = card.locator(IMG).first
            image = await img_loc.get_attribute("src") if await img_loc.count() else None
        except Exception:
            image = None

        try:
            sale_loc = card.locator(PRICE_CURR).first
            sale_txt = await sale_loc.text_content() if await sale_loc.count() else None
        except Exception:
            sale_txt = None

        try:
            regular_loc = card.locator(PRICE_WAS).first
            regular_txt = await regular_loc.text_content() if await regular_loc.count() else None
        except Exception:
            regular_txt = None

        price_sale = parse_price(sale_txt)
        price_regular = parse_price(regular_txt)

        discount = None
        if price_sale and price_regular and price_regular > 0:
            discount = round((1 - price_sale / price_regular) * 100)

        if title and (price_sale or price_regular) and href:
            items.append(
                {
                    "title": title,
                    "category": category,
                    "price": price_regular,
                    "sale_price": price_sale,
                    "discount_pct": discount,
                    "url": href,
                    "image": image or "",
                    "store": "Walmart",
                    "city": CITY_LABEL,
                }
            )

    return items


async def extract_from_category(page, url: str, category: str) -> List[Dict]:
    seen_urls: Dict[str, Dict] = {}
    page_num = 1

    while True:
        current_url = _build_page_url(url, page_num)
        try:
            await page.goto(current_url, timeout=90000)
        except PWTimeout:
            break

        await accept_cookies(page)
        await page.wait_for_load_state("networkidle")
        await human_pause()

        try:
            await page.wait_for_selector(CARD, timeout=15000)
        except PWTimeout:
            cards = []
        else:
            for _ in range(15):
                await page.mouse.wheel(0, 2000)
                await human_pause()
            cards = await page.query_selector_all(CARD)

        try:
            data = await page.evaluate("() => window.__NEXT_DATA__")
        except Exception:
            data = None

        parsed: List[Dict] = []
        if isinstance(data, dict):
            parsed = _extract_items_from_json(data)

        if not parsed:
            try:
                redux_state = await page.evaluate(
                    "() => window.__WML_REDUX_INITIAL_STATE__"
                )
            except Exception:
                redux_state = None
            if isinstance(redux_state, dict):
                parsed = _extract_items_from_json(redux_state)

        if not parsed and cards:
            parsed = await _extract_from_dom(cards, category)
        else:
            for item in parsed:
                item["category"] = category

        new_items = 0
        for item in parsed:
            href = item.get("url")
            if not href or href in seen_urls:
                continue
            seen_urls[href] = item
            new_items += 1

        if not parsed or new_items == 0:
            break

        await human_pause()
        page_num += 1

    return list(seen_urls.values())


async def run(electronics_url: str, toys_url: str, appliances_url: str, out_dir: Path):
    out_dir.mkdir(parents=True, exist_ok=True)

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-dev-shm-usage",
            ],
        )
        ctx = await browser.new_context(locale="fr-CA", user_agent=USER_AGENT)
        page = await ctx.new_page()

        await ensure_store(page)
        await human_pause()

        datasets: List[Tuple[str, str]] = [
            ("electronique", ensure_clearance_query(electronics_url)),
            ("jouets", ensure_clearance_query(toys_url)),
            ("electromenagers", ensure_clearance_query(appliances_url)),
        ]

        for cat, url in datasets:
            print(f"➡️  Catégorie {cat} → {url}")
            await human_pause()
            data = await extract_from_category(page, url, cat)
            json_path = out_dir / f"{cat}.json"
            csv_path = out_dir / f"{cat}.csv"

            # JSON (écrase pour garder « l’état courant »)
            with open(json_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)

            # CSV (écrase aussi)
            if data:
                with open(csv_path, "w", newline="", encoding="utf-8") as f:
                    w = csv.DictWriter(
                        f,
                        fieldnames=[
                            "title",
                            "category",
                            "price",
                            "sale_price",
                            "discount_pct",
                            "url",
                            "image",
                            "store",
                            "city",
                        ],
                    )
                    w.writeheader()
                    w.writerows(data)

            print(f"✅  {cat}: {len(data)} produits – {json_path}")

        await browser.close()


if __name__ == "__main__":
    electronics = os.getenv("WAL_ELECTRONICS_URL", "").strip()
    toys = os.getenv("WAL_TOYS_URL", "").strip()
    appliances = os.getenv("WAL_APPLIANCES_URL", "").strip()

    if not electronics or not toys or not appliances:
        print("ERROR: Missing one of WAL_* URLs")
        sys.exit(1)

    out = Path("data/walmart/saint-jerome")
    asyncio.run(run(electronics, toys, appliances, out))
