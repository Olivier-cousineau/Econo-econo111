import asyncio
import json
import os
import random
from typing import List

from playwright.async_api import async_playwright

# Liste des 73 magasins Walmart au Québec (ID, nom, ville, etc.)
magasins = [
    {"id_store": "1001", "ville": "Montréal", "adresse": "Adresse..."},
    # ... (complétez avec la liste exacte de tous les magasins)
]

# Liste de proxies résidentiels à utiliser
PROXIES: List[str] = [
    "http://user:pass@proxy1:port",
    "http://user:pass@proxy2:port",
    # ...
]

def load_proxies() -> List[str]:
    """Load proxy list from WALMART_PROXIES env var or fall back to defaults."""

    env_value = os.environ.get("WALMART_PROXIES")
    if env_value:
        try:
            parsed = json.loads(env_value)
        except json.JSONDecodeError as exc:
            raise ValueError(
                "WALMART_PROXIES doit contenir une liste JSON (ex: ['http://user:pass@proxy:port'])."
            ) from exc
        if not isinstance(parsed, list) or not all(isinstance(item, str) for item in parsed):
            raise ValueError("WALMART_PROXIES doit être une liste JSON de chaînes de caractères.")
        return parsed

    return PROXIES


async def scrape_liquidation(store, proxy_pool: List[str]):
    proxy = random.choice(proxy_pool) if proxy_pool else None
    url = f'https://www.walmart.ca/fr/store/{store["id_store"]}/liquidation'
    stealth_options = {
        "args": ["--disable-blink-features=AutomationControlled"],
    }
    launch_kwargs = {"headless": True, "args": stealth_options["args"]}
    if proxy:
        launch_kwargs["proxy"] = {"server": proxy}

    async with async_playwright() as p:
        browser = await p.chromium.launch(**launch_kwargs)
        page = await browser.new_page()
        await page.goto(url)

        # Attendre que la page charge les données, gérer anti-bot
        await page.wait_for_selector("div.product", timeout=15000)
        items = await page.query_selector_all("div.product")

        data = []
        for item in items:
            title = await item.query_selector_eval("h2", "element => element.innerText")
            price = await item.query_selector_eval(".price", "element => element.innerText")
            lien = await item.query_selector_eval("a", "el => el.href")
            data.append({
                "magasin": store["ville"],
                "titre": title,
                "prix": price,
                "url": lien
            })

        await browser.close()
        return data

# Boucle sur tous les magasins, avec limitation requêtes pour ne pas surcharger.
async def main():
    proxy_pool = load_proxies()
    if not proxy_pool:
        raise ValueError(
            "Aucun proxy n'a été fourni. Ajoutez des entrées dans PROXIES ou définissez la variable d'environnement WALMART_PROXIES."
        )

    results = []
    for i, magasin in enumerate(magasins):
        try:
            items = await scrape_liquidation(magasin, proxy_pool)
            results.extend(items)
        except Exception as e:
            print(f"Erreur magasin {magasin['ville']} : {e}")
        await asyncio.sleep(random.uniform(5, 15))  # Pause pour limiter le trafic sans bloquer l'event loop

    with open("liquidations_walmart_qc.json", "w", encoding="utf8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

asyncio.run(main())
