"""
Scraper Canadian Tire via Scrape.do
By Olivier Cousineau – EconoDeal
"""

import json
import requests
from bs4 import BeautifulSoup
from datetime import datetime

# 🔑 Ton token Scrape.do (remplace par un secret GitHub dans le futur)
SCRAPE_DO_API_KEY = "79806d0a26a2413fb4a1c33f14dda9743940a7548ba"

# 🌐 URL à scraper
TARGET_URL = "https://www.canadiantire.ca/fr/promotions/liquidation.html"

# ✅ Scrape.do attend l'API Key dans les headers, pas dans l'URL
headers = {"x-api-key": SCRAPE_DO_API_KEY}
params = {
    "url": TARGET_URL,
    "render": "true",  # exécute le JS
    "premium_proxy": "true"  # contourne les protections si besoin
}

print("🕐 Téléchargement de la page Canadian Tire via Scrape.do...")
response = requests.get("https://api.scrape.do/v1/scrape", headers=headers, params=params)

if response.status_code != 200:
    print(f"❌ Erreur Scrape.do ({response.status_code}) : {response.text[:200]}")
    exit(1)

html = response.text
print("✅ Page reçue avec succès!")

# Sauvegarde HTML pour debug (facultatif)
with open("debug_canadiantire.html", "w", encoding="utf-8") as f:
    f.write(html)

soup = BeautifulSoup(html, "html.parser")

# 📦 Extraction des produits
products = []
items = soup.select(".product-tile, .product__list-item")

for item in items:
    name = item.select_one(".product__title, .product-tile__title")
    image = item.select_one("img")
    original_price = item.select_one(".price__was, .price-was")
    sale_price = item.select_one(".price__sale, .price-sale")
    link = item.select_one("a")

    data = {
        "product_name": name.get_text(strip=True) if name else None,
        "original_price": original_price.get_text(strip=True) if original_price else None,
        "discount_price": sale_price.get_text(strip=True) if sale_price else None,
        "image_url": image["src"] if image and image.has_attr("src") else None,
        "product_link": f"https://www.canadiantire.ca{link['href']}" if link and link.has_attr("href") else None,
        "availability": "En stock" if "En stock" in item.get_text() else "Non précisé"
    }

    if data["product_name"]:
        products.append(data)

print(f"🧾 {len(products)} produits trouvés sur la page.")

# 💾 Sauvegarde JSON propre
timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M")
output_file = f"data/canadian_tire_liquidation_{timestamp}.json"

with open(output_file, "w", encoding="utf-8") as f:
    json.dump(products, f, indent=2, ensure_ascii=False)

print(f"✅ Données sauvegardées dans {output_file}")
