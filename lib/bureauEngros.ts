import fs from "fs";
import path from "path";
import branches from "../data/bureauengros/stores.json";

const ROOT_DIR = process.cwd();
const BUREAU_EN_GROS_OUTPUTS_ROOT = path.join(
  ROOT_DIR,
  "outputs",
  "bureauengros"
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
  storeId?: string;
  storeName?: string;
  sourceStore?: string;
  scrapedAt?: string;
  url?: string;
  count?: number;
  products?: BureauEnGrosDeal[];
  store?: {
    id?: string;
    name?: string;
    address?: string;
    store?: string;
  };
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

function getBureauEnGrosStoreFilePath(storeSlug: string): string {
  return path.join(BUREAU_EN_GROS_OUTPUTS_ROOT, storeSlug, "data.json");
}

function getDefaultBureauEnGrosStoreSlug(): string | null {
  if (fs.existsSync(BUREAU_EN_GROS_OUTPUTS_ROOT)) {
    const entries = fs.readdirSync(BUREAU_EN_GROS_OUTPUTS_ROOT, {
      withFileTypes: true,
    });

    const firstDir = entries.find((entry) => entry.isDirectory());
    if (firstDir) {
      return firstDir.name;
    }
  }

  return BUREAU_EN_GROS_STORES[0]?.slug ?? null;
}

export function getBureauEnGrosStores(): BureauEnGrosStore[] {
  return BUREAU_EN_GROS_STORES;
}

export function getBureauEnGrosStoreBySlug(
  slug: string
): BureauEnGrosStore | undefined {
  return BUREAU_EN_GROS_STORES.find((s) => s.slug === slug);
}

export function listBureauEnGrosStoreSlugs(): string[] {
  return BUREAU_EN_GROS_STORES.map((store) => store.slug);
}

/**
 * Lit le fichier de données pour un magasin Bureau en Gros spécifique.
 * Les fichiers sont générés par le scraper et déposés dans
 * outputs/bureauengros/<storeSlug>/data.json.
 */
export function readBureauEnGrosStoreData(
  storeSlug: string
): SourceFileShape | null {
  const storeFilePath = getBureauEnGrosStoreFilePath(storeSlug);

  if (!fs.existsSync(storeFilePath)) {
    return null;
  }

  try {
    const raw = fs.readFileSync(storeFilePath, "utf8");
    const parsed = JSON.parse(raw) as SourceFileShape;

    if (!parsed.products || !Array.isArray(parsed.products)) {
      parsed.products = [];
    }

    if (typeof parsed.count !== "number") {
      parsed.count = parsed.products.length;
    }

    return parsed;
  } catch (err) {
    console.error("Failed to read Bureau en Gros store file:", storeFilePath, err);
    return null;
  }
}

/**
 * Lit les deals depuis le fichier outputs/bureauengros/<storeSlug>/data.json.
 * Si aucun magasin n'est précisé, on utilise le premier magasin disponible
 * pour rester compatible avec l'ancien comportement "global".
 */
export function readBureauEnGrosDealsForAllStores(
  storeSlug?: string
): BureauEnGrosDeal[] {
  const slug = storeSlug ?? getDefaultBureauEnGrosStoreSlug();
  if (!slug) {
    return [];
  }

  const storeData = readBureauEnGrosStoreData(slug);
  return storeData?.products ?? [];
}

export function readBureauEnGrosDealsForStore(
  storeSlug: string
): BureauEnGrosDeal[] {
  return readBureauEnGrosDealsForAllStores(storeSlug);
}
