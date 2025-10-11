#!/usr/bin/env python3
"""Daily Amazon Canada data fetcher for EconoDeal.

This script pulls product data from the Amazon Product Advertising API (PA API)
for a configurable list of keywords and stores the results as JSON that matches
EconoDeal's expected `/data` schema. If the API cannot be reached or returns no
items, the script automatically falls back to generating deterministic dummy
entries so the site still shows content.

Environment variables expected:
    PAAPI_CLIENT_ID        -> Your PA API access key (amzn1.application-oa2-client...)
    PAAPI_CLIENT_SECRET    -> Your PA API secret key
    PAAPI_ASSOCIATE_TAG    -> Your Amazon Associates partner tag

Usage examples:
    python admin/amazon_paapi_daily.py
    python admin/amazon_paapi_daily.py --keywords "gaming laptop" --limit 5
    python admin/amazon_paapi_daily.py --output data/amazon_custom.json
    python admin/amazon_paapi_daily.py --no-api --limit 3  # mode test sans appel API

Install dependencies:
    pip install requests

Amazon PA API docs: https://webservices.amazon.com/paapi5/documentation/
"""
from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import logging
import os
import random
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Optional

LOGGER = logging.getLogger("amazon_paapi_daily")

HOST = "webservices.amazon.ca"
REGION = "us-east-1"
SERVICE = "ProductAdvertisingAPI"
CONTENT_TYPE = "application/json; charset=UTF-8"
TARGET = "com.amazon.paapi5.v1.ProductAdvertisingAPIv1.SearchItems"
DEFAULT_OUTPUT = Path(__file__).resolve().parents[1] / "data" / "amazon_ca_daily.json"
DEFAULT_KEYWORDS_FILE = Path(__file__).resolve().parent / "amazon_keywords.json"
DEFAULT_LIMIT = 6


@dataclass
class Deal:
    """Represents a single deal entry compatible with the site JSON schema."""

    title: str
    image: str
    price: float
    sale_price: float
    store: str
    city: str
    url: str

    def to_dict(self) -> Dict[str, object]:
        return {
            "title": self.title,
            "image": self.image,
            "price": round(self.price, 2),
            "salePrice": round(self.sale_price, 2),
            "store": self.store,
            "city": self.city,
            "url": self.url,
        }


def _sign(key: bytes, msg: str) -> bytes:
    return hmac.new(key, msg.encode("utf-8"), hashlib.sha256).digest()


def _signature_key(secret_key: str, date_stamp: str, region: str, service: str) -> bytes:
    k_date = _sign(("AWS4" + secret_key).encode("utf-8"), date_stamp)
    k_region = hmac.new(k_date, region.encode("utf-8"), hashlib.sha256).digest()
    k_service = hmac.new(k_region, service.encode("utf-8"), hashlib.sha256).digest()
    return hmac.new(k_service, b"aws4_request", hashlib.sha256).digest()


def _build_headers(payload: bytes, access_key: str, secret_key: str) -> Dict[str, str]:
    now = datetime.now(timezone.utc)
    amz_date = now.strftime("%Y%m%dT%H%M%SZ")
    date_stamp = now.strftime("%Y%m%d")
    canonical_uri = "/paapi5/searchitems"
    canonical_querystring = ""
    canonical_headers = "\n".join(
        [
            f"content-type:{CONTENT_TYPE}",
            f"host:{HOST}",
            f"x-amz-date:{amz_date}",
            f"x-amz-target:{TARGET}",
        ]
    )
    signed_headers = "content-type;host;x-amz-date;x-amz-target"
    payload_hash = hashlib.sha256(payload).hexdigest()
    canonical_request = (
        "POST\n"
        f"{canonical_uri}\n"
        f"{canonical_querystring}\n"
        f"{canonical_headers}\n\n"
        f"{signed_headers}\n"
        f"{payload_hash}"
    )

    algorithm = "AWS4-HMAC-SHA256"
    credential_scope = f"{date_stamp}/{REGION}/{SERVICE}/aws4_request"
    string_to_sign = (
        f"{algorithm}\n"
        f"{amz_date}\n"
        f"{credential_scope}\n"
        f"{hashlib.sha256(canonical_request.encode('utf-8')).hexdigest()}"
    )
    signing_key = _signature_key(secret_key, date_stamp, REGION, SERVICE)
    signature = hmac.new(signing_key, string_to_sign.encode("utf-8"), hashlib.sha256).hexdigest()

    authorization_header = (
        f"{algorithm} Credential={access_key}/{credential_scope}, "
        f"SignedHeaders={signed_headers}, Signature={signature}"
    )

    return {
        "Content-Type": CONTENT_TYPE,
        "X-Amz-Date": amz_date,
        "X-Amz-Target": TARGET,
        "Authorization": authorization_header,
        "Host": HOST,
    }


def _extract_float(value: Optional[Dict[str, object]]) -> Optional[float]:
    if not value:
        return None
    amount = value.get("Amount")
    if isinstance(amount, (int, float)):
        return float(amount)
    return None


def _parse_item(item: Dict[str, object], keyword: str) -> Optional[Deal]:
    title = (
        item.get("ItemInfo", {})
        .get("Title", {})
        .get("DisplayValue")
    )
    url = item.get("DetailPageURL")
    images = item.get("Images", {})
    image = (
        images.get("Primary", {})
        .get("Large", {})
        .get("URL")
    )
    listing = None
    offers = item.get("Offers", {})
    listings = offers.get("Listings") if isinstance(offers.get("Listings"), list) else []
    if listings:
        listing = listings[0]
    price_info = listing.get("Price") if isinstance(listing, dict) else None
    savings_info = listing.get("SavingBasis") if isinstance(listing, dict) else None
    sale_price = _extract_float(price_info)
    original_price = _extract_float(savings_info)

    if title and url and image and sale_price:
        if not original_price or original_price < sale_price:
            original_price = sale_price
        return Deal(
            title=title,
            image=image,
            price=original_price,
            sale_price=sale_price,
            store="Amazon Canada",
            city="En ligne",
            url=url,
        )

    LOGGER.debug("Skipping item for keyword '%s' due to missing fields", keyword)
    return None


def fetch_from_paapi(
    keywords: Iterable[str],
    access_key: str,
    secret_key: str,
    associate_tag: str,
    limit: int,
) -> List[Deal]:
    import requests

    url = f"https://{HOST}/paapi5/searchitems"
    deals: List[Deal] = []

    for keyword in keywords:
        remaining = limit
        page = 1
        while remaining > 0 and page <= 10:  # PA API allows up to 10 pages
            batch = min(remaining, 10)
            body = {
                "Keywords": keyword,
                "Marketplace": "www.amazon.ca",
                "PartnerTag": associate_tag,
                "PartnerType": "Associates",
                "ItemCount": batch,
                "ItemPage": page,
                "Resources": [
                    "Images.Primary.Large",
                    "ItemInfo.Title",
                    "Offers.Listings.Price",
                    "Offers.Listings.SavingBasis",
                ],
            }
            payload = json.dumps(body, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
            headers = _build_headers(payload, access_key, secret_key)

            LOGGER.info("Requesting '%s' (page %s, %s items)", keyword, page, batch)
            response = requests.post(url, data=payload, headers=headers, timeout=30)

            if response.status_code != 200:
                LOGGER.warning(
                    "PA API request failed for '%s' (status %s): %s",
                    keyword,
                    response.status_code,
                    response.text[:200],
                )
                break

            data = response.json()
            items = data.get("SearchResult", {}).get("Items", [])
            if not items:
                LOGGER.info("No more items returned for '%s'", keyword)
                break

            for item in items:
                deal = _parse_item(item, keyword)
                if deal:
                    deals.append(deal)
            remaining -= batch
            page += 1

    return deals


def load_keywords(args_keywords: Optional[List[str]]) -> List[str]:
    if args_keywords:
        return [kw.strip() for kw in args_keywords if kw.strip()]
    if DEFAULT_KEYWORDS_FILE.exists():
        with DEFAULT_KEYWORDS_FILE.open("r", encoding="utf-8") as fh:
            data = json.load(fh)
            keywords = data.get("keywords", [])
            return [kw for kw in keywords if isinstance(kw, str) and kw.strip()]
    LOGGER.warning("Keyword file %s not found; using fallback keywords", DEFAULT_KEYWORDS_FILE)
    return ["amazon deals"]


def generate_dummy_deals(keywords: Iterable[str], limit: int) -> List[Deal]:
    random.seed(datetime.now().strftime("%Y%m%d"))
    catalog = []
    templates = [
        "Offre éclair {kw}",
        "Rabais {kw}",
        "Promo exclusive {kw}",
        "Essentiel {kw}",
        "Top vente {kw}",
    ]
    images = [
        "https://images-na.ssl-images-amazon.com/images/I/81w%2BAAAAAaL._AC_SL1500_.jpg",
        "https://images-na.ssl-images-amazon.com/images/I/71BBBBBBbL._AC_SL1500_.jpg",
        "https://images-na.ssl-images-amazon.com/images/I/61CCCCCCcL._AC_SL1500_.jpg",
    ]
    for keyword in keywords:
        for _ in range(limit):
            full_keyword = keyword.title()
            title = random.choice(templates).format(kw=full_keyword)
            base_price = random.uniform(40, 250)
            discount = random.uniform(0.1, 0.45)
            sale_price = base_price * (1 - discount)
            catalog.append(
                Deal(
                    title=title,
                    image=random.choice(images),
                    price=base_price,
                    sale_price=sale_price,
                    store="Amazon Canada",
                    city="En ligne",
                    url="https://www.amazon.ca/deal/fictif",
                )
            )
    return catalog


def persist_deals(deals: List[Deal], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    payload = [deal.to_dict() for deal in deals]
    with output_path.open("w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2, ensure_ascii=False)
    LOGGER.info("Saved %s deals to %s", len(payload), output_path)


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Fetch Amazon Canada deals into /data")
    parser.add_argument("--keywords", nargs="*", help="Override keywords (space separated list)")
    parser.add_argument("--limit", type=int, default=DEFAULT_LIMIT, help="Items per keyword (default: %(default)s)")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT, help="Output JSON file")
    parser.add_argument(
        "--no-api",
        action="store_true",
        help="Skip API calls and generate deterministic dummy data",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        help="Logging level (DEBUG, INFO, WARNING, ...)",
    )
    return parser.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> int:
    args = parse_args(argv)
    logging.basicConfig(level=getattr(logging, args.log_level.upper(), logging.INFO), format="%(levelname)s: %(message)s")

    keywords = load_keywords(args.keywords)
    if not keywords:
        LOGGER.error("No keywords provided; aborting")
        return 1

    access_key = os.getenv("PAAPI_CLIENT_ID")
    secret_key = os.getenv("PAAPI_CLIENT_SECRET")
    associate_tag = os.getenv("PAAPI_ASSOCIATE_TAG")

    deals: List[Deal] = []
    if not args.no_api and access_key and secret_key and associate_tag:
        try:
            deals = fetch_from_paapi(keywords, access_key, secret_key, associate_tag, args.limit)
        except Exception as exc:  # pragma: no cover - defensive fallback
            LOGGER.exception("Error while querying PA API: %s", exc)

    if not deals:
        LOGGER.warning("Falling back to deterministic dummy deals")
        deals = generate_dummy_deals(keywords, args.limit)

    persist_deals(deals, args.output)
    return 0


if __name__ == "__main__":
    sys.exit(main())
