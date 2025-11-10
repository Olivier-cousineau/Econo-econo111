import asyncio
import csv
import json
import os
import re
import sys
from pathlib import Path
from typing import Dict, List, Tuple

from playwright.async_api import TimeoutError as PWTimeout
from playwright.async_api import async_playwright

# --- Réglages magasin Saint-Jérôme
POSTAL_CODE = "J7Y 4Y9"  # on peut remplacer via VAR d'env si tu veux
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


async def extract_from_category(page, url: str, category: str) -> List[Dict]:
    items = []

    async def parse_cards():
        for c in await page.locator(CARD).all():
            try:
                name = (await c.locator(NAME).first.text_content()) or ""
            except Exception:
                name = (await c.text_content()) or ""
            name = " ".join(name.split())

            # lien
            href = ""
            if await c.locator(LINK).first.count():
                href = await c.locator(LINK).first.get_attribute("href") or ""
                if href.startswith("/"):
                    href = "https://www.walmart.ca" + href

            # image
            img = ""
            if await c.locator(IMG).first.count():
                img = (await c.locator(IMG).first.get_attribute("src")) or ""

            # prix
            price_curr_loc = c.locator(PRICE_CURR).first
            price_was_loc = c.locator(PRICE_WAS).first
            price_curr_txt = await price_curr_loc.text_content() if await price_curr_loc.count() else ""
            price_was_txt = await price_was_loc.text_content() if await price_was_loc.count() else ""
            price = money_from_text(price_curr_txt)
            was = money_from_text(price_was_txt)

            # rabais %
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

    # Aller à la page catégorie
    await page.goto(url, timeout=90000)
    await page.wait_for_timeout(2000)

    # Pagination : Walmart a soit bouton "Suivant", soit param ?page=
    seen_urls = set()

    while True:
        # anti-loop
        if page.url in seen_urls:
            break
        seen_urls.add(page.url)

        # attendre le grid
        await page.wait_for_timeout(1500)
        await parse_cards()

        # tente de trouver un bouton "Suivant"
        next_btns = page.locator("a:has-text('Suivant'), button:has-text('Suivant'), a[aria-label='Suivant']")
        if await next_btns.count():
            if await next_btns.last.is_enabled():
                await next_btns.last.click()
                continue

        # sinon, essaie param page=
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
            await parse_cards()
            if len(items) == prev_len:
                break  # pas de nouveaux items → fin
        except PWTimeout:
            break

    return items


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
            print(f"➡️  Catégorie {cat} → {url}")
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
