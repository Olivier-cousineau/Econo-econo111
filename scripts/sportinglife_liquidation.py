from __future__ import annotations

import asyncio
import csv
from pathlib import Path
from typing import Iterable, List

from playwright.async_api import (
    TimeoutError as PlaywrightTimeoutError,
    async_playwright,
)

URL = "https://www.sportinglife.ca/fr-CA/liquidation/"
OUTPUT_FILE = "sportinglife_laval_liquidation.csv"
FIELDNAMES = [
    "Nom du produit",
    "Prix réduit",
    "Prix original",
    "Image",
    "Lien",
]
PRODUCT_CARD_SELECTOR = (
    ".product-tile, [data-testid=\"product-tile\"], [data-testid=\"productTile\"], "
    "[data-testid=\"product-card\"], [data-component=\"ProductCard\"], "
    "article[data-testid=\"plp-product-tile\"], article[data-test=\"product-tile\"], "
    "li.grid-tile, div.grid-tile, div.product-grid__tile, div.plp-product-grid__item"
)

PRODUCT_CONTENT_WAIT_SELECTOR = (
    ".pdp-link, .product-name, [data-testid=\"productTile-title\"], "
    "[data-testid=\"product-card\"], [data-component=\"ProductCard\"], "
    "article[data-testid=\"plp-product-tile\"], article[data-test=\"product-tile\"]"
)


def save_rows(rows: Iterable[dict]) -> None:
    """Écrit le fichier CSV, même en l'absence de produits."""

    with open(OUTPUT_FILE, "w", newline="", encoding="utf-8") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)


async def accept_cookies(page) -> bool:
    """Ferme les bannières de consentement si elles sont visibles."""

    cookie_selectors: List[str] = [
        "#onetrust-accept-btn-handler",
        "button:has-text(\"Accepter\")",
        "button:has-text(\"J'accepte\")",
        "button:has-text(\"Tout accepter\")",
        "button:has-text(\"Allow all\")",
        "button:has-text(\"Accept All\")",
        "button:has-text(\"Autoriser tous\")",
    ]

    for selector in cookie_selectors:
        locator = page.locator(selector).first
        try:
            if await locator.count() == 0:
                continue
            await locator.wait_for(state="visible", timeout=2000)
            await locator.click()
            await page.wait_for_timeout(500)
            print("🍪 Bandeau de cookies accepté.")
            return True
        except PlaywrightTimeoutError:
            continue
        except Exception:
            continue
    return False


async def close_location_modal(page) -> bool:
    """Ferme la fenêtre de sélection de magasin si elle apparaît."""

    modal_buttons: List[str] = [
        "button:has-text(\"Continuer sans\")",
        "button:has-text(\"Magasiner en ligne\")",
        "button:has-text(\"Shop Online\")",
        "button:has-text(\"Continue without\")",
        "button:has-text(\"Continuer sans choisir\")",
        "button:has-text(\"Continue without selecting\")",
    ]

    for selector in modal_buttons:
        locator = page.locator(selector).first
        try:
            if await locator.count() == 0:
                continue
            await locator.wait_for(state="visible", timeout=2000)
            await locator.click()
            print("📍 Sélection de magasin ignorée.")
            return True
        except PlaywrightTimeoutError:
            continue
        except Exception:
            continue

    return False


async def expand_all_products(page, max_clicks: int = 40) -> None:
    """Clique sur « Voir plus » jusqu'à l'affichage de tous les produits."""

    previous_count = await count_products(page)
    for _ in range(max_clicks):
        button = page.locator("button:has-text(\"Voir plus\")").first
        try:
            await button.wait_for(state="visible", timeout=4000)
        except PlaywrightTimeoutError:
            break

        try:
            await button.scroll_into_view_if_needed()
            await button.click()
        except Exception:
            break

        try:
            await page.wait_for_function(
                "(selector, previousCount) => "
                "document.querySelectorAll(selector).length > previousCount",
                PRODUCT_CARD_SELECTOR,
                previous_count,
                timeout=10000,
            )
            previous_count = await count_products(page)
        except PlaywrightTimeoutError:
            # Aucun nouveau produit : on stoppe pour éviter une boucle infinie.
            break

        await page.wait_for_timeout(800)


async def count_products(page) -> int:
    return await page.evaluate(
        "(selector) => document.querySelectorAll(selector).length",
        PRODUCT_CARD_SELECTOR,
    )


async def extract_first_text(product, selectors: Iterable[str]) -> str:
    for selector in selectors:
        locator = product.locator(selector).first
        try:
            if await locator.count() == 0:
                continue
            text = (await locator.inner_text()).strip()
            if text:
                return text
        except Exception:
            continue
    return ""


async def extract_first_attribute(product, selectors: Iterable[str], attribute: str) -> str:
    for selector in selectors:
        locator = product.locator(selector).first
        try:
            if await locator.count() == 0:
                continue
            value = await locator.get_attribute(attribute)
            if value:
                return value.strip()
        except Exception:
            continue
    return ""


async def scrape_sportinglife():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(locale="fr-CA")
        page = await context.new_page()

        try:
            print("🌐 Ouverture de la page Sporting Life Liquidation...")
            await page.goto(URL, timeout=120000, wait_until="domcontentloaded")
            await page.wait_for_load_state("networkidle")

            await accept_cookies(page)

            await close_location_modal(page)

            try:
                await page.wait_for_selector(
                    PRODUCT_CONTENT_WAIT_SELECTOR,
                    state="attached",
                    timeout=60000,
                )
            except PlaywrightTimeoutError:
                print("⚠️ Aucun produit trouvé avant expiration du délai.")
                html = await page.content()
                Path("debug_sportinglife.html").write_text(html, encoding="utf-8")
                save_rows([])
                return

            await expand_all_products(page)

            product_locator = page.locator(PRODUCT_CARD_SELECTOR)
            product_count = await product_locator.count()
            if product_count == 0:
                print("⚠️ Aucun produit détecté malgré le chargement de la page.")
                html = await page.content()
                Path("debug_sportinglife.html").write_text(html, encoding="utf-8")
                save_rows([])
                return

            print("✅ Produits trouvés, extraction en cours...")

            name_selectors = [
                ".pdp-link",
                "a[data-testid='productTile-link']",
                ".product-name",
                "a[aria-label]",
                "[data-testid='product-card'] a",
                "article[data-testid='plp-product-tile'] a",
                "h3 a",
            ]
            price_now_selectors = [
                ".sales",
                "[data-testid='productTile-price'] .sales",
                ".price-sales",
                ".product-pricing__price",
                "[data-testid='price-current']",
                "span[data-test='price-sales']",
            ]
            price_original_selectors = [
                ".was",
                "[data-testid='productTile-price'] .was",
                ".price-standard",
                ".product-pricing__was",
                "[data-testid='price-original']",
                "span[data-test='price-standard']",
            ]
            link_selectors = [
                ".pdp-link",
                "a[data-testid='productTile-link']",
                "a[href]",
                "[data-testid='product-card'] a",
                "article[data-testid='plp-product-tile'] a",
            ]

            data = []
            for index in range(product_count):
                product = product_locator.nth(index)
                name = await extract_first_text(product, name_selectors)
                price_now = await extract_first_text(product, price_now_selectors)
                price_original = await extract_first_text(product, price_original_selectors)
                image = await extract_first_attribute(product, ["img"], "src")
                link = await extract_first_attribute(product, link_selectors, "href")

                if link and not link.startswith("http"):
                    link = "https://www.sportinglife.ca" + link

                data.append(
                    {
                        "Nom du produit": name,
                        "Prix réduit": price_now,
                        "Prix original": price_original or "—",
                        "Image": image,
                        "Lien": link,
                    }
                )

            save_rows(data)

            print(f"💾 {len(data)} produits enregistrés dans {OUTPUT_FILE}")
        except Exception as error:
            print(f"❌ Erreur inattendue lors du scraping : {error}")
            save_rows([])
            raise
        finally:
            await context.close()
            await browser.close()


if __name__ == "__main__":
    asyncio.run(scrape_sportinglife())
