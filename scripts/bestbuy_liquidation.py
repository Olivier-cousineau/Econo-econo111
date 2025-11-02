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
PAGE_SIZE = 100          # max per request (safe default)
MAX_PAGES = 20           # safety cap to avoid runaway loops
REQUEST_TIMEOUT = 30     # seconds
SLEEP_BETWEEN_REQUESTS = 0.5

if not API_KEY:
    print("ERROR: BESTBUY_API_KEY environment variable is not set.", file=sys.stderr)
    sys.exit(2)

def build_url(page: int = 1):
    # BestBuy v1 endpoint pattern; uses pageSize and page
    # filter: onSale=true to get discounted products
    return (
        "https://api.bestbuy.com/v1/products(onSale=true)"
        f"?apiKey={API_KEY}&format=json&pageSize={PAGE_SIZE}&page={page}"
    )

def fetch_page(page: int):
    url = build_url(page)
    try:
        resp = requests.get(url, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        return resp.json()
    except requests.HTTPError as e:
        print(f"[HTTP ERROR] page={page} url={url} -> {e}", file=sys.stderr)
        return None
    except Exception as e:
        print(f"[ERROR] page={page} -> {e}", file=sys.stderr)
        return None

def normalize_product(p: dict) -> dict:
    # Extract the fields we want, tolerance for missing keys
    return {
        "product_name": p.get("name") or p.get("longDescription") or "",
        "original_price": p.get("regularPrice") if p.get("regularPrice") is not None else "",
        "discount_price": p.get("salePrice") if p.get("salePrice") is not None else "",
        "image_url": p.get("image") or p.get("thumbnailImage") or "",
        "product_link": p.get("url") or p.get("addToCartUrl") or "",
        "availability": p.get("inStoreAvailability") or p.get("onlineAvailability") or "",
        "sku": p.get("sku") or ""
    }

def save_json(products: list):
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    payload = {
        "updated_at": datetime.utcnow().isoformat() + "Z",
        "total_products": len(products),
        "products": products
    }
    with OUTPUT_FILE.open("w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)
    print(f"Saved {len(products)} products to {OUTPUT_FILE}")

def main():
    print("Starting BestBuy liquidation fetch...")
    all_products = []
    for page in range(1, MAX_PAGES + 1):
        print(f"Fetching page {page}...")
        data = fetch_page(page)
        if not data:
            print(f"Stopping: failed to fetch or empty response on page {page}.")
            break

        products = data.get("products") or data.get("items") or []
        if not products:
            print(f"No products found on page {page}; stopping pagination.")
            break

        for p in products:
            try:
                normalized = normalize_product(p)
                all_products.append(normalized)
            except Exception as e:
                print(f"Warning: failed to normalize product: {e}")

        # If less than page size, we've reached the last page
        if len(products) < PAGE_SIZE:
            print("Last page detected (returned fewer items than page size).")
            break

        time.sleep(SLEEP_BETWEEN_REQUESTS)

    if all_products:
        # Optional: remove duplicates by sku+product_link
        seen = set()
        unique = []
        for item in all_products:
            key = (item.get("sku") or "") + "|" + (item.get("product_link") or "")
            if key in seen:
                continue
            seen.add(key)
            unique.append(item)

        save_json(unique)
    else:
        print("No products retrieved. Writing an empty JSON for diagnostics.")
        save_json([])

if __name__ == "__main__":
    main()
