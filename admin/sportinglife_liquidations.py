"""Scrape Sporting Life liquidation products and upload them to EconoDeal."""
from __future__ import annotations

import argparse
import json
import logging
import os
import random
import sys
import time
import urllib.parse
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any

import requests
from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright

DEFAULT_LIQUIDATION_URL = os.getenv(
    "SPORTINGLIFE_LIQUIDATION_URL",
    "https://www.sportinglife.ca/fr-CA/liquidation/",
)
DEFAULT_OUTPUT_PATH = Path(
    os.getenv("SPORTINGLIFE_OUTPUT_FILE", "data/liquidations_sportinglife.json")
)
DEFAULT_API_URL = os.getenv(
    "SPORTINGLIFE_API_URL", "https://www.econodeal.ca/api/import_liquidations"
)
DEFAULT_LOG_PATH = Path(
    os.getenv("SPORTINGLIFE_LOG_FILE", "logs/sportinglife_scraper.log")
)
DEFAULT_MAX_RETRIES = int(os.getenv("SPORTINGLIFE_MAX_RETRIES", "3"))
DEFAULT_RETRY_DELAY = float(os.getenv("SPORTINGLIFE_RETRY_DELAY", "5.0"))
DEFAULT_TIMEOUT = int(os.getenv("SPORTINGLIFE_PAGE_TIMEOUT", "60000"))
DEFAULT_WAIT_TIMEOUT = int(os.getenv("SPORTINGLIFE_WAIT_TIMEOUT", "30000"))

USER_AGENTS = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_4) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/16.4 Safari/605.1.15",
    "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:124.0) Gecko/20100101 Firefox/124.0",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1",
    "Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/123.0.0.0 Mobile Safari/537.36",
)


def configure_logging(level: int, log_path: Path | None) -> None:
    """Configure structured logging to both STDOUT and an optional file."""

    handlers: list[logging.Handler] = [logging.StreamHandler(sys.stdout)]

    if log_path is not None:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        handlers.append(
            RotatingFileHandler(
                log_path,
                maxBytes=1_000_000,
                backupCount=3,
                encoding="utf-8",
            )
        )

    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=handlers,
    )


def _extract_text(node, selector: str) -> str | None:
    element = node.query_selector(selector)
    if not element:
        return None
    text = element.inner_text()
    return text.strip() if text else None


def _resolve_href(node, base_url: str) -> str | None:
    element = node.query_selector("a[href]")
    if not element:
        return None
    href = element.get_attribute("href")
    if not href:
        return None
    return urllib.parse.urljoin(base_url, href)


def scrape_liquidations(
    *,
    url: str = DEFAULT_LIQUIDATION_URL,
    max_retries: int = DEFAULT_MAX_RETRIES,
    retry_delay: float = DEFAULT_RETRY_DELAY,
    headless: bool = True,
    page_timeout: int = DEFAULT_TIMEOUT,
    wait_timeout: int = DEFAULT_WAIT_TIMEOUT,
) -> list[dict[str, Any]]:
    """Scrape liquidation products from Sporting Life with retry logic."""

    last_exception: Exception | None = None

    for attempt in range(1, max_retries + 1):
        logging.info("Scraping Sporting Life liquidation page (attempt %s/%s)", attempt, max_retries)
        user_agent = random.choice(USER_AGENTS)
        logging.debug("Using user-agent: %s", user_agent)

        dataset: list[dict[str, Any]] | None = None

        try:
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(headless=headless)
                context = browser.new_context(user_agent=user_agent)
                try:
                    page = context.new_page()
                    page.set_default_timeout(wait_timeout)

                    page.goto(url, wait_until="networkidle", timeout=page_timeout)
                    page.wait_for_selector(".product-item", timeout=wait_timeout)

                    products = page.query_selector_all(".product-item")
                    logging.info("Detected %s product containers", len(products))

                    dataset = []
                    for product in products:
                        name = _extract_text(product, ".product-item-name")
                        if not name:
                            logging.debug("Skipping product without a name")
                            continue

                        item = {
                            "nom": name,
                            "prix_actuel": _extract_text(product, ".price"),
                            "prix_original": _extract_text(product, ".old-price"),
                            "rabais": _extract_text(product, ".savings"),
                            "url": _resolve_href(product, url),
                        }
                        dataset.append(item)
                finally:
                    context.close()
                    browser.close()

        except (PlaywrightTimeoutError, PlaywrightError) as exc:
            last_exception = exc
            logging.warning("Playwright error during scraping: %s", exc)
        except Exception as exc:  # pragma: no cover - defensive
            last_exception = exc
            logging.exception("Unexpected error during scraping")
        else:
            if dataset:
                logging.info("Successfully scraped %s liquidation products", len(dataset))
                return dataset
            last_exception = RuntimeError("Aucun produit de liquidation n'a été extrait.")
            logging.warning("Page loaded but no products were extracted")

        if attempt < max_retries:
            sleep_time = retry_delay * attempt
            logging.info("Retrying in %.1f seconds", sleep_time)
            time.sleep(sleep_time)

    if last_exception:
        raise last_exception
    raise RuntimeError("Scraper failed without raising an exception")


def write_atomic_json(data: list[dict[str, Any]], destination: Path) -> None:
    """Persist data to ``destination`` atomically."""

    destination.parent.mkdir(parents=True, exist_ok=True)
    temp_path = destination.with_suffix(destination.suffix + ".tmp")
    with temp_path.open("w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=2, ensure_ascii=False)
    temp_path.replace(destination)
    logging.info("Dataset written to %s", destination)


def upload_to_api(
    data: list[dict[str, Any]],
    *,
    api_url: str = DEFAULT_API_URL,
    api_token: str | None = None,
    timeout: int = 30,
) -> requests.Response:
    """Upload the dataset to the remote API."""

    headers = {"Content-Type": "application/json"}
    if api_token:
        headers["Authorization"] = f"Bearer {api_token}"
    else:
        logging.warning("No API token provided. The upload will be attempted without authentication.")

    logging.info("Uploading dataset to %s", api_url)
    response = requests.post(api_url, headers=headers, json=data, timeout=timeout)
    response.raise_for_status()
    logging.info("Upload succeeded with status code %s", response.status_code)
    return response


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--url",
        default=DEFAULT_LIQUIDATION_URL,
        help="URL de la page liquidation à scruter (default: %(default)s)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT_PATH,
        help="Chemin du fichier JSON de sortie (default: %(default)s)",
    )
    parser.add_argument(
        "--api-url",
        default=DEFAULT_API_URL,
        help="URL de l'API EconoDeal pour importer les liquidations",
    )
    parser.add_argument(
        "--api-token",
        default=os.getenv("SPORTINGLIFE_API_TOKEN"),
        help="Jeton Bearer pour l'API EconoDeal (env: SPORTINGLIFE_API_TOKEN)",
    )
    parser.add_argument(
        "--max-retries",
        type=int,
        default=DEFAULT_MAX_RETRIES,
        help="Nombre maximal de tentatives Playwright (default: %(default)s)",
    )
    parser.add_argument(
        "--retry-delay",
        type=float,
        default=DEFAULT_RETRY_DELAY,
        help="Délai de base entre les tentatives (default: %(default)s s)",
    )
    parser.add_argument(
        "--page-timeout",
        type=int,
        default=DEFAULT_TIMEOUT,
        help="Timeout de chargement de page en millisecondes (default: %(default)s)",
    )
    parser.add_argument(
        "--wait-timeout",
        type=int,
        default=DEFAULT_WAIT_TIMEOUT,
        help="Timeout pour attendre les éléments (default: %(default)s)",
    )
    parser.add_argument(
        "--headless",
        default=True,
        action=argparse.BooleanOptionalAction,
        help="Active/désactive le mode headless Playwright (default: activé)",
    )
    parser.add_argument(
        "--log-level",
        default=os.getenv("SPORTINGLIFE_LOG_LEVEL", "INFO"),
        help="Niveau de log (default: %(default)s)",
    )
    parser.add_argument(
        "--log-file",
        type=Path,
        default=DEFAULT_LOG_PATH,
        help="Chemin du fichier de log (default: %(default)s)",
    )
    parser.add_argument(
        "--skip-upload",
        action="store_true",
        help="Ne pas envoyer le résultat à l'API même si un token est disponible",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    log_level_name = args.log_level.upper()
    log_level = getattr(logging, log_level_name, logging.INFO)

    log_file: Path | None = args.log_file if args.log_file else None
    configure_logging(int(log_level), log_file)

    try:
        dataset = scrape_liquidations(
            url=args.url,
            max_retries=args.max_retries,
            retry_delay=args.retry_delay,
            headless=args.headless,
            page_timeout=args.page_timeout,
            wait_timeout=args.wait_timeout,
        )
    except Exception as exc:  # pragma: no cover - runtime path
        logging.exception("Scraping failed")
        return 1

    try:
        write_atomic_json(dataset, args.output)
    except OSError:
        logging.exception("Unable to persist the dataset to %s", args.output)
        return 1

    if not args.skip_upload:
        if not args.api_url:
            logging.info("API URL manquante, envoi sauté.")
        elif not args.api_token:
            logging.info(
                "Aucun jeton API fourni. Ajoutez --skip-upload pour masquer cet avertissement."
            )
        else:
            try:
                upload_to_api(
                    dataset,
                    api_url=args.api_url,
                    api_token=args.api_token,
                )
            except requests.RequestException:
                logging.exception("Upload to API failed")
                return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
