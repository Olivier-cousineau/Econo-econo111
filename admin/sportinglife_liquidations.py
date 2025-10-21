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
from html.parser import HTMLParser

try:  # pragma: no cover - import guard exercised at runtime
    from playwright.sync_api import Error as PlaywrightError
    from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
    from playwright.sync_api import sync_playwright
    PLAYWRIGHT_IMPORT_ERROR: ModuleNotFoundError | None = None
except ModuleNotFoundError as exc:  # pragma: no cover - import guard exercised at runtime
    PlaywrightError = PlaywrightTimeoutError = Exception  # type: ignore[assignment]
    sync_playwright = None  # type: ignore[assignment]
    PLAYWRIGHT_IMPORT_ERROR = exc

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


def _ensure_playwright_available() -> None:
    if sync_playwright is None:
        raise ModuleNotFoundError(
            "Playwright n'est pas installé. Exécutez `pip install playwright` "
            "puis `playwright install chromium`."
        ) from PLAYWRIGHT_IMPORT_ERROR


class LiquidationHTMLParser(HTMLParser):
    """Minimal HTML parser to extract Sporting Life liquidation products."""

    def __init__(self, base_url: str):
        super().__init__(convert_charrefs=True)
        self.base_url = base_url
        self.products: list[dict[str, Any]] = []
        self._current_product: dict[str, Any] | None = None
        self._product_depth = 0
        self._field_stack: list[dict[str, Any]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attrs_dict = {name: value or "" for name, value in attrs}
        classes = attrs_dict.get("class", "").split()

        if "product-item" in classes and tag in {"div", "article", "li"}:
            if self._current_product is not None:
                self._finalize_product()
            self._current_product = {}
            self._product_depth = 1
        elif self._current_product is not None:
            self._product_depth += 1
        else:
            return

        if self._current_product is None:
            return

        if tag == "a":
            href = attrs_dict.get("href")
            if href and not self._current_product.get("url"):
                self._current_product["url"] = urllib.parse.urljoin(self.base_url, href)

        field: str | None = None
        if "product-item-name" in classes:
            field = "nom"
        elif "old-price" in classes:
            field = "prix_original"
        elif "price" in classes and "old-price" not in classes:
            field = "prix_actuel"
        elif "savings" in classes:
            field = "rabais"

        if field:
            self._field_stack.append({"tag": tag, "field": field, "buffer": []})

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        # Treat <tag /> as start+end
        self.handle_starttag(tag, attrs)
        self.handle_endtag(tag)

    def handle_endtag(self, tag: str) -> None:
        if self._current_product is None:
            return

        while self._field_stack and self._field_stack[-1]["tag"] == tag:
            field_info = self._field_stack.pop()
            text = "".join(field_info["buffer"]).strip()
            if text and field_info["field"] not in self._current_product:
                self._current_product[field_info["field"]] = text

        if self._product_depth > 0:
            self._product_depth -= 1
        if self._product_depth == 0:
            self._finalize_product()

    def handle_data(self, data: str) -> None:
        if not data or not self._field_stack:
            return
        self._field_stack[-1]["buffer"].append(data)

    def _finalize_product(self) -> None:
        self._flush_field_stack()
        if self._current_product and self._current_product.get("nom"):
            self.products.append(
                {
                    "nom": self._current_product.get("nom"),
                    "prix_actuel": self._current_product.get("prix_actuel"),
                    "prix_original": self._current_product.get("prix_original"),
                    "rabais": self._current_product.get("rabais"),
                    "url": self._current_product.get("url"),
                }
            )

        self._current_product = None
        self._product_depth = 0
        self._field_stack.clear()

    def _flush_field_stack(self) -> None:
        while self._field_stack:
            field_info = self._field_stack.pop()
            text = "".join(field_info["buffer"]).strip()
            if text and self._current_product is not None and field_info["field"] not in self._current_product:
                self._current_product[field_info["field"]] = text


def parse_liquidation_html(html: str, base_url: str) -> list[dict[str, Any]]:
    """Extract liquidation products from an HTML document."""

    parser = LiquidationHTMLParser(base_url)
    parser.feed(html)
    parser.close()
    logging.debug("Parsed %s product containers from HTML", len(parser.products))
    return parser.products


def _load_html_via_playwright(
    *,
    url: str,
    headless: bool,
    wait_timeout: int,
    page_timeout: int,
    user_agent: str,
) -> str:
    _ensure_playwright_available()
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=headless)
        context = browser.new_context(user_agent=user_agent)
        try:
            page = context.new_page()
            page.set_default_timeout(wait_timeout)
            page.goto(url, wait_until="networkidle", timeout=page_timeout)
            page.wait_for_selector(".product-item", timeout=wait_timeout)
            html = page.content()
        finally:
            context.close()
            browser.close()

    return html


def _load_html_via_requests(*, url: str, timeout: float, user_agent: str) -> str:
    headers = {"User-Agent": user_agent}
    response = requests.get(url, headers=headers, timeout=timeout)
    response.raise_for_status()
    return response.text


def scrape_liquidations(
    *,
    url: str = DEFAULT_LIQUIDATION_URL,
    max_retries: int = DEFAULT_MAX_RETRIES,
    retry_delay: float = DEFAULT_RETRY_DELAY,
    headless: bool = True,
    page_timeout: int = DEFAULT_TIMEOUT,
    wait_timeout: int = DEFAULT_WAIT_TIMEOUT,
    html_snapshot: Path | None = None,
    use_requests: bool = False,
    request_timeout: float = 30.0,
) -> list[dict[str, Any]]:
    """Scrape liquidation products from Sporting Life with retry logic."""

    if html_snapshot:
        html_path = Path(html_snapshot)
        logging.info("Parsing liquidation snapshot from %s", html_path)
        html = html_path.read_text(encoding="utf-8")
        dataset = parse_liquidation_html(html, url)
        if dataset:
            logging.info("Successfully parsed %s products from snapshot", len(dataset))
            return dataset
        raise RuntimeError("Aucun produit de liquidation n'a été extrait du fichier HTML fourni.")

    last_exception: Exception | None = None

    for attempt in range(1, max_retries + 1):
        logging.info("Scraping Sporting Life liquidation page (attempt %s/%s)", attempt, max_retries)
        user_agent = random.choice(USER_AGENTS)
        logging.debug("Using user-agent: %s", user_agent)
        try:
            if use_requests:
                logging.debug("Fetching liquidation page with requests")
                html = _load_html_via_requests(
                    url=url,
                    timeout=request_timeout,
                    user_agent=user_agent,
                )
            else:
                logging.debug("Fetching liquidation page with Playwright")
                html = _load_html_via_playwright(
                    url=url,
                    headless=headless,
                    wait_timeout=wait_timeout,
                    page_timeout=page_timeout,
                    user_agent=user_agent,
                )

            dataset = parse_liquidation_html(html, url)
        except ModuleNotFoundError as exc:
            logging.error("Playwright indisponible: %s", exc)
            raise
        except (PlaywrightTimeoutError, PlaywrightError) as exc:
            last_exception = exc
            logging.warning("Playwright error during scraping: %s", exc)
        except requests.RequestException as exc:
            last_exception = exc
            logging.warning("HTTP error during scraping: %s", exc)
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
    parser.add_argument(
        "--html-snapshot",
        type=Path,
        help="Fichier HTML local à analyser (bypasse Playwright)",
    )
    parser.add_argument(
        "--use-requests",
        action="store_true",
        help="Charger la page via requests plutôt que Playwright",
    )
    parser.add_argument(
        "--request-timeout",
        type=float,
        default=30.0,
        help="Timeout HTTP pour requests (default: %(default)s s)",
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
            html_snapshot=args.html_snapshot,
            use_requests=args.use_requests,
            request_timeout=args.request_timeout,
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
