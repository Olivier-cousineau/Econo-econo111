import fs from "fs";
import path from "path";
import {
  BureauEnGrosDeal,
  getDefaultBureauEnGrosStoreSlug,
  listBureauEnGrosStoreSlugs,
} from "../bureauEngros";

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

const ROOT_DIR = process.cwd();
const BUREAU_EN_GROS_PUBLIC_ROOT = path.join(
  ROOT_DIR,
  "public",
  "bureau-en-gros"
);

function getBureauEnGrosStoreFilePath(storeSlug: string): string {
  return path.join(BUREAU_EN_GROS_PUBLIC_ROOT, storeSlug, "data.json");
}

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
    console.error(
      "Failed to read Bureau en Gros store file:",
      storeFilePath,
      err
    );
    return null;
  }
}

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

export function listAvailableBureauEnGrosStoreSlugs(): string[] {
  const explicitSlugs = listBureauEnGrosStoreSlugs();

  if (!fs.existsSync(BUREAU_EN_GROS_PUBLIC_ROOT)) {
    return explicitSlugs;
  }

  const directories = fs
    .readdirSync(BUREAU_EN_GROS_PUBLIC_ROOT, { withFileTypes: true })
    .filter((entry) => entry.isDirectory())
    .map((entry) => entry.name);

  return Array.from(new Set([...directories, ...explicitSlugs]));
}
