import asyncio
import os
import re
import time
from pathlib import Path
from typing import Dict, List, Optional

from playwright.async_api import async_playwright, TimeoutError as PWTimeout
from bs4 import BeautifulSoup
import pandas as pd

# == CONFIG ==
BASE_LIQUIDATION_URL = os.getenv(
    "LIQUIDATION_URL", "https://www.canadiantire.ca/fr/promotions/liquidation.html"
)
STORE_ID = os.getenv("STORE_ID", "271")


def build_liquidation_url(base_url: str, store_id: Optional[str]) -> str:
    if "store=" in base_url:
        return base_url
    if not store_id:
        return base_url
    separator = "&" if "?" in base_url else "?"
    return f"{base_url}{separator}store={store_id}"


LIQUIDATION_URL_WITH_STORE = build_liquidation_url(BASE_LIQUIDATION_URL, STORE_ID)

HEADLESS = True
MAX_PAGING = 20  # safety cap for "Charger plus"

OUTPUT_CSV = "liquidation_st_jerome.csv"
OUTPUT_HTML = "preview.html"
DEBUG_HTML = "debug_last_response.html"

OUTPUT_COLUMNS = [
    "product_name",
    "image_url",
    "original_price",
    "discount_price",
    "availability",
    "product_link",
    "sku",
]


# == HELPERS ==
def env_proxy_list() -> List[Dict[str, Optional[str]]]:
    p1 = os.getenv("PROXY1_SERVER")
    p2 = os.getenv("PROXY2_SERVER")
    user = os.getenv("PROXY_USERNAME")
    pwd = os.getenv("PROXY_PASSWORD")

    proxies: List[Dict[str, Optional[str]]] = []
    for server in (p1, p2):
        if server:
            proxies.append({"server": server, "username": user, "password": pwd})
    return proxies


def proxy_label(proxy: Optional[Dict[str, Optional[str]]]) -> str:
    if isinstance(proxy, dict):
        return proxy.get("server", "<proxy>") or "<proxy>"
    return "<direct>"


def proxies_to_cycle() -> List[Optional[Dict[str, Optional[str]]]]:
    proxies = env_proxy_list()
    if proxies:
        print(f"Configured {len(proxies)} proxy endpoint(s).")
        proxies.append(None)
        return proxies
    print("No proxy secrets detected; attempting direct connection only.")
    return [None]


PROXIES = proxies_to_cycle()


def clean_price(text: str) -> Optional[float]:
    if not text:
        return None
    text = text.replace("\xa0", " ").strip()
    m = re.search(r"([\d\.,]+)", text)
    if not m:
        return None
    num = m.group(1).replace(",", "").replace(" ", "")
    try:
        return float(num)
    except Exception:
        return None


def extract_sku_from_link(link: str) -> Optional[str]:
    if not link:
        return None
    m = re.search(r"/(\d+)(?:$|[/?])", link)
    if m:
        return m.group(1)
    m2 = re.search(r"(\d{4,})", link)
    return m2.group(1) if m2 else None


# == SCRAPER ==
async def try_with_proxies(action_fn, proxies: List[Optional[Dict[str, Optional[str]]]]):
    last_exc = None
    for p in proxies:
        try:
            return await action_fn(p)
        except Exception as e:
            print(f"[proxy error] proxy {proxy_label(p)} failed: {e}")
            last_exc = e
            time.sleep(1)
    raise last_exc


async def fetch_and_extract(proxy: Optional[Dict[str, Optional[str]]]):
    print(f"Launching browser with proxy {proxy_label(proxy)}")
    async with async_playwright() as p:
        launch_kwargs = {"headless": HEADLESS}
        if proxy:
            launch_kwargs["proxy"] = proxy  # type: ignore

        browser = await p.chromium.launch(**launch_kwargs)
        context = await browser.new_context(locale="fr-CA")
        page = await context.new_page()

        try:
            await page.goto(LIQUIDATION_URL_WITH_STORE, timeout=120000)
            await page.wait_for_load_state("networkidle", timeout=60000)
        except PWTimeout as e:
            html = await page.content()
            Path(DEBUG_HTML).write_text(html, encoding="utf-8")
            await browser.close()
            raise RuntimeError("Initial page load timed out; debug HTML saved.") from e

        # Cookie / popup cleanup
        try:
            for sel in [
                "button:has-text('Accepter')",
                "button:has-text('OK')",
                "button[aria-label='close']",
            ]:
                if await page.locator(sel).count() > 0:
                    try:
                        await page.locator(sel).first.click(timeout=3000)
                    except Exception:
                        pass
        except Exception:
            pass

        # Pagination / "Charger plus"
        page_num = 0
        while page_num < MAX_PAGING:
            page_num += 1
            print("Page batch:", page_num)
            await page.wait_for_timeout(1500)
            clicked = False
            try:
                btn_selectors = [
                    "button:has-text('Charger plus')",
                    "button:has-text('Afficher plus')",
                    "button:has-text('Show more')",
                    "button.load-more",
                    "button[data-testid='load-more']",
                ]
                for sel in btn_selectors:
                    locator = page.locator(sel)
                    if await locator.count() > 0 and await locator.is_visible():
                        try:
                            await locator.first.click()
                            clicked = True
                            await page.wait_for_load_state("networkidle", timeout=60000)
                            await page.wait_for_timeout(1000)
                            break
                        except Exception:
                            try:
                                await page.eval_on_selector(sel, "el => el.click()")
                                clicked = True
                                await page.wait_for_load_state("networkidle", timeout=60000)
                                await page.wait_for_timeout(1000)
                                break
                            except Exception:
                                pass
            except Exception:
                pass

            if not clicked:
                await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                await page.wait_for_timeout(1200)
                found_any = False
                for sel in [
                    "button:has-text('Charger plus')",
                    "button:has-text('Afficher plus')",
                    "button:has-text('Show more')",
                ]:
                    if await page.locator(sel).count() > 0:
                        found_any = True
                if not found_any:
                    print("No more 'Charger plus' found — stopping pagination.")
                    break

        html = await page.content()
        Path(OUTPUT_HTML).write_text(html, encoding="utf-8")

        soup = BeautifulSoup(html, "lxml")

        product_elements = soup.select("div.product-tile, div.product-card, li.product")
        if not product_elements:
            product_elements = soup.select("a[href*='/produit/']")
            print(f"Fallback: {len(product_elements)} elements found")

        results = []
        for el in product_elements:
            try:
                link_tag = el.find("a", href=True)
                link = ""
                if link_tag:
                    link = (
                        "https://www.canadiantire.ca" + link_tag.get("href")
                        if link_tag.get("href").startswith("/")
                        else link_tag.get("href")
                    )
                elif el.name == "a" and el.get("href"):
                    link = (
                        "https://www.canadiantire.ca" + el.get("href")
                        if el.get("href").startswith("/")
                        else el.get("href")
                    )

                title_tag = el.find(["h2", "h3", "h4", "span"])
                title = title_tag.get_text(strip=True) if title_tag else ""

                img_tag = el.find("img")
                img_src = (
                    img_tag.get("data-src")
                    or img_tag.get("src")
                    if img_tag
                    else None
                )

                price_tags = el.select("[class*='price'], [data-test*='price']")
                price_text = " ".join(
                    [t.get_text(" ", strip=True) for t in price_tags]
                )
                prices = re.findall(r"\$[\s]*[\d\.,]+", price_text)
                orig_price = clean_price(prices[0]) if len(prices) >= 2 else ""
                sale_price = clean_price(prices[-1]) if prices else ""

                availability = ""
                avail_tag = el.find(
                    lambda t: t.name in ["span", "div", "p"]
                    and ("En stock" in t.get_text() or "En rupture" in t.get_text())
                )
                if avail_tag:
                    availability = avail_tag.get_text(" ", strip=True)

                sku = extract_sku_from_link(link)

                results.append(
                    {
                        "product_name": title,
                        "image_url": img_src,
                        "original_price": orig_price,
                        "discount_price": sale_price,
                        "availability": availability,
                        "product_link": link,
                        "sku": sku,
                    }
                )
            except Exception as e:
                print("Parse error:", e)
                continue

        await browser.close()
        return results


async def main():
    print("Starting scrape (Canadian Tire - Saint-Jérôme) ...")
    try:
        results = await try_with_proxies(fetch_and_extract, PROXIES)
    except Exception as exc:
        print(f"Scraper failed after exhausting proxies: {exc}")
        df = pd.DataFrame(columns=OUTPUT_COLUMNS)
        df.to_csv(OUTPUT_CSV, index=False, encoding="utf-8-sig")
        return

    df = pd.DataFrame(results, columns=OUTPUT_COLUMNS)
    df.to_csv(OUTPUT_CSV, index=False, encoding="utf-8-sig")
    print(f"✅ Saved {len(df)} rows to {OUTPUT_CSV}")
    print(f"📄 Saved full page preview to {OUTPUT_HTML}")


if __name__ == "__main__":
    asyncio.run(main())
