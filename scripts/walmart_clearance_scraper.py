import asyncio
import json
from pathlib import Path
from typing import Dict, Any, Set

from playwright.async_api import async_playwright

# Page liquidation (tu peux garder la même, le store est pris du contexte de ton cookie/session)
START_URL = "https://www.walmart.ca/fr/clearance"
OUTPUT = "data/walmart/st-jerome.json"

MAX_PAGES = 100  # garde une sécurité
SLOW_MO = 150


def normalize(raw: Dict[str, Any]) -> Dict[str, Any]:
    name = raw.get("name") or raw.get("title") or "Produit"
    sku = str(raw.get("usItemId") or raw.get("sku") or raw.get("id") or "")
    # prix
    price = None
    pi = raw.get("priceInfo") or {}
    if isinstance(pi, dict):
        price = (pi.get("currentPrice") or {}).get("price") or pi.get("price")
    price = price or raw.get("price") or raw.get("salePrice")
    # image
    image = None
    imgs = raw.get("images") or raw.get("imageInfo") or {}
    if isinstance(imgs, dict):
        image = imgs.get("thumbnailUrl") or imgs.get("primaryImageUrl")
    elif isinstance(imgs, list) and imgs:
        image = imgs[0]
    # lien
    link = raw.get("canonicalUrl") or raw.get("productPageUrl") or raw.get("productUrl")
    if link and link.startswith("/"):
        link = "https://www.walmart.ca" + link
    availability = raw.get("availabilityStatus") or raw.get("availability") or "Inconnu"
    return {
        "product_name": name,
        "sku": sku,
        "sale_price": price,
        "regular_price": raw.get("msrp") or raw.get("listPrice"),
        "image": image,
        "product_link": link,
        "availability": availability,
        "store": "Walmart St-Jérôme",
    }


async def run():
    Path(OUTPUT).parent.mkdir(parents=True, exist_ok=True)
    items: Dict[str, Dict[str, Any]] = {}
    seen: Set[str] = set()

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, slow_mo=SLOW_MO)
        context = await browser.new_context(locale="fr-CA", viewport={"width": 1400, "height": 900})
        page = await context.new_page()

        # Collecte des produits à partir des réponses JSON
        async def on_response(resp):
            url = resp.url
            if any(s in url for s in ["graphql", "/api/", "/bsp/"]):
                try:
                    data = await resp.json()
                except Exception:
                    return

                def harvest(node):
                    if isinstance(node, dict):
                        for v in node.values():
                            harvest(v)
                    elif isinstance(node, list):
                        if node and isinstance(node[0], dict) and ("name" in node[0] or "usItemId" in node[0]):
                            for raw in node:
                                sku = str(raw.get("usItemId") or raw.get("sku") or raw.get("id") or "")
                                if not sku or sku in seen:
                                    continue
                                seen.add(sku)
                                items[sku] = normalize(raw)
                        else:
                            for v in node:
                                harvest(v)

                harvest(data)

        page.on("response", on_response)

        # Aller à la page de liquidation
        await page.goto(START_URL, timeout=120_000)
        await page.wait_for_load_state("networkidle", timeout=120_000)

        # Pagination: clique “Suivant” jusqu'à la fin
        page_no = 1
        while page_no <= MAX_PAGES:
            # petit scroll pour déclencher lazy-load
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            await page.wait_for_timeout(800)

            # tente clic sur “Suivant”
            next_btn = await page.locator(
                "button[aria-label*='Suivant'], a[aria-label*='Suivant'], "
                "button[aria-label*='Next'], a[aria-label*='Next'], "
                "button:has-text('›'), a:has-text('›')"
            ).first

            try:
                if not await next_btn.is_visible(timeout=2000):
                    break
                # si disabled → fin
                if await next_btn.is_disabled():
                    break
                await next_btn.click()
                page_no += 1
                await page.wait_for_load_state("networkidle", timeout=120_000)
            except Exception:
                break

        await browser.close()

    data = list(items.values())
    with open(OUTPUT, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    print(f"✅ Walmart clearance total: {len(data)} items → {OUTPUT}")


if __name__ == "__main__":
    asyncio.run(run())
