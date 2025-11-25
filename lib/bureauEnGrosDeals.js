import fs from "fs";
import path from "path";

const ROOT_DIR = process.cwd();
const BUREAU_EN_GROS_OUTPUT_DIR = path.join(
  ROOT_DIR,
  "outputs",
  "bureauengros",
);

export function getAllBureauEnGrosStores() {
  if (!fs.existsSync(BUREAU_EN_GROS_OUTPUT_DIR)) {
    console.warn(
      "[BureauEnGros] outputs/bureauengros directory not found:",
      BUREAU_EN_GROS_OUTPUT_DIR,
    );
    return [];
  }

  const entries = fs.readdirSync(BUREAU_EN_GROS_OUTPUT_DIR, {
    withFileTypes: true,
  });

  const stores = [];

  for (const entry of entries) {
    if (!entry.isDirectory()) continue;

    const slug = entry.name; // e.g. "10-bureau-en-gros-greater-sudbury-on"
    const folderPath = path.join(BUREAU_EN_GROS_OUTPUT_DIR, slug);
    const jsonPath = path.join(folderPath, "data.json");

    if (!fs.existsSync(jsonPath)) {
      continue;
    }

    let productCount = 0;
    try {
      const raw = fs.readFileSync(jsonPath, "utf8");
      const parsed = JSON.parse(raw);
      if (Array.isArray(parsed)) {
        productCount = parsed.length;
      }
    } catch (err) {
      console.warn("[BureauEnGros] Failed to read JSON for store:", slug, err);
    }

    const parts = slug.split("-");
    const id = parts[0] ?? slug;

    let cityAndProvince = parts.slice(4).join(" ");
    if (!cityAndProvince) {
      cityAndProvince = slug;
    }

    const label = `Bureau en Gros – ${cityAndProvince.toUpperCase()}`;

    stores.push({
      slug,
      id,
      label,
      jsonPath,
      productCount,
    });
  }

  stores.sort((a, b) => a.id.localeCompare(b.id));

  console.log(
    `[BureauEnGros] Found ${stores.length} store(s) under outputs/bureauengros`,
  );

  return stores;
}

export function getBureauEnGrosStoreBySlug(slug) {
  const stores = getAllBureauEnGrosStores();
  return stores.find((s) => s.slug === slug) ?? null;
}

export function readBureauEnGrosStoreDeals(slug) {
  const store = getBureauEnGrosStoreBySlug(slug);
  if (!store) {
    return null;
  }

  try {
    const raw = fs.readFileSync(store.jsonPath, "utf8");
    const parsed = JSON.parse(raw);
    const products = Array.isArray(parsed) ? parsed : [];
    return { store, products };
  } catch (error) {
    console.error(
      "[BureauEnGros] Failed to read deals for store",
      slug,
      store.jsonPath,
      error,
    );
    return null;
  }
}
