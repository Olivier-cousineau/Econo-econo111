"""Scraper Walmart (HTTP) avec rotation de proxies.

Ce module propose une alternative légère au scraper Playwright en utilisant
des requêtes ``requests`` classiques. Il récupère le JSON ``__NEXT_DATA__``
exposé dans les pages liquidation de Walmart Canada puis exporte des fichiers
compatibles avec le site statique.
"""

from __future__ import annotations

import argparse
import json
import random
import time
from pathlib import Path
from typing import List, Optional, Sequence, Set, Tuple

import requests
from bs4 import BeautifulSoup
from requests import Response

try:  # Support exécution directe et import au sein du package
    from incoming.walmart_common import (
        Deal,
        Store,
        build_deal_from_dict,
        deduplicate_deals,
        extract_from_state,
    )
    from incoming.walmart_scraper import (
        ensure_output_paths,
        load_proxies,
        load_stores,
        normalize_store_token,
        store_matches_filters,
        write_json,
    )
except ImportError:  # pragma: no cover - fallback pour exécution directe
    from walmart_common import (
        Deal,
        Store,
        build_deal_from_dict,
        deduplicate_deals,
        extract_from_state,
    )
    from walmart_scraper import (
        ensure_output_paths,
        load_proxies,
        load_stores,
        normalize_store_token,
        store_matches_filters,
        write_json,
    )

DEFAULT_TIMEOUT = 15
DEFAULT_MAX_RETRIES = 10
DEFAULT_DELAY_RANGE: Tuple[float, float] = (1.0, 4.0)
DEFAULT_AGGREGATED_FILENAME = "liquidations_walmart_qc.json"

USER_AGENTS: Tuple[str, ...] = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36",
)


def pick_proxy(proxies: List[str]) -> Optional[str]:
    if not proxies:
        return None
    return random.choice(proxies)


def build_headers() -> dict[str, str]:
    return {
        "User-Agent": random.choice(USER_AGENTS),
        "Accept-Language": "fr-FR,fr;q=0.9",
    }


def fetch_page(
    url: str,
    proxies: List[str],
    *,
    max_retries: int,
    timeout: int,
    delay_range: Tuple[float, float],
) -> str:
    """Download ``url`` using random proxies until success or timeout."""

    last_error: Optional[Exception] = None
    for attempt in range(1, max_retries + 1):
        proxy = pick_proxy(proxies)
        proxy_label = proxy or "direct"
        headers = build_headers()
        proxies_dict = {"http": proxy, "https": proxy} if proxy else None
        try:
            response: Response = requests.get(
                url,
                headers=headers,
                proxies=proxies_dict,
                timeout=timeout,
            )
            if response.status_code == 200:
                return response.text
            print(
                f"Echec (status {response.status_code}) avec le proxy {proxy_label} "
                f"(essai {attempt}/{max_retries})."
            )
        except Exception as exc:  # noqa: BLE001 - on loggue l'erreur pour inspection
            last_error = exc
            print(
                f"Echec avec le proxy {proxy_label} à l'essai {attempt}/{max_retries}: {exc}"
            )

        time.sleep(random.uniform(*delay_range))

    raise RuntimeError(
        "Impossible de charger la page après plusieurs tentatives via proxy."
    ) from last_error


def extract_deals_from_html(page_source: str) -> List[Deal]:
    """Parse ``page_source`` and return normalized deals."""

    soup = BeautifulSoup(page_source, "html.parser")
    script_tag = soup.find("script", {"id": "__NEXT_DATA__"})
    if script_tag is None or not script_tag.string:
        raise ValueError("Section JSON '__NEXT_DATA__' non trouvée.")

    try:
        json_data = json.loads(script_tag.string)
    except json.JSONDecodeError as exc:  # pragma: no cover - logging context
        raise ValueError("Impossible de décoder le JSON '__NEXT_DATA__'.") from exc

    deals: List[Deal] = []
    for candidate in extract_from_state(json_data):
        deal = build_deal_from_dict(candidate)
        if deal:
            deals.append(deal)

    return deduplicate_deals(deals)


def scrape_store(
    store: Store,
    proxies: List[str],
    *,
    max_retries: int,
    timeout: int,
    delay_range: Tuple[float, float],
) -> List[Deal]:
    page_source = fetch_page(
        store.url,
        proxies,
        max_retries=max_retries,
        timeout=timeout,
        delay_range=delay_range,
    )
    deals = extract_deals_from_html(page_source)
    print(f"✔ {store.ville}: {len(deals)} produits (HTTP)")
    return deals


def run(
    *,
    store_filters: Optional[Set[str]] = None,
    output_dir: Optional[Path] = None,
    aggregated_path: Optional[Path] = None,
    max_retries: int = DEFAULT_MAX_RETRIES,
    timeout: int = DEFAULT_TIMEOUT,
    delay_range: Tuple[float, float] = DEFAULT_DELAY_RANGE,
) -> None:
    proxies = load_proxies()
    stores = load_stores()
    if not stores:
        raise ValueError("Aucun magasin Walmart n'a été configuré.")

    normalized_filters: Set[str] = set()
    if store_filters:
        for item in store_filters:
            normalized_filters.update(normalize_store_token(item))

    if normalized_filters:
        stores = [store for store in stores if store_matches_filters(store, normalized_filters)]
        if not stores:
            raise ValueError("Aucun magasin ne correspond aux filtres fournis.")

    per_store_dir = ensure_output_paths(output_dir)
    aggregated_target = aggregated_path or Path(DEFAULT_AGGREGATED_FILENAME)

    aggregated: List[dict] = []
    processed = 0
    for store in stores:
        try:
            deals = scrape_store(
                store,
                proxies,
                max_retries=max_retries,
                timeout=timeout,
                delay_range=delay_range,
            )
        except Exception as exc:  # noqa: BLE001 - trace par magasin
            print(f"⚠️  {store.ville}: {exc}")
            continue

        payload = [deal.to_payload(store) for deal in deals]
        write_json(per_store_dir / f"{store.slug}.json", payload)
        aggregated.extend(payload)
        processed += 1

    write_json(aggregated_target, aggregated)
    print(
        "🗂️  Export terminé: "
        f"{len(aggregated)} produits sur {processed}/{len(stores)} magasins traités."
    )


def parse_arguments(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Scraper les liquidations Walmart via requêtes HTTP."
    )
    parser.add_argument(
        "--store",
        "-s",
        action="append",
        dest="stores",
        help="Filtrer les magasins par ID, ville ou slug (répétable).",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Dossier de sortie pour les fichiers JSON par magasin (défaut: data/walmart).",
    )
    parser.add_argument(
        "--aggregated-path",
        type=Path,
        default=None,
        help="Chemin du fichier JSON agrégé (défaut: liquidations_walmart_qc.json).",
    )
    parser.add_argument(
        "--max-retries",
        type=int,
        default=DEFAULT_MAX_RETRIES,
        help="Nombre maximum de tentatives par requête HTTP.",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=DEFAULT_TIMEOUT,
        help="Délai maximum (en secondes) pour chaque requête HTTP.",
    )
    parser.add_argument(
        "--min-delay",
        type=float,
        default=DEFAULT_DELAY_RANGE[0],
        help="Delai minimal entre les tentatives (en secondes).",
    )
    parser.add_argument(
        "--max-delay",
        type=float,
        default=DEFAULT_DELAY_RANGE[1],
        help="Delai maximal entre les tentatives (en secondes).",
    )
    return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> None:
    args = parse_arguments(argv)

    if args.min_delay < 0 or args.max_delay < 0:
        raise ValueError("Les délais doivent être positifs.")
    if args.min_delay > args.max_delay:
        raise ValueError("Le délai minimal doit être inférieur ou égal au délai maximal.")

    store_filters = set(args.stores) if args.stores else None
    delay_range = (args.min_delay, args.max_delay)

    run(
        store_filters=store_filters,
        output_dir=args.output_dir,
        aggregated_path=args.aggregated_path,
        max_retries=args.max_retries,
        timeout=args.timeout,
        delay_range=delay_range,
    )


if __name__ == "__main__":
    main()

