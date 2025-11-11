import asyncio
import json
import re
import subprocess
import sys
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

try:
    from playwright.async_api import Error as PlaywrightError
    from playwright.async_api import async_playwright
except ModuleNotFoundError as exc:  # pragma: no cover - import-time guard
    raise SystemExit(
        "Playwright is required to run this scraper. Install it with 'pip install playwright'."
    ) from exc

OUT_DIR = Path("data/walmart/saint-jerome")
OUT_DIR.mkdir(parents=True, exist_ok=True)

CATEGORIES = {
    "electronique": "https://www.walmart.ca/fr/browse/electronics/10003?special_offers=Clearance&postalCode=J7Z5T3",
    "jouets":       "https://www.walmart.ca/fr/browse/jouets/10011?special_offers=Clearance&postalCode=J7Z5T3",
    "electromenagers": "https://www.walmart.ca/fr/browse/appliances/10018?special_offers=Clearance&postalCode=J7Z5T3",
}

PRODUCT_SEL = "div[data-automation='product'], li[data-automation='product'], div[class*='product-tile']"

def normalize_price(text: str | None):
    if not text:
        return None
    t = text.replace("\xa0", " ").replace(",", ".")
    m = re.search(r"(\d+(?:\.\d{1,2})?)", t)
    return float(m.group(1)) if m else None

async def accept_cookies(page):
    # FR/EN variantes
    for label in ["Accepter tout", "Tout accepter", "Accept all", "Accept All"]:
        try:
            await page.get_by_role("button", name=label).first.click(timeout=2500)
            break
        except Exception:
            pass


def install_chromium_if_needed():
    """Install Chromium for Playwright when it has not been provisioned yet."""
    print("Installing Playwright Chromium browser ...", flush=True)
    try:
        subprocess.run(
            [sys.executable, "-m", "playwright", "install", "chromium"],
            check=True,
        )
    except subprocess.CalledProcessError as exc:
        raise RuntimeError("Unable to install Playwright Chromium browser") from exc

def with_page(url: str, page_num: int) -> str:
    """Ajoute/maj le param ?page=N si présent (pagination côté Walmart)."""
    parts = list(urlparse(url))
    qs = parse_qs(parts[4])
    qs["page"] = [str(page_num)]
    parts[4] = urlencode(qs, doseq=True)
    return urlunparse(parts)

async def scrape_category(context, name: str, base_url: str):
    page = await context.new_page()
    items = []
    page_num = 1
    empty_pages = 0

    while True:
        url = with_page(base_url, page_num)
        await page.goto(url, timeout=90000)
        await accept_cookies(page)
        await page.wait_for_load_state("networkidle")

        # scroll pour déclencher le rendu lazy
        for _ in range(14):
            await page.mouse.wheel(0, 1800)
            await page.wait_for_timeout(450)

        await page.wait_for_timeout(800)

        cards = await page.query_selector_all(PRODUCT_SEL)
        batch = []
        for c in cards:
            # titre
            try:
                title = await c.locator("a, h2, h3, [data-automation*='title']").first.text_content()
                title = (title or "").strip()
            except Exception:
                title = None

            # URLs
            href = None
            try:
                href = await c.locator("a[href]").first.get_attribute("href")
            except Exception:
                pass
            full_url = f"https://www.walmart.ca{href}" if href and href.startswith("/") else href

            # prix
            sale_txt = None
            was_txt = None
            for sel in [
                "[data-automation*='current-price']",
                ".price-current",
                "[class*='sale']",
                "[data-automation='price-raw']",
            ]:
                try:
                    sale_txt = await c.locator(sel).first.text_content()
                    if sale_txt:
                        break
                except Exception:
                    pass
            for sel in [
                "[data-automation*='was-price']",
                ".price-was",
                "s, del",
                "[class*='was']",
            ]:
                try:
                    was_txt = await c.locator(sel).first.text_content()
                    if was_txt:
                        break
                except Exception:
                    pass

            p_sale = normalize_price(sale_txt)
            p_was = normalize_price(was_txt)
            if not title:
                continue

            disc = None
            if p_sale and p_was and p_was > 0:
                disc = round((1 - (p_sale / p_was)) * 100)

            # image (optionnel)
            img = None
            for sel in ["img[src]", "img[data-src]"]:
                try:
                    img = await c.locator(sel).first.get_attribute("src") or await c.locator(sel).first.get_attribute("data-src")
                    if img:
                        break
                except Exception:
                    pass

            if p_sale or p_was:
                batch.append({
                    "title": title,
                    "price_sale": p_sale,
                    "price_regular": p_was,
                    "discount_pct": disc,
                    "product_url": full_url,
                    "image": img,
                    "category": name,
                    "source": url,
                })

        if not batch:
            empty_pages += 1
        else:
            items.extend(batch)
            empty_pages = 0

        # Heuristique d’arrêt : 2 pages vides d’affilée ou > 30 pages explorées
        if empty_pages >= 2 or page_num >= 30:
            break
        page_num += 1

    # Écriture JSON
    out = OUT_DIR / f"{name}.json"
    with out.open("w", encoding="utf-8") as f:
        json.dump(items, f, ensure_ascii=False, indent=2)
    print(f"{name}: {len(items)} produits → {out}")
    await page.close()

async def main():
    async with async_playwright() as p:
        try:
            browser = await p.chromium.launch(
                headless=True,
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--no-sandbox",
                    "--disable-dev-shm-usage",
                ],
            )
        except PlaywrightError as exc:
            if "Executable doesn't exist" not in str(exc):
                raise
            install_chromium_if_needed()
            browser = await p.chromium.launch(
                headless=True,
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--no-sandbox",
                    "--disable-dev-shm-usage",
                ],
            )
        context = await browser.new_context(
            locale="fr-CA",
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        )
        for name, url in CATEGORIES.items():
            await scrape_category(context, name, url)
        await context.close()
        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
