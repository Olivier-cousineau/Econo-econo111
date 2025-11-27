import fs from "fs";
import path from "path";

const ROOT_DIR = process.cwd();
const BUREAU_EN_GROS_OUTPUT_DIR = path.join(
  ROOT_DIR,
  "outputs",
  "bureauengros"
);

/**
 * Normalise un paramètre de query (string ou tableau)
 */
function normalizeQueryParam(value) {
  if (Array.isArray(value)) {
    return typeof value[0] === "string" ? value[0].trim() : "";
  }
  return typeof value === "string" ? value.trim() : "";
}

/**
 * Essaie de retrouver le bon dossier magasin à partir d'un "slug"
 * - d'abord on teste un match direct
 * - sinon on teste les dossiers qui se terminent par ce slug
 *   (ex: slug = "bureau-en-gros-alma-qc"
 *        dossier = "182-bureau-en-gros-alma-qc")
 */
function findStoreJsonPathForSlug(slug) {
  if (!slug) return null;

  // 1) chemin direct
  let jsonPath = path.join(
    BUREAU_EN_GROS_OUTPUT_DIR,
    slug,
    "data.json"
  );
  if (fs.existsSync(jsonPath)) {
    return jsonPath;
  }

  // 2) on tente de trouver un dossier qui se termine par le slug
  try {
    const entries = fs.readdirSync(BUREAU_EN_GROS_OUTPUT_DIR, {
      withFileTypes: true,
    });

    const match = entries.find(
      (entry) =>
        entry.isDirectory() &&
        (entry.name === slug || entry.name.endsWith(slug))
    );

    if (!match) {
      return null;
    }

    jsonPath = path.join(
      BUREAU_EN_GROS_OUTPUT_DIR,
      match.name,
      "data.json"
    );

    return fs.existsSync(jsonPath) ? jsonPath : null;
  } catch (err) {
    console.error(
      "Error while trying to resolve Bureau en Gros store slug:",
      slug,
      err
    );
    return null;
  }
}

/**
 * Lit les deals pour un magasin Bureau en Gros à partir du slug
 */
function readBureauEnGrosStoreDeals(storeSlug) {
  const jsonPath = findStoreJsonPathForSlug(storeSlug);

  if (!jsonPath) {
    return null;
  }

  try {
    const raw = fs.readFileSync(jsonPath, "utf8");
    const parsed = JSON.parse(raw);
    return parsed && typeof parsed === "object" ? parsed : null;
  } catch (error) {
    console.error(
      `Failed to read Bureau en Gros deals for slug: ${storeSlug}`,
      error
    );
    return null;
  }
}

/**
 * Récupère le slug de magasin à partir de plusieurs possibles paramètres
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

export default async function handler(req, res) {
  if (req.method !== "GET") {
    res.setHeader("Allow", "GET");
    res.status(405).json({ error: "Method not allowed" });
    return;
  }

  const retailer = normalizeQueryParam(req.query.retailer).toLowerCase();
  const storeSlug = getStoreSlug(req.query);

  if (!retailer) {
    res.status(400).json({ error: "Missing retailer" });
    return;
  }

  if (retailer === "bureauengros" || retailer === "bureau-en-gros") {
    if (!storeSlug) {
      res.status(400).json({ error: "Missing store slug" });
      return;
    }

    try {
      const data = readBureauEnGrosStoreDeals(storeSlug);

      if (!data) {
        res
          .status(404)
          .json({ error: "Store not found or unavailable", storeSlug });
        return;
      }

      const storeMeta = data.store || {};
      const products = Array.isArray(data.products) ? data.products : [];

      // On retourne un format très riche pour être compatible
      res.status(200).json({
        retailer: "bureau-en-gros",
        storeSlug,
        store: {
          id: storeMeta.id ?? null,
          name: storeMeta.name ?? "",
          address: storeMeta.address ?? "",
        },
        products,
        // champs supplémentaires pour le front
        deals: products,
        items: products,
        count: products.length,
      });
    } catch (error) {
      console.error(
        "Failed to load Bureau en Gros deals via generic API",
        error
      );
      res.status(500).json({ error: "Unable to load store data" });
    }
    return;
  }

  res.status(400).json({ error: `Unsupported retailer: ${retailer}` });
}
