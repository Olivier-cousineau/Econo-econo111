"""Best Buy API scraper script."""
import os
import sys
from typing import Any, Dict, Optional

import requests

BASE_URL = "https://api.bestbuy.com/v1/products"
DEFAULT_PAGE_SIZE = 20


def get_api_key() -> str:
    """Return the Best Buy API key from environment variables.

    Raises:
        RuntimeError: If the API key cannot be found.
    """
    api_key = os.getenv("BESTBUY_API_KEY")
    if not api_key:
        raise RuntimeError(
            "Best Buy API key not found. Set the BESTBUY_API_KEY environment variable."
        )
    return api_key


def get_products(query: str, page: int = 1, page_size: int = DEFAULT_PAGE_SIZE) -> Optional[Dict[str, Any]]:
    """Retrieve products from the Best Buy API that match the search query.

    Args:
        query: Search query (keyword or category).
        page: Page number for pagination.
        page_size: Number of results per page (1-100).

    Returns:
        JSON response as a dictionary if the request succeeds, otherwise ``None``.
    """

    params = {
        "apiKey": get_api_key(),
        "format": "json",
        "pageSize": page_size,
        "page": page,
    }

    url = f"{BASE_URL}(search={query})"
    response = requests.get(url, params=params, timeout=30)

    if response.status_code == requests.codes.ok:
        return response.json()

    print(f"API error {response.status_code}: {response.text}", file=sys.stderr)
    return None


def main() -> None:
    query = sys.argv[1] if len(sys.argv) > 1 else "laptop"
    products = get_products(query)
    if not products:
        print("No products returned.")
        return

    for product in products.get("products", []):
        name = product.get("name", "Unknown product")
        price = product.get("salePrice", "N/A")
        print(f"Name: {name}, Price: {price} USD")


if __name__ == "__main__":
    main()
