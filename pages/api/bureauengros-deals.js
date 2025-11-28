// pages/api/bureauengros-deals.js
import fs from "fs";
import path from "path";

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

  if (Array.isArray(slugCandidate)) {
    return typeof slugCandidate[0] === "string" ? slugCandidate[0].trim() : "";
  }
  return typeof slugCandidate === "string" ? slugCandidate.trim() : "";
}

/**
 * Lit un magasin : /outputs/bureauengros/<storeSlug>/data.json
 */
function readStoreDeals(storeSlug) {
  const filePath = path.join(
    process.cwd(),
    "outputs",
    "bureauengros",
    storeSlug,
    "data.json"
  );

  if (!fs.existsSync(filePath)) {
    return null;
  }

  try {
    const raw = fs.readFileSync(filePath, "utf8");
    const parsed = JSON.parse(raw);
    return parsed && typeof parsed === "object" ? parsed : null;
  } catch (err) {
    console.error(`Failed to read Bureau en Gros deals for ${storeSlug}`, err);
    return null;
  }
}

/**
 * Liste tous les magasins Bureau en Gros à partir de /outputs/bureauengros/
 */
function readAllStoresDeals() {
  const rootDir = path.join(process.cwd(), "outputs", "bureauengros");

  if (!fs.existsSync(rootDir)) {
    return [];
  }

  const entries = fs.readdirSync(rootDir, { withFileTypes: true });
  const stores = [];

  for (const entry of entries) {
    if (!entry.isDirectory()) continue;

    const storeSlug = entry.name;
    const data = readStoreDeals(storeSlug);
    if (!data) continue;

    const products = Array.isArray(data.products) ? data.products : [];
    const count =
      typeof data.count === "number" ? data.count : products.length;

    stores.push({
      storeSlug,
      storeId: data.storeId ?? null,
      storeName: data.storeName ?? null,
      sourceStore: data.sourceStore ?? null,
      url: data.url ?? null,
      scrapedAt: data.scrapedAt ?? null,
      count,
    });
  }

  return stores;
}

export default function handler(req, res) {
  if (req.method !== "GET") {
    res.setHeader("Allow", "GET");
    return res.status(405).json({ ok: false, error: "METHOD_NOT_ALLOWED" });
  }

  const storeSlug = getStoreSlug(req.query);

  // 1) SANS storeSlug → renvoie la liste des magasins + count
  if (!storeSlug) {
    const stores = readAllStoresDeals();
    return res.status(200).json({
      ok: true,
      chain: "bureauengros",
      mode: "all-stores",
      stores,
    });
  }

  // 2) AVEC storeSlug → renvoie les produits du magasin
  const data = readStoreDeals(storeSlug);
  if (!data) {
    return res.status(404).json({
      ok: false,
      error: "STORE_NOT_FOUND",
      chain: "bureauengros",
      storeSlug,
    });
  }

  const products = Array.isArray(data.products) ? data.products : [];
  const count =
    typeof data.count === "number" ? data.count : products.length;

  return res.status(200).json({
    ok: true,
    chain: "bureauengros",
    mode: "single-store",
    storeSlug,
    storeId: data.storeId ?? null,
    storeName: data.storeName ?? null,
    sourceStore: data.sourceStore ?? null,
    url: data.url ?? null,
    scrapedAt: data.scrapedAt ?? null,
    count,
    products,
  });
}
