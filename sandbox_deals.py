"""Fetch fake Amazon deals using the Product Advertising API v5 sandbox."""
import json
from pathlib import Path

import paapi5_python_sdk
from paapi5_python_sdk.api.default_api import DefaultApi
from paapi5_python_sdk.models.search_items_request import SearchItemsRequest
from paapi5_python_sdk.models.search_items_resource import SearchItemsResource
from paapi5_python_sdk.rest import ApiException


def fetch_fake_deals(
    *,
    access_key: str,
    secret_key: str,
    partner_tag: str,
    region: str = "us-east-1",
    host: str = "webservices.amazon.com",
    marketplace: str = "www.amazon.com",
    keywords: str = "Harry Potter",
    output_path: Path | None = None,
) -> list[dict[str, str | None]]:
    """Fetch mock deals from the PAAPI sandbox and persist them to ``output_path``.

    Parameters
    ----------
    access_key, secret_key, partner_tag
        Your Amazon Associates sandbox credentials.
    region, host, marketplace
        Connection settings for the sandbox API.
    keywords
        Keyword search term supported by the sandbox.
    output_path
        Optional custom destination for the generated JSON file. When omitted,
        ``data/fake_amazon_deals.json`` is used.
    """

    configuration = paapi5_python_sdk.Configuration(
        access_key=access_key,
        secret_key=secret_key,
        host=host,
        region=region,
    )

    api_instance = DefaultApi(paapi5_python_sdk.ApiClient(configuration))

    request = SearchItemsRequest(
        partner_tag=partner_tag,
        partner_type="Associates",
        keywords=keywords,
        marketplace=marketplace,
        resources=[
            SearchItemsResource.ITEMINFO_TITLE,
            SearchItemsResource.IMAGES_PRIMARY_LARGE,
            SearchItemsResource.OFFERS_LISTINGS_PRICE,
        ],
    )

    if output_path is None:
        output_path = Path("data") / "fake_amazon_deals.json"

    try:
        response = api_instance.search_items(request, sandbox=True)
    except ApiException as exc:  # pragma: no cover - relies on external API
        raise RuntimeError("Failed to query PAAPI sandbox") from exc

    fake_deals: list[dict[str, str | None]] = []

    if response.search_result and response.search_result.items:
        for item in response.search_result.items:
            title = None
            if item.item_info and item.item_info.title:
                title = item.item_info.title.display_value

            image = None
            if item.images and item.images.primary and item.images.primary.large:
                image = item.images.primary.large.url

            price = "N/A"
            if item.offers and item.offers.listings:
                listing = item.offers.listings[0]
                if listing.price:
                    price = listing.price.display_amount

            fake_deals.append(
                {
                    "title": title,
                    "image": image,
                    "price": price,
                    "url": item.detail_page_url,
                }
            )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as file:
        json.dump(fake_deals, file, indent=2)

    return fake_deals


def main() -> None:
    """Entry point for running the script as a module."""

    access_key = "YOUR_ACCESS_KEY"
    secret_key = "YOUR_SECRET_KEY"
    partner_tag = "YOUR_ASSOCIATE_TAG"

    fake_deals = fetch_fake_deals(
        access_key=access_key,
        secret_key=secret_key,
        partner_tag=partner_tag,
    )

    print("✅ Fake deals saved to data/fake_amazon_deals.json")
    print(json.dumps(fake_deals, indent=2))


if __name__ == "__main__":
    main()
