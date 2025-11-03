#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Scrape BestBuy (collection "Magasinez toutes les offres") et sauve en JSON/CSV.
URL fournie (FR-CA) : https://www.bestbuy.ca/fr-ca/collection/magasinez-toutes-les-offres/16074

Points clés:
- Utilise Playwright (Chromium headless).
- Charge la page, clique "Afficher plus" / "Load more" jusqu'à la fin (si présent).
- Tente d'extraire d'abord depuis __NEXT_DATA__ (Next.js) pour robustesse.
- Fallback DOM si structure JSON indispo.
- Sauvegarde dans data/bestbuy/anjou/ avec datestamp + dernier snapshot "latest".
"""

from __future__ import annotations

import asyncio
import csv
import json
import re
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, List, Optional

from playwright.async_api import TimeoutError as PwTimeout
from playwright.async_api import async_playwright

COLLECTION_URL = "https://www.bestbuy.ca/fr-ca/collection/magasinez-toutes-les-offres/16074"

OUT_DIR = Path("data/bestbuy/anjou").resolve()
OUT_DIR.mkdir(parents=True, exist_ok=True)


@dataclass
class Product:
    sku: Optional[str]
    name: Optional[str]
    price: Optional[float]
    sale_price: Optional[float]
    image_url: Optional[str]
    product_link: Optional[str]
    availability: Optional[str]


def _to_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)

    txt = str(value)
    txt = txt.replace("\u202f", "")
    txt = txt.replace(" ", "")
    txt = txt.replace("$", "").replace("CAD", "")
    txt = txt.replace(",", ".")
    match = re.search(r"(\d+(?:\.\d+)?)", txt)
    return float(match.group(1)) if match else None


def _uniq(products: Iterable[Product]) -> List[Product]:
    seen = set()
    unique_products: List[Product] = []
    for product in products:
        key = (
            product.sku or "",
            product.product_link or "",
            product.name or "",
        )
        if key in seen:
            continue
        seen.add(key)
        unique_products.append(product)
    return unique_products


async def extract_via_next_data(page) -> List[Product]:
    """Essaye d'extraire depuis __NEXT_DATA__ (structure Next.js)."""
    try:
        next_data = await page.evaluate(
            """() => {
            const el = document.getElementById('__NEXT_DATA__');
            return el ? JSON.parse(el.textContent) : null;
        }"""
        )
    except Exception:
        next_data = None

    products: List[Product] = []

    def walk(obj: Any) -> None:
        if isinstance(obj, dict):
            keys = obj.keys()
            looks_like_product = any(k in keys for k in ("sku", "skuId", "name")) and any(
                k in keys for k in ("salePrice", "regularPrice", "price")
            )
            if looks_like_product:
                sku = str(obj.get("sku") or obj.get("skuId") or "") or None
                name = obj.get("name") or obj.get("title") or None
                sale_price = _to_float(
                    obj.get("salePrice") or obj.get("currentPrice") or obj.get("price")
                )
                price = _to_float(
                    obj.get("regularPrice") or obj.get("listPrice") or obj.get("priceBefore")
                )
                image_url = obj.get("thumbnailImage") or obj.get("image") or None
                link = obj.get("productUrl") or obj.get("url") or None
                availability = obj.get("availability") or obj.get("stockStatus") or None

                if isinstance(link, str) and link.startswith("/"):
                    link = "https://www.bestbuy.ca" + link

                products.append(
                    Product(
                        sku=sku,
                        name=name,
                        price=price,
                        sale_price=sale_price,
                        image_url=image_url,
                        product_link=link,
                        availability=availability,
                    )
                )

            for value in obj.values():
                walk(value)
        elif isinstance(obj, list):
            for value in obj:
                walk(value)

    if next_data:
        walk(next_data)

    return _uniq(products)


async def load_all_items(page) -> None:
    """Clique 'Afficher plus' / 'Load more' jusqu'à disparition ou désactivation."""
    selectors = [
        '[data-automation="loadMoreButton"]',
        'button:has-text("Afficher plus")',
        'button:has-text("Voir plus")',
        'button:has-text("Load more")',
        'button:has-text("Show more")',
    ]
    while True:
        clicked = False
        for selector in selectors:
            try:
                button = page.locator(selector)
                if await button.is_visible():
                    disabled = await button.get_attribute("disabled")
                    aria_disabled = await button.get_attribute("aria-disabled")
                    if disabled is not None or aria_disabled == "true":
                        return
                    await button.scroll_into_view_if_needed()
                    await button.click()
                    await page.wait_for_timeout(1000)
                    clicked = True
                    break
            except Exception:
                continue
        if not clicked:
            return


async def _safe_text(locator) -> Optional[str]:
    try:
        value = await locator.text_content()
        return value.strip() if value else None
    except Exception:
        return None


async def _safe_attr(locator, name: str) -> Optional[str]:
    try:
        return await locator.get_attribute(name)
    except Exception:
        return None


async def extract_via_dom(page) -> List[Product]:
    """Fallback DOM quand __NEXT_DATA__ ne suffit pas."""
    cards = page.locator('[data-automation="productCard"]')
    count = await cards.count()
    products: List[Product] = []
    for index in range(count):
        card = cards.nth(index)
        name = await _safe_text(card.locator('[data-automation="productTitle"]'))
        price_txt = await _safe_text(
            card.locator('[data-automation="strikePrice"], [data-automation="regularPrice"]').first
        )
        sale_txt = await _safe_text(
            card.locator('[data-automation="salePrice"], [data-automation="currentPrice"]').first
        )
        link = await _safe_attr(card.locator('a[href]').first, "href")
        image_url = await _safe_attr(card.locator("img").first, "src")
        availability = await _safe_text(card.locator('[data-automation="availability"]').first)

        if isinstance(link, str) and link.startswith("/"):
            link = "https://www.bestbuy.ca" + link

        products.append(
            Product(
                sku=None,
                name=name,
                price=_to_float(price_txt),
                sale_price=_to_float(sale_txt),
                image_url=image_url,
                product_link=link,
                availability=availability,
            )
        )
    return _uniq(products)


async def run() -> None:
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=True)
        context = await browser.new_context(locale="fr-CA")
        page = await context.new_page()

        await page.goto(COLLECTION_URL, timeout=120_000)
        await page.wait_for_load_state("networkidle")

        await load_all_items(page)

        products = await extract_via_next_data(page)

        if not products:
            products = await extract_via_dom(page)

        timestamp = datetime.now(timezone.utc).astimezone()
        day = timestamp.strftime("%Y-%m-%d")

        json_path = OUT_DIR / f"bestbuy_anjou_{day}.json"
        latest_path = OUT_DIR / "latest.json"
        csv_path = OUT_DIR / f"bestbuy_anjou_{day}.csv"

        data = [asdict(product) for product in products]
        with open(json_path, "w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False, indent=2)
        with open(latest_path, "w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False, indent=2)

        fieldnames = [
            "name",
            "price",
            "sale_price",
            "image_url",
            "product_link",
            "availability",
            "sku",
        ]
        with open(csv_path, "w", encoding="utf-8", newline="") as fh:
            writer = csv.DictWriter(fh, fieldnames=fieldnames)
            writer.writeheader()
            for product in products:
                writer.writerow(
                    {
                        "name": product.name or "",
                        "price": product.price if product.price is not None else "",
                        "sale_price": product.sale_price if product.sale_price is not None else "",
                        "image_url": product.image_url or "",
                        "product_link": product.product_link or "",
                        "availability": product.availability or "",
                        "sku": product.sku or "",
                    }
                )

        print(f"[OK] Produits extraits: {len(products)}")
        print(f"[OK] JSON:   {json_path}")
        print(f"[OK] LATEST: {latest_path}")
        print(f"[OK] CSV:    {csv_path}")

        await context.close()
        await browser.close()


def main() -> None:
    try:
        asyncio.run(run())
    except PwTimeout:
        print("[ERREUR] Timeout Playwright — réessaie plus tard.", file=sys.stderr)
        sys.exit(2)
    except Exception as exc:  # pylint: disable=broad-except
        print(f"[ERREUR] {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
