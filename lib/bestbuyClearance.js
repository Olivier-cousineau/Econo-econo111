import fs from "fs";
import path from "path";

const clearancePath = path.join(
  process.cwd(),
  "outputs",
  "bestbuy",
  "clearance.json"
);

function normalizePrice(item) {
  if (typeof item.price === "number") {
    return item.price;
  }

  if (typeof item.price_raw === "string") {
    const numeric = parseFloat(item.price_raw.replace(/[^0-9.]/g, ""));
    return Number.isFinite(numeric) ? numeric : null;
  }

  return null;
}

export function readBestBuyClearanceDeals() {
  try {
    const content = fs.readFileSync(clearancePath, "utf8");
    const data = JSON.parse(content);

    if (!Array.isArray(data)) {
      return [];
    }

    return data.map((item, index) => ({
      title:
        typeof item.title === "string" && item.title.trim()
          ? item.title.trim()
          : `Produit ${index + 1}`,
      url: typeof item.url === "string" ? item.url : "",
      price: normalizePrice(item),
      priceRaw: typeof item.price_raw === "string" ? item.price_raw : "",
    }));
  } catch (error) {
    console.error("Failed to read Best Buy clearance deals", error);
    return [];
  }
}
