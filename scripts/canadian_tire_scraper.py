#!/usr/bin/env python3
"""Helper CLI to run the Canadian Tire scraper with sensible defaults."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

DEFAULT_STORE = "0271"
DEFAULT_MAX_PAGES = 125
DEFAULT_OUT_PATH = Path("data/canadian-tire/saint-jerome.json")
URL_TEMPLATE = "https://www.canadiantire.ca/fr/promotions/liquidation.html?store={store}"


def _build_url(store: str) -> str:
    store_id = str(store).strip()
    if not store_id:
        raise ValueError("store must not be empty")
    return URL_TEMPLATE.format(store=store_id)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the Canadian Tire scraper")
    parser.add_argument("--store", default=DEFAULT_STORE, help="Store identifier (e.g. 0271)")
    parser.add_argument("--url", help="Override the automatically generated liquidation URL")
    parser.add_argument(
        "--max-pages",
        type=int,
        default=DEFAULT_MAX_PAGES,
        help="Maximum number of pages to crawl",
        dest="max_pages",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=DEFAULT_OUT_PATH,
        help="Destination JSON file for the scraped data",
    )
    parser.add_argument(
        "--images-dir",
        type=Path,
        help="Optional directory where images should be downloaded",
        dest="images_dir",
    )
    parser.add_argument(
        "--csv",
        type=Path,
        help="Optional CSV output path; defaults to the JSON path with .csv extension",
    )
    parser.add_argument(
        "--headful",
        action="store_true",
        help="Run the browser in headful mode (useful for debugging)",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    repo_root = Path(__file__).resolve().parents[1]
    script_path = repo_root / "scrape.js"
    if not script_path.exists():
        raise FileNotFoundError(f"Unable to locate scraper script: {script_path}")

    url = args.url or _build_url(args.store)
    out_path: Path = args.out
    out_path.parent.mkdir(parents=True, exist_ok=True)

    command = [
        "node",
        str(script_path),
        "--url",
        url,
        "--maxPages",
        str(args.max_pages),
        "--out",
        str(out_path),
    ]

    if args.images_dir is not None:
        command.extend(["--imagesDir", str(args.images_dir)])
    if args.csv is not None:
        command.extend(["--outCsv", str(args.csv)])
    if args.headful:
        command.append("--headful")

    process = subprocess.run(command, cwd=repo_root)
    return process.returncode


if __name__ == "__main__":
    sys.exit(main())
