#!/usr/bin/env python3
"""
bestbuy_liquidation.py
Fetch Best Buy discounted/onSale products via BestBuy API and save as JSON.
Reads API key from env var BESTBUY_API_KEY.

Outputs:
  - data/bestbuy_liquidation.json
"""

import os
import sys
import time
import json
import requests
from datetime import datetime
from pathlib import Path

# Config
API_KEY = os.getenv("BESTBUY_API_KEY")
OUTPUT_DIR = Path("data")
OUTPUT_FILE = OUTPUT_DIR / "bestbuy_liquidation.json"
PAGE_SIZE = 100
MAX_PAGES = 20
REQUEST_TIMEOUT = 30
SLEEP_BETWEEN_REQUESTS = 0.5

if not API_KEY:
    print("❌ ERROR: BESTBUY_API_KEY environment variable is not set.", file=sys.stderr)
    sys.exit(2)

def build_url(page: int = 1):
    """Build paginated API URL"""
    return (
        "https://api.bestbuy.com/v1/products(onSale=true)"
        f"?apiKey={API_KEY}&format=json&pageSize={PAGE_SIZE}&page={page}"
    )

def fetch_page(page: int):
    """Fetch one page of products"""
    url = build_url(page)
    try:
        resp = requests.get(url, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        return resp.json()
    except requests.HTTPError as e:
        print(f"[HTTP ERROR] page={page} -> {e}", file=sys.stderr)
        return None
    except Exception as e:
        print(f"[ERROR] page={page} -> {e}", file=sys.stderr)
        return None

def normalize_product(p: dict) -> dict:
    """Extract relevant product info"""
    return {
        "product_name": p.get("name") or "",
        "original_price": p.get("regularPrice") or "",
        "discount_price": p.get("salePrice") or "",
        "image_url": p.get("image") or "",
        "product_link": p.get("url") or "",
        "availability": (
            "In stock" if p.get("inStoreAvailability") or p.get("onlineAvailability") else "Out of stock"
        ),
        "sku": str(p.get("sku") or "")
    }

def save_json(products: list):
    """Save output file"""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    payload = {
        "updated_at": datetime.utcnow().isoformat() + "Z",
        "total_products": len(products),
        "products": products,
    }
    with OUTPUT_FILE.open("w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)
    print(f"💾 Saved {len(products)} products to {OUTPUT_FILE}")

def main():
    print("🚀 Starting BestBuy liquidation fetch...")
    all_products = []
    for page in range(1, MAX_PAGES + 1):
        print(f"Fetching page {page}...")
        data = fetch_page(page)
        if not data:
            print(f"⚠️ No response or failed fetch for page {page}")
            break

        products = data.get("products") or []
        if not products:
            print(f"✅ No more products (page {page} empty).")
            break

        for p in products:
            try:
                all_products.append(normalize_product(p))
            except Exception as e:
                print(f"⚠️ Could not parse a product: {e}")

        if len(products) < PAGE_SIZE:
            print("📦 Last page reached.")
            break
        time.sleep(SLEEP_BETWEEN_REQUESTS)

    # ✅ Fix: force SKU to string before concatenation
    seen = set()
    unique = []
    for item in all_products:
        key = str(item.get("sku") or "") + "|" + str(item.get("product_link") or "")
        if key in seen:
            continue
        seen.add(key)
        unique.append(item)

    save_json(unique)

if __name__ == "__main__":
    main()
