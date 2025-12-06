import fs from "fs";
import path from "path";

export type BestBuyRawProduct = {
  title: string;
  url: string;
  price: number | string;
  price_raw?: string;
};

export type Deal = {
  id: string;
  store: "bestbuy";
  title: string;
  productUrl: string;
  currentPrice: number | null;
  originalPrice: number | null;
  discountPercent: number | null;
  imageUrl: string | null;
  city: string | null;
  branchId: string | null;
};

const BESTBUY_JSON_PATH = path.join(
  process.cwd(),
  "outputs",
  "bestbuy",
  "clearance.json"
);

export function readBestBuyDeals(): Deal[] {
  if (!fs.existsSync(BESTBUY_JSON_PATH)) {
    console.warn("[BestBuy] clearance.json not found:", BESTBUY_JSON_PATH);
    return [];
  }

  const raw = fs.readFileSync(BESTBUY_JSON_PATH, "utf8");
  const data = JSON.parse(raw) as BestBuyRawProduct[];

  return data.map((item, index) => {
    const priceNumber =
      typeof item.price === "number"
        ? item.price
        : parseFloat(item.price.replace(/[^0-9.,]/g, "").replace(",", "."));

    return {
      id: `bestbuy-${index}`,
      store: "bestbuy",
      title: item.title,
      productUrl: item.url,
      currentPrice: Number.isFinite(priceNumber) ? priceNumber : null,
      originalPrice: null,
      discountPercent: null, // on pourra calculer le rabais plus tard si on scrape le prix original
      imageUrl: null,        // à remplir quand le scraper aura les images
      city: null,
      branchId: null,
    };
  });
}
