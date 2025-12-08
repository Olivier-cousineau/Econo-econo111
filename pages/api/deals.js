// pages/api/deals.js
import { readBureauEnGrosStoreData } from "../../lib/server/bureauEnGrosData";
import { readBestBuyDeals } from "../../lib/bestbuy";

/**
 * Normalizes query parameters that may arrive as string or array.
 * @param {string|string[]} value
 * @returns {string}
 */
function normalizeQueryParam(value) {
  if (Array.isArray(value)) {
    return typeof value[0] === "string" ? value[0].trim() : "";
  }
  return typeof value === "string" ? value.trim() : "";
}

/**
 * Extracts the store slug from multiple possible query aliases.
 * @param {Record<string, any>} query
 * @returns {string}
 */
function getStoreSlug(query) {
  const slugCandidate =
    query.storeSlug ??
    query.slug ??
    query.branchSlug ??
    query.branch ??
    query.store ??
    query.storeId ??
    query.branchId ??
    query.id;

  return normalizeQueryParam(slugCandidate);
}

function formatStoreLabel(slug) {
  return slug ? slug.replace(/-/g, " ") : "";
}

function slugify(value) {
  if (value === undefined || value === null) return "";
  const text = String(value)
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "");
  return text
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .replace(/--+/g, "-");
}

function normalizeBestBuyDeals(rawDeals = []) {
  const storeName = "Best Buy";
  const storeSlug = "best-buy";

  return rawDeals.map((deal, index) => {
    const id = deal?.id ?? `bestbuy-${index}`;
    const city = deal?.city?.trim() || "En ligne (Canada)";
    const branchSlug = deal?.branchId
      ? slugify(deal.branchId)
      : slugify(city) || storeSlug;

    const parsedCurrent =
      typeof deal?.currentPrice === "number" && Number.isFinite(deal.currentPrice)
        ? deal.currentPrice
        : typeof deal?.price === "number" && Number.isFinite(deal.price)
          ? deal.price
          : null;

    const parsedOriginal =
      typeof deal?.originalPrice === "number" && Number.isFinite(deal.originalPrice)
        ? deal.originalPrice
        : null;

    const discount =
      typeof deal?.discountPercent === "number" && Number.isFinite(deal.discountPercent)
        ? deal.discountPercent
        : 0;

    return {
      ...deal,
      id,
      store: storeName,
      storeSlug,
      retailer: "bestbuy",
      branch: city,
      branchSlug,
      city,
      citySlug: slugify(city),
      productUrl: deal?.productUrl ?? deal?.url ?? "",
      url: deal?.productUrl ?? deal?.url ?? "",
      currentPrice: parsedCurrent,
      originalPrice: parsedOriginal,
      discountPercent: discount,
      image: deal?.imageUrl ?? deal?.image ?? null,
      imageUrl: deal?.imageUrl ?? deal?.image ?? null,
    };
  });
}

/**
 * API route serving clearance deals.
 * Supports Bureau en Gros data stored under public/bureau-en-gros/<storeSlug>/data.json.
 */
export default async function handler(req, res) {
  if (req.method !== "GET") {
    res.status(405).json({ error: "Method not allowed" });
    return;
  }

  const chain = normalizeQueryParam(
    req.query.chain ?? req.query.retailer ?? req.query.store
  ).toLowerCase();
  const storeSlug = getStoreSlug(req.query);
  const normalizedStore = slugify(storeSlug);

  const isBestBuyRequest =
    chain === "bestbuy" ||
    chain === "best-buy" ||
    normalizedStore === "bestbuy" ||
    normalizedStore === "best-buy";

  if (isBestBuyRequest || (!chain && !normalizedStore)) {
    const deals = normalizeBestBuyDeals(readBestBuyDeals());
    res.status(200).json({
      ok: true,
      chain: "bestbuy",
      storeSlug: "best-buy",
      storeName: "Best Buy",
      count: deals.length,
      deals,
      items: deals,
      products: deals,
    });
    return;
  }

  if (!chain) {
    res.status(400).json({ error: "Missing retailer" });
    return;
  }

  // 🔹 Branche Bureau en Gros
  if (chain === "bureauengros" || chain === "bureau-en-gros") {
    if (!storeSlug) {
      res.status(400).json({ error: "Missing store slug" });
      return;
    }

    try {
      const storeData = readBureauEnGrosStoreData(storeSlug);

      if (!storeData) {
        res.status(200).json({
          ok: false,
          error: "STORE_NOT_FOUND",
          chain: "bureau-en-gros",
          mode: "single-store",
          storeSlug,
          storeId: null,
          storeName: null,
          sourceStore: null,
          url: null,
          scrapedAt: null,
          count: 0,
          products: [],
        });
        return;
      }

      const products = Array.isArray(storeData.products)
        ? storeData.products
        : [];

      res.status(200).json({
        ok: true,
        chain: "bureau-en-gros",
        storeSlug,
        count: typeof storeData.count === "number" ? storeData.count : products.length,
        storeId: storeData.storeId ?? storeData.store?.id ?? "",
        storeName:
          storeData.storeName ??
          storeData.store?.name ??
          formatStoreLabel(storeSlug),
        sourceStore: storeData.sourceStore ?? "",
        url: storeData.url ?? "",
        scrapedAt: storeData.scrapedAt ?? "",
        products,
        deals: products,
        items: products,
      });
    } catch (error) {
      console.error("Failed to load Bureau en Gros store via API", error);
      res.status(500).json({ error: "Unable to load store data" });
    }
    return;
  }

  // Autres détaillants pas encore gérés
  res.status(400).json({ error: `Unsupported retailer: ${chain}` });
}
