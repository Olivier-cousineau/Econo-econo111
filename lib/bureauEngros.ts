import fs from "fs";
import path from "path";
import branches from "../data/bureauengros/branches.json";

const ROOT_DIR = process.cwd();

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

type StoreFile = {
  store?: {
    id?: string;
    name?: string;
    address?: string;
    store?: string;
  };
  products?: BureauEnGrosDeal[];
};

/**
 * Slugify helper – must match the scraper convention
 */
function slugify(value: string): string {
  return value
    .normalize("NFD")
    // Remove diacritic marks (accents) – compatible with older JS targets
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
 * Read a single store JSON: outputs/bureauengros/<storeSlug>/data.json
 */
export function readBureauEnGrosDealsForStore(
  storeSlug: string
): BureauEnGrosDeal[] {
  const jsonPath = path.join(
    ROOT_DIR,
    "outputs",
    "bureauengros",
    storeSlug,
    "data.json"
  );

  if (!fs.existsSync(jsonPath)) {
    return [];
  }

  try {
    const raw = fs.readFileSync(jsonPath, "utf8");
    const parsed = JSON.parse(raw) as StoreFile | BureauEnGrosDeal[];

    // Old / current format: { store: {...}, products: [...] }
    if (!Array.isArray(parsed) && Array.isArray(parsed.products)) {
      return parsed.products;
    }

    // Fallback: if JSON is directly an array of products
    if (Array.isArray(parsed)) {
      return parsed;
    }

    return [];
  } catch (err) {
    console.error(
      `Failed to read Bureau en Gros deals for store ${storeSlug}`,
      err
    );
    return [];
  }
}
