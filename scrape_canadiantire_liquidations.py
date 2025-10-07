"""Command-line helper to scrape Canadian Tire clearance deals.

This script is a thin wrapper around :mod:`incoming.canadian_tire_scraper` that
loads the list of stores from ``data/canadian-tire/stores.json`` and exports a
command line tailored for quick usage.
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Optional, Sequence, Tuple

from incoming import canadian_tire_scraper


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Extraction des aubaines en liquidation de Canadian Tire.",
    )
    parser.add_argument(
        "--store",
        action="append",
        dest="stores",
        default=[],
        help="Filtre les magasins (ID, ville, surnom ou slug).",
    )
    parser.add_argument(
        "--language",
        choices=("fr", "en"),
        default=canadian_tire_scraper.DEFAULT_LANGUAGE,
        help="Langue des pages magasin à interroger (fr ou en).",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Dossier de sortie pour les fichiers JSON par magasin.",
    )
    parser.add_argument(
        "--aggregated-path",
        type=Path,
        default=None,
        help=(
            "Chemin du fichier d'agrégation global. Défaut : "
            f"{canadian_tire_scraper.DEFAULT_AGGREGATED_FILENAME}."
        ),
    )
    parser.add_argument(
        "--max-retries",
        type=int,
        default=canadian_tire_scraper.DEFAULT_MAX_RETRIES,
        help="Nombre maximal de tentatives HTTP par page.",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=canadian_tire_scraper.DEFAULT_TIMEOUT,
        help="Délai (secondes) alloué à chaque requête HTTP.",
    )
    parser.add_argument(
        "--delay",
        nargs=2,
        type=float,
        metavar=("MIN", "MAX"),
        default=None,
        help=(
            "Intervalle (secondes) utilisé pour les pauses entre les tentatives. "
            f"Défaut : {canadian_tire_scraper.DEFAULT_DELAY_RANGE[0]} "
            f"{canadian_tire_scraper.DEFAULT_DELAY_RANGE[1]}."
        ),
    )
    return parser


def main(argv: Optional[Sequence[str]] = None) -> None:
    args = build_parser().parse_args(argv)
    delay_range: Tuple[float, float]
    if args.delay:
        delay_range = (float(args.delay[0]), float(args.delay[1]))
    else:
        delay_range = canadian_tire_scraper.DEFAULT_DELAY_RANGE

    canadian_tire_scraper.run(
        store_filters=args.stores,
        language=args.language,
        output_dir=args.output_dir,
        aggregated_path=args.aggregated_path,
        max_retries=args.max_retries,
        timeout=args.timeout,
        delay_range=delay_range,
    )


if __name__ == "__main__":
    main()
