#!/usr/bin/env python3
"""Scrape Best Buy liquidation items and overwrite the site JSON files.

The script calls the public Best Buy developer API with the provided API key
and fetches every product currently on sale (``onSale=true``). The returned
items are normalized to the structure expected by the static site (see
``data/README.md``) and written to ``data/best-buy/liquidations.json`` by
default.

Two usage modes are available:

* ``--run-once`` – fetch the inventory a single time. This is ideal for
  immediate updates or testing the credentials.
* Scheduler (default) – keep the process running and automatically refresh the
  dataset every Sunday at 04:00 (America/Toronto timezone) as requested by the
  client. The scheduler is implemented without external dependencies.

Example (manual run):

```bash
python automation/bestbuy_liquidations.py --api-key "$BESTBUY_API_KEY" --run-once
```

The API key can also be supplied via the ``BESTBUY_API_KEY`` environment
variable.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Iterable, List

import requests

try:
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover (Python < 3.9)
    from backports.zoneinfo import ZoneInfo  # type: ignore


LOGGER = logging.getLogger("bestbuy_liquidations")

BESTBUY_API_URL = "https://api.bestbuy.com/v1/products((onSale=true)&(marketplace=false))"
DEFAULT_OUTPUT = Path("data/best-buy/liquidations.json")
DEFAULT_TIMEZONE = "America/Toronto"
TARGET_WEEKDAY = 6  # Sunday (Monday=0)
TARGET_HOUR = 4


def parse_args(argv: Iterable[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--api-key",
        dest="api_key",
        default=os.getenv("BESTBUY_API_KEY"),
        help="Best Buy developer API key (defaults to BESTBUY_API_KEY env variable).",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help="Destination JSON file (defaults to data/best-buy/liquidations.json).",
    )
    parser.add_argument(
        "--page-size",
        type=int,
        default=100,
        help="Number of products fetched per page (max 100).",
    )
    parser.add_argument(
        "--run-once",
        action="store_true",
        help="Fetch immediately and exit without scheduling future runs.",
    )
    parser.add_argument(
        "--timezone",
        default=DEFAULT_TIMEZONE,
        help="Timezone used for the Sunday 04:00 schedule (default: America/Toronto).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Fetch and display a summary without writing to disk.",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG"],
        help="Logging verbosity (default: INFO).",
    )
    return parser.parse_args(argv)


def fetch_liquidations(api_key: str, page_size: int) -> List[dict]:
    """Retrieve all on-sale products from the Best Buy API."""

    if not api_key:
        raise ValueError("An API key must be supplied via --api-key or BESTBUY_API_KEY")

    session = requests.Session()
    session.headers.update({"Accept": "application/json"})

    products: List[dict] = []
    page = 1

    while True:
        params = {
            "apiKey": api_key,
            "format": "json",
            "page": page,
            "pageSize": page_size,
            "show": ",".join(
                [
                    "sku",
                    "name",
                    "image",
                    "regularPrice",
                    "salePrice",
                    "url",
                    "onlineAvailability",
                    "shipping",
                    "customerReviewAverage",
                    "customerReviewCount",
                ]
            ),
        }

        LOGGER.debug("Fetching page %s", page)
        response = session.get(BESTBUY_API_URL, params=params, timeout=30)
        response.raise_for_status()
        payload = response.json()

        page_products = payload.get("products", [])
        LOGGER.debug("Received %s products on page %s", len(page_products), page)
        products.extend(page_products)

        total_pages = payload.get("totalPages", page)
        if page >= total_pages:
            break
        page += 1

    LOGGER.info("Fetched %s liquidation products from Best Buy", len(products))
    return products


def normalize_products(products: Iterable[dict]) -> List[dict]:
    """Convert Best Buy products to the JSON structure expected by the site."""

    normalized: List[dict] = []
    for product in products:
        try:
            regular_price = float(product.get("regularPrice") or 0)
            sale_price = float(product.get("salePrice") or 0)
        except (TypeError, ValueError):
            LOGGER.debug("Skipping product with invalid prices: %s", product.get("sku"))
            continue

        if not product.get("name") or not product.get("url"):
            LOGGER.debug("Skipping product missing name or url: %s", product.get("sku"))
            continue

        normalized.append(
            {
                "title": product.get("name", "Produit Best Buy"),
                "image": product.get("image") or "",
                "price": regular_price,
                "salePrice": sale_price,
                "store": "Best Buy",
                "city": "En ligne",
                "url": product.get("url"),
                "metadata": {
                    "sku": product.get("sku"),
                    "customerReviewAverage": product.get("customerReviewAverage"),
                    "customerReviewCount": product.get("customerReviewCount"),
                    "onlineAvailability": product.get("onlineAvailability"),
                },
            }
        )

    LOGGER.info("Normalized %s products", len(normalized))
    return normalized


def write_output(output_path: Path, items: List[dict]) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as handle:
        json.dump(items, handle, ensure_ascii=False, indent=2)
    LOGGER.info("Wrote %s products to %s", len(items), output_path)


def compute_next_run(now: datetime, tz: ZoneInfo) -> datetime:
    target = now.astimezone(tz)
    target = target.replace(hour=TARGET_HOUR, minute=0, second=0, microsecond=0)

    days_ahead = (TARGET_WEEKDAY - target.weekday()) % 7
    if days_ahead == 0 and target <= now.astimezone(tz):
        days_ahead = 7

    run_at = target + timedelta(days=days_ahead)
    return run_at


def sleep_until(run_at: datetime, tz: ZoneInfo) -> None:
    while True:
        now = datetime.now(tz)
        remaining = (run_at - now).total_seconds()
        if remaining <= 0:
            break
        sleep_chunk = min(remaining, 60)
        time.sleep(max(sleep_chunk, 1))


def run_job(api_key: str, output: Path, page_size: int, dry_run: bool) -> None:
    products = fetch_liquidations(api_key, page_size)
    normalized = normalize_products(products)
    if dry_run:
        LOGGER.info("Dry-run: %s produits normalisés (aucun fichier écrit)", len(normalized))
        return
    write_output(output, normalized)


def main(argv: Iterable[str] | None = None) -> int:
    args = parse_args(argv)
    logging.basicConfig(level=getattr(logging, args.log_level), format="%(asctime)s %(levelname)s %(message)s")

    if not args.api_key:
        LOGGER.error("Aucune clé API fournie. Utilisez --api-key ou la variable BESTBUY_API_KEY.")
        return 1

    tz = ZoneInfo(args.timezone)

    if args.run_once:
        LOGGER.info("Execution unique du scraper Best Buy")
        run_job(args.api_key, args.output, args.page_size, args.dry_run)
        return 0

    LOGGER.info(
        "Scheduler actif – la collecte Best Buy s'exécutera chaque dimanche à %02d:00 (%s)",
        TARGET_HOUR,
        args.timezone,
    )
    while True:
        run_at = compute_next_run(datetime.now(tz), tz)
        LOGGER.info("Prochaine collecte prévue le %s", run_at.isoformat())
        sleep_until(run_at, tz)
        try:
            run_job(args.api_key, args.output, args.page_size, args.dry_run)
        except Exception as exc:  # pragma: no cover - defensive logging
            LOGGER.exception("Échec lors de l'exécution du scraper Best Buy: %s", exc)


if __name__ == "__main__":  # pragma: no cover - CLI entrypoint
    sys.exit(main())
