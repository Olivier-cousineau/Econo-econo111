"""Scraper for Canadian Tire liquidation deals specific to the St-Jérôme store."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

from playwright.sync_api import (
    TimeoutError as PlaywrightTimeoutError,
    sync_playwright,
)

URL = "https://www.canadiantire.ca/fr/promotions/liquidation.html?store=271"
OUTPUT_PATH = Path("liquidation_ct_stjerome.json")
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36"
)
PRODUCT_SELECTORS = [
    "[data-automation='product-card']",
    "[data-test='product-card']",
    ".product-list__item",
]
NEXT_BUTTON_SELECTORS = [
    "button[aria-label*='Suivant']",
    "button[aria-label*='Next']",
]


def _extract_text(element, selector: str) -> str:
    """Safely extract text from a selector under the given element."""
    sub_el = element.query_selector(selector)
    return sub_el.inner_text().strip() if sub_el else ""


def _extract_attribute(element, selector: str, attribute: str) -> str:
    sub_el = element.query_selector(selector)
    if not sub_el:
        return ""
    value = sub_el.get_attribute(attribute)
    return value.strip() if value else ""


def _dismiss_overlays(page) -> None:
    """Attempt to close cookie or location overlays that hide content."""

    overlay_selectors = [
        "#onetrust-accept-btn-handler",
        "button:has-text('Accepter tout')",
        "button:has-text('Tout accepter')",
        "button:has-text('J\'accepte')",
        "button:has-text('Continuer')",
        "button:has-text('Fermer')",
    ]

    for selector in overlay_selectors:
        try:
            overlay = page.locator(selector)
            if overlay.is_visible(timeout=1_000):
                overlay.click(timeout=2_000)
                page.wait_for_timeout(500)
        except PlaywrightTimeoutError:
            continue
        except Exception:
            continue


def _wait_for_product_selector(page) -> str:
    for selector in PRODUCT_SELECTORS:
        try:
            page.wait_for_selector(selector, timeout=10_000)
            return selector
        except PlaywrightTimeoutError:
            continue

    raise PlaywrightTimeoutError(
        "Unable to find product listing on liquidation page."
    )


def scrape_liquidation_ct() -> List[Dict[str, Any]]:
    print("Début du scraper Playwright")
    with sync_playwright() as p:
        print("Lancement de Chromium en mode headless…")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--no-sandbox"])
        context = browser.new_context(
            locale="fr-CA",
            user_agent=USER_AGENT,
            viewport={"width": 1280, "height": 720},
        )
        page = context.new_page()
        page.set_default_timeout(60_000)
        print("Ouverture de la page de liquidation…")
        page.goto(URL, wait_until="domcontentloaded")
        page.wait_for_timeout(5_000)
        print("Tentative de fermeture des overlays…")
        _dismiss_overlays(page)
        print("Recherche du sélecteur produit actif…")
        active_selector = _wait_for_product_selector(page)
        print(f"Sélecteur actif identifié: {active_selector}")
        page.goto(URL, wait_until="domcontentloaded")
        page.wait_for_timeout(5_000)
        _dismiss_overlays(page)
        active_selector = _wait_for_product_selector(page)

        results: List[Dict[str, Any]] = []
        seen_urls = set()

        while True:
            print("Récupération des produits sur la page courante…")
            items = page.query_selector_all(active_selector)
            for item in items:
                titre = _extract_text(
                    item,
                    ".product-title, .productCard__title, [data-test='product-title']",
                )
                prix = _extract_text(
                    item,
                    ".price__value, [data-test='product-price'], [data-automation='price']",
                )
                rabais = _extract_text(
                    item,
                    ".badge--savings, [data-test='badge-savings'], [data-automation='badge-savings']",
                )
                relative_url = _extract_attribute(
                    item,
                    ".product-title a, .productCard__title a, [data-test='product-title'] a",
                    "href",
                )
                image = _extract_attribute(
                    item,
                    ".product-image img, img[loading='lazy']",
                    "src",
                )

                if not relative_url or relative_url in seen_urls:
                    continue

                seen_urls.add(relative_url)
                results.append(
                    {
                        "titre": titre,
                        "prix": prix,
                        "rabais": rabais,
                        "url": f"https://www.canadiantire.ca{relative_url}",
                        "image": image,
                    }
                )

            next_btn = None
            for selector in NEXT_BUTTON_SELECTORS:
                next_candidate = page.query_selector(selector)
                if next_candidate and next_candidate.is_enabled():
                    next_btn = next_candidate
                    break

            if next_btn:
                print("Bouton \"Suivant\" détecté, passage à la page suivante…")
                next_btn.click()
                page.wait_for_timeout(2_500)
                _dismiss_overlays(page)
                try:
                    page.wait_for_selector(active_selector, timeout=10_000)
                except PlaywrightTimeoutError:
                    print(
                        "Sélecteur initial introuvable après pagination, nouvelle recherche…"
                    )
                    active_selector = _wait_for_product_selector(page)
                    print(f"Nouveau sélecteur actif: {active_selector}")
            else:
                print("Aucun bouton \"Suivant\" disponible, fin de la pagination.")
                break

        browser.close()
        print("Navigateur fermé, extraction terminée.")
                    active_selector = _wait_for_product_selector(page)
            else:
                break

        browser.close()

    return results


def main() -> None:
    print("Démarrage du script de scraping Canadian Tire St-Jérôme…")
    data = scrape_liquidation_ct()
    print(f"Nombre total d'offres collectées: {len(data)}")
    print("Écriture des résultats dans le fichier JSON…")
    data = scrape_liquidation_ct()
    OUTPUT_PATH.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"Fichier écrit: {OUTPUT_PATH.resolve()}")


if __name__ == "__main__":
    main()
