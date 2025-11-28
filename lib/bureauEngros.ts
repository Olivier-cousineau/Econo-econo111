import fs from "fs";
import path from "path";
import branches from "../data/bureauengros/branches.json";

const ROOT_DIR = process.cwd();

// 🔹 Fichier source unique : Saint-Jérôme
const BUREAU_EN_GROS_SOURCE_FILE = path.join(
  ROOT_DIR,
  "data",
  "bureauengros",
  "saint-jerome.json"
);

type Branch = {
  id: string;
  name: string;
  address?: string;
  store?: string;
};

export type BureauEnGrosStore = {
  id: string;
  slug: string;
  name: string;
  city: string;
  address: string;
  store?: string;
};

export type BureauEnGrosDeal = {
  title?: string;
  name?: string;
  productName?: string;
  productUrl?: string;
  url?: string;
  link?: string;
  currentPrice?: number;
  originalPrice?: number;
  discountPercent?: number;
  imageUrl?: string;
  image?: string;
  [key: string]: any;
};

type SourceFileShape = {
  store?: {
    id?: string;
    name?: string;
    address?: string;
    store?: string;
  };
  url?: string;
  count?: number;
  products?: BureauEnGrosDeal[];
};

/**
 * Slug helper – compatible ES5 (pas de \p{Diacritic})
 */
function slugify(value: string): string {
  return value
    .normalize("NFD")
    // remove accents
    .replace(/[\u0300-\u036f]/g, "")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/(^-|-$)/g, "");
}

function branchToStore(branch: Branch): BureauEnGrosStore {
  const cityLabel = branch.name.split("–")[1]?.trim() ?? branch.name;
  const slug = `${branch.id}-${slugify(branch.name)}`;

  return {
    id: branch.id,
    slug,
    name: branch.name,
    city: cityLabel,
    address: branch.address ?? "",
    store: branch.store,
  };
}

const BUREAU_EN_GROS_STORES: BureauEnGrosStore[] = (branches as Branch[]).map(
  branchToStore
);

export function getBureauEnGrosStores(): BureauEnGrosStore[] {
  return BUREAU_EN_GROS_STORES;
}

export function getBureauEnGrosStoreBySlug(
  slug: string
): BureauEnGrosStore | undefined {
  return BUREAU_EN_GROS_STORES.find((s) => s.slug === slug);
}

/**
 * Lit le fichier saint-jerome.json et renvoie la liste de produits.
 */
export function readBureauEnGrosDealsForAllStores(): BureauEnGrosDeal[] {
  if (!fs.existsSync(BUREAU_EN_GROS_SOURCE_FILE)) {
    console.error("Bureau en Gros source file not found:", BUREAU_EN_GROS_SOURCE_FILE);
    return [];
  }

  try {
    const raw = fs.readFileSync(BUREAU_EN_GROS_SOURCE_FILE, "utf8");
    const parsed = JSON.parse(raw) as SourceFileShape | BureauEnGrosDeal[];

    // format: { store: {...}, products: [...] }
    if (!Array.isArray(parsed) && Array.isArray(parsed.products)) {
      return parsed.products;
    }

    // format: [ {...}, {...} ]
    if (Array.isArray(parsed)) {
      return parsed;
    }

    return [];
  } catch (err) {
    console.error("Failed to read Bureau en Gros deals JSON:", err);
    return [];
  }
}

/**
 * Pour l’instant: même deals pour tous les magasins.
 */
export function readBureauEnGrosDealsForStore(
  _storeSlug: string
): BureauEnGrosDeal[] {
  return readBureauEnGrosDealsForAllStores();
}
