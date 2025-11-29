import branches from "../data/bureauengros/stores.json";

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

type Branch = {
  id: string;
  name: string;
  address?: string;
  store?: string;
};

/**
 * Slug helper – compatible ES5 (pas de \p{Diacritic})
 */
export function slugify(value: string): string {
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

export function listBureauEnGrosStoreSlugs(): string[] {
  return BUREAU_EN_GROS_STORES.map((store) => store.slug);
}

export function getDefaultBureauEnGrosStoreSlug(): string | null {
  return BUREAU_EN_GROS_STORES[0]?.slug ?? null;
}
