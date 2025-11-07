import asyncio
import json
import os
from pathlib import Path
from typing import List, Dict

from playwright.async_api import async_playwright, Page

# =============== CONFIG ===============
# Mets ici les catégories à visiter (URLs de départ)
CATEGORIES: List[Dict[str, str]] = [
    # Exemple – remplace par tes URLs de catégories:
    {"name": "televisions", "url": "https://www.bestbuy.ca/en-ca/category/tvs/21117"},
    {"name": "laptops", "url": "https://www.bestbuy.ca/en-ca/category/laptops-macbooks/20352"},
]
OUT_DIR = "screenshots"      # dossier de sortie
MAX_PAGES = 999              # sécurité : limite haute de pagination
HEADLESS = True              # passe à False pour debug local
VIEWPORT = {"width": 1600, "height": 1000}
WAIT_IDLE_MS = 120_000       # attente du réseau
# =====================================

SEE_ALL_SELECTORS = [
    "text=Voir tout",
    "text=Voir Tous",
    "text=See all",
    "a:has-text('Voir tout')",
    "a:has-text('See all')",
    "button:has-text('Voir tout')",
    "button:has-text('See all')",
]

NEXT_PAGE_SELECTORS = [
    "button[aria-label*='Next']",
    "a[aria-label*='Next']",
    "button:has-text('Suivant')",
    "a:has-text('Suivant')",
    "button:has-text('Next')",
    "a:has-text('Next')",
    "nav[role='navigation'] button:has(svg)",
]

PRODUCT_GRID_HINTS = [
    "[class*='productGrid']",
    "[data-automation*='product-grid']",
    "ul:has(li[class*='product'])",
    "main",
]


def ensure_json_serializable_categories() -> None:
    """Ensure categories are JSON serializable for logging purposes."""
    try:
        json.dumps(CATEGORIES)
    except TypeError as exc:
        raise ValueError("CATEGORIES must be a list of dictionaries with JSON-serializable values") from exc


async def click_if_visible(page: Page, selectors: List[str], timeout: int = 4000) -> bool:
    for sel in selectors:
        try:
            loc = page.locator(sel)
            if await loc.first().is_visible(timeout=timeout):
                await loc.first().click(timeout=timeout)
                return True
        except Exception:
            continue
    return False


async def wait_grid_or_idle(page: Page) -> None:
    # attendre que le contenu arrive
    for sel in PRODUCT_GRID_HINTS:
        try:
            await page.wait_for_selector(sel, timeout=6000, state="visible")
            return
        except Exception:
            pass
    await page.wait_for_load_state("networkidle", timeout=WAIT_IDLE_MS)


async def take_full_screenshot(page: Page, out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    # petit scroll pour charger les images lazy
    await page.evaluate("window.scrollTo(0,0)")
    await page.wait_for_timeout(500)
    await page.evaluate(
        """
        const h = document.body.scrollHeight;
        window.scrollTo(0, h);
    """
    )
    await page.wait_for_timeout(800)
    await page.screenshot(path=str(out_path), full_page=True)


async def capture_category(page: Page, name: str, url: str) -> None:
    base_dir = Path(OUT_DIR) / name
    await page.goto(url, timeout=WAIT_IDLE_MS)
    await page.wait_for_load_state("domcontentloaded", timeout=WAIT_IDLE_MS)

    # 1) Cliquer "Voir tout / See all" si présent
    await click_if_visible(page, SEE_ALL_SELECTORS)
    await wait_grid_or_idle(page)

    # 2) Boucle de pagination
    page_num = 1
    while page_num <= MAX_PAGES:
        await wait_grid_or_idle(page)
        out_file = base_dir / f"page-{page_num:03d}.png"
        print(f"[{name}] Screenshot page {page_num} -> {out_file}")
        await take_full_screenshot(page, out_file)

        # essayer de cliquer "Next"
        clicked = await click_if_visible(page, NEXT_PAGE_SELECTORS, timeout=2500)
        if not clicked:
            break  # plus de page
        # laisse le JS charger
        await page.wait_for_load_state("networkidle", timeout=WAIT_IDLE_MS)
        await page.wait_for_timeout(800)
        page_num += 1


async def main() -> None:
    ensure_json_serializable_categories()
    os.makedirs(OUT_DIR, exist_ok=True)
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=HEADLESS, slow_mo=150)
        context = await browser.new_context(locale="fr-CA", viewport=VIEWPORT)
        page = await context.new_page()

        # (optionnel) accepter un bandeau cookies si présent
        try:
            cookies_button = page.locator(
                "button:has-text('Accepter'), button:has-text('J’accepte'), button:has-text('Accept')"
            )
            if await cookies_button.is_visible(timeout=3000):
                await cookies_button.click()
        except Exception:
            pass

        for cat in CATEGORIES:
            await capture_category(page, cat["name"], cat["url"])

        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
