// pages/api/deals.js
import {
  getBureauEnGrosStores,
  readBureauEnGrosDealsForAllStores,
} from "../../lib/bureauEngros";

function normalizeQueryParam(value) {
  if (Array.isArray(value)) {
    return typeof value[0] === "string" ? value[0].trim() : "";
  }
  return typeof value === "string" ? value.trim() : "";
}

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

export default async function handler(req, res) {
  if (req.method !== "GET") {
    res.status(405).json({ error: "Method not allowed" });
    return;
  }

  const retailer = normalizeQueryParam(req.query.retailer).toLowerCase();
  const storeSlug = getStoreSlug(req.query);

  if (!retailer) {
    res.status(400).json({ error: "Missing retailer" });
    return;
  }

  // 🔹 Branche Bureau en Gros
  if (retailer === "bureauengros" || retailer === "bureau-en-gros") {
    if (!storeSlug) {
      res.status(400).json({ error: "Missing store slug" });
      return;
    }

    try {
      const stores = getBureauEnGrosStores();
      const storeMetadata = stores.find((store) => store.slug === storeSlug);

      if (!storeMetadata) {
        res
          .status(404)
          .json({ error: "Store not found or unavailable", storeSlug });
        return;
      }

      // 🔥 Ici on lit vraiment les deals depuis saint-jerome.json
      const products = readBureauEnGrosDealsForAllStores();

      if (!products || products.length === 0) {
        res.status(404).json({
          error: "No deals available right now",
          storeSlug,
        });
        return;
      }

      res.status(200).json({
        retailer: "bureau-en-gros",
        storeSlug,
        store: {
          id: storeMetadata.id,
          name: storeMetadata.name || formatStoreLabel(storeSlug),
          address: storeMetadata.address || "",
        },
        products,
        deals: products,
        items: products,
        count: products.length,
      });
    } catch (error) {
      console.error("Failed to load Bureau en Gros store via API", error);
      res.status(500).json({ error: "Unable to load store data" });
    }
    return;
  }

  // Autres détaillants pas encore gérés
  res.status(400).json({ error: `Unsupported retailer: ${retailer}` });
}
