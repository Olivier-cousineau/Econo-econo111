// pages/api/deals.js
import { readBureauEnGrosStoreData } from "../../lib/bureauEngros";

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

/**
 * API route serving clearance deals.
 * Supports Bureau en Gros data stored under outputs/bureauengros/<storeSlug>/data.json.
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
        res.status(404).json({ ok: false, error: "STORE_NOT_FOUND" });
        return;
      }

      const products = Array.isArray(storeData.products)
        ? storeData.products
        : [];

      res.status(200).json({
        ok: true,
        chain: "bureauengros",
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
