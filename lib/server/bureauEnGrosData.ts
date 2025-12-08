// lib/server/bureauEnGrosData.js
import fs from "fs";
import path from "path";

const ROOT_DIR = process.cwd();
const BUREAU_EN_GROS_OUTPUT_DIR = path.join(
  ROOT_DIR,
  "outputs",
  "bureauengros"
);

/**
 * Retourne la liste des slugs disponibles, par ex.:
 * ["124-bureau-en-gros-saint-jerome-qc", "308-bureau-en-gros-boisbriand-qc", ...]
 */
export function listAvailableBureauEnGrosStoreSlugs() {
  if (!fs.existsSync(BUREAU_EN_GROS_OUTPUT_DIR)) {
    return [];
  }

  const entries = fs.readdirSync(BUREAU_EN_GROS_OUTPUT_DIR, {
    withFileTypes: true,
  });

  return entries
    .filter((entry) => entry.isDirectory())
    .map((entry) => entry.name)
    .sort();
}

/**
 * Lit le fichier outputs/bureauengros/<slug>/data.json
 * et renvoie un objet normalisé.
 */
export function readBureauEnGrosStoreData(storeSlug) {
  if (!storeSlug) return null;

  const storeDir = path.join(BUREAU_EN_GROS_OUTPUT_DIR, storeSlug);
  const jsonPath = path.join(storeDir, "data.json");

  if (!fs.existsSync(jsonPath)) {
    // pas de fichier = pas de magasin
    return null;
  }

  try {
    const raw = fs.readFileSync(jsonPath, "utf8");
    const parsed = JSON.parse(raw);

    if (!parsed || typeof parsed !== "object") {
      return null;
    }

    // Si jamais le JSON est directement un tableau de produits
    if (Array.isArray(parsed)) {
      return {
        storeSlug,
        storeId: null,
        storeName: null,
        sourceStore: "bureau-en-gros",
        url: null,
        scrapedAt: null,
        count: parsed.length,
        products: parsed,
      };
    }

    // Si le JSON a déjà la bonne structure (products, store, etc.), on le renvoie tel quel
    return parsed;
  } catch (error) {
    console.error(
      `Failed to read Bureau en Gros store data for slug: ${storeSlug}`,
      error
    );
    return null;
  }
}
