import asyncio
import csv
import json
import os
import re
import sys
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse
from typing import Dict, List, Tuple

from playwright.async_api import TimeoutError as PWTimeout
from playwright.async_api import async_playwright

# --- Réglages magasin Saint-Jérôme
POSTAL_CODE = "J7Z 5T3"  # on peut remplacer via VAR d'env si tu veux
CITY_QUERY = "Saint-Jérôme, QC"
CITY_LABEL = "Saint-Jérôme"

# Sélecteurs "robustes" Walmart (peuvent bouger – on a des fallback)
CARD = "article[data-automation='product-item']," \
       "div[data-automation='product-card']," \
       "div[data-automation='product-tile']"

NAME = "[data-automation='product-title'], [data-automation='product-name'], a[aria-label]"
PRICE_CURR = "[data-automation='current-price'], span[data-automation='pricing-price'], span:has-text('$')"
PRICE_WAS = "[data-automation='was-price'], [data-automation='strike-price'], s"
IMG = "img"
LINK = "a[href*='/ip/'], a[href*='/product/']"


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


async def ensure_store(page):
    """Sélectionne le magasin via code postal; robuste aux variantes UI."""
    try:
        await page.goto("https://www.walmart.ca/", timeout=90000)
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
                break

        # Champ de recherche d’emplacement
        search_sel = "input[type='search'], input[aria-label*='code postal'], input[placeholder*='code postal']"
        await page.locator(search_sel).first.fill(POSTAL_CODE)
        await page.keyboard.press("Enter")
        # Choisit le premier magasin proposé
        await page.locator("button:has-text('Sélectionner')").first.click()
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


def _extract_items_from_json(payload: Dict) -> List[Dict]:
    stacks = []
    search_paths = [
        ("props", "pageProps", "initialData", "searchResult", "itemStacks"),
        ("props", "pageProps", "initialState", "search", "searchResult", "itemStacks"),
        ("props", "pageProps", "initialData", "productSearch", "searchResult", "itemStacks"),
    ]

    def _dig(data: Dict, path: Tuple[str, ...]):
        cur = data
        for key in path:
            if not isinstance(cur, dict) or key not in cur:
                return None
            cur = cur[key]
        return cur

    for path in search_paths:
        res = _dig(payload, path)
        if isinstance(res, list) and res:
            stacks = res
            break

    items: List[Dict] = []
    for stack in stacks:
        stack_items = stack.get("items") if isinstance(stack, dict) else None
        if not isinstance(stack_items, list):
            continue
        for raw in stack_items:
            if not isinstance(raw, dict):
                continue

            title = raw.get("name") or raw.get("productName") or ""
            title = " ".join(str(title).split())
            if not title:
                continue

            # URL
            url = raw.get("canonicalUrl") or raw.get("productPageUrl") or ""
            if url.startswith("/"):
                url = "https://www.walmart.ca" + url

            # Image (plusieurs clés possibles)
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
                            image = first.get("url") or first.get("assetSizeUrls", {}).get("large") or ""
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

    return items


async def extract_from_category(page, url: str, category: str) -> List[Dict]:
    items: List[Dict] = []

    # Aller à la page catégorie
    await page.goto(url, timeout=90000)
    await page.wait_for_timeout(2000)

    seen_urls = set()

    while True:
        if page.url in seen_urls:
            break
        seen_urls.add(page.url)

        # 1) Essaye d’abord d’utiliser les données JSON embarquées
        try:
            data = await page.evaluate("() => window.__NEXT_DATA__")
        except Exception:
            data = None

        if isinstance(data, dict):
            parsed = _extract_items_from_json(data)
            for item in parsed:
                item["category"] = category
            items.extend([i for i in parsed if i.get("url")])

        # 2) Fallback DOM si jamais le JSON n’a rien donné
        if not items:
            for c in await page.locator(CARD).all():
                try:
                    name = (await c.locator(NAME).first.text_content()) or ""
                except Exception:
                    name = (await c.text_content()) or ""
                name = " ".join(name.split())

                href = ""
                if await c.locator(LINK).first.count():
                    href = await c.locator(LINK).first.get_attribute("href") or ""
                    if href.startswith("/"):
                        href = "https://www.walmart.ca" + href

                img = ""
                if await c.locator(IMG).first.count():
                    img = (await c.locator(IMG).first.get_attribute("src")) or ""

                price_curr_loc = c.locator(PRICE_CURR).first
                price_was_loc = c.locator(PRICE_WAS).first
                price_curr_txt = await price_curr_loc.text_content() if await price_curr_loc.count() else ""
                price_was_txt = await price_was_loc.text_content() if await price_was_loc.count() else ""
                price = money_from_text(price_curr_txt)
                was = money_from_text(price_was_txt)

                discount = None
                if price and was and was > 0:
                    discount = round(100.0 * (was - price) / was, 1)

                if name and href:
                    items.append({
                        "title": name,
                        "category": category,
                        "price": was,
                        "sale_price": price,
                        "discount_pct": discount,
                        "url": href,
                        "image": img,
                        "store": "Walmart",
                        "city": CITY_LABEL,
                    })

        next_btns = page.locator("a:has-text('Suivant'), button:has-text('Suivant'), a[aria-label='Suivant']")
        if await next_btns.count():
            if await next_btns.last.is_enabled():
                await next_btns.last.click()
                await page.wait_for_timeout(1500)
                continue

        m = re.search(r"([?&])page=(\d+)", page.url)
        base = page.url
        if m:
            curr = int(m.group(2))
            nxt = curr + 1
            base = re.sub(r"([?&])page=\d+", rf"\1page={nxt}", base)
        else:
            sep = "&" if "?" in base else "?"
            base = f"{base}{sep}page=2"

        prev_len = len(items)
        try:
            await page.goto(base, timeout=60000)
            await page.wait_for_timeout(1500)
        except PWTimeout:
            break

        if len(items) == prev_len:
            # aucune donnée supplémentaire → fin
            break

    # dédoublonne sur l’URL
    deduped: Dict[str, Dict] = {}
    for item in items:
        url = item.get("url")
        if url and url not in deduped:
            deduped[url] = item

    return list(deduped.values())


async def run(electronics_url: str, toys_url: str, appliances_url: str, out_dir: Path):
    out_dir.mkdir(parents=True, exist_ok=True)

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        ctx = await browser.new_context(locale="fr-CA")
        page = await ctx.new_page()

        await ensure_store(page)

        datasets: List[Tuple[str, str]] = [
            ("electronique", electronics_url),
            ("jouets", toys_url),
            ("electromenagers", appliances_url),
        ]

        for cat, url in datasets:
            normalized_url = ensure_clearance_query(url)
            print(f"➡️  Catégorie {cat} → {normalized_url}")
            data = await extract_from_category(page, normalized_url, cat)
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
