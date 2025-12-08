import {
  listAvailableBureauEnGrosStoreSlugs,
  readBureauEnGrosStoreData,
} from "../../lib/server/bureauEnGrosData";

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

export default function handler(req, res) {
  if (req.method !== "GET") {
    res.setHeader("Allow", "GET");
    return res.status(405).json({ ok: false, error: "METHOD_NOT_ALLOWED" });
  }

  const storeSlug = getStoreSlug(req.query);

  if (!storeSlug) {
    const slugs = listAvailableBureauEnGrosStoreSlugs();
    const stores = slugs
      .map((slug) => ({ slug, data: readBureauEnGrosStoreData(slug) }))
      .filter(({ data }) => Boolean(data))
      .map(({ slug, data }) => {
        const products = Array.isArray(data.products) ? data.products : [];
        const count = typeof data.count === "number" ? data.count : products.length;

        return {
          storeSlug: data.store?.slug ?? slug,
          storeId: data.storeId ?? data.store?.id ?? null,
          storeName: data.storeName ?? data.store?.name ?? null,
          sourceStore: data.sourceStore ?? null,
          url: data.url ?? null,
          scrapedAt: data.scrapedAt ?? null,
          count,
          products,
        };
      });

    return res.status(200).json({
      ok: true,
      chain: "bureau-en-gros",
      mode: "all-stores",
      stores,
    });
  }

  const data = readBureauEnGrosStoreData(storeSlug);
  if (!data) {
    return res.status(200).json({
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
  }

  const products = Array.isArray(data.products) ? data.products : [];
  const count = typeof data.count === "number" ? data.count : products.length;

  return res.status(200).json({
    ok: true,
    chain: "bureau-en-gros",
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
