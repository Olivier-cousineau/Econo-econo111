import stores from "../data/bureau-en-gros/stores.json";

export type BureauEnGrosStore = {
  id: string;
  slug: string;
  name: string;
  city: string;
  address: string;
  store?: string;
};

type RawStore = {
  id: string;
  name: string;
  address?: string;
  store?: string;
};

function slugify(value: string): string {
  return value
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/(^-|-$)/g, "");
}

function mapToStore(entry: RawStore): BureauEnGrosStore {
  const cityLabel = entry.name.split("–")[1]?.trim() ?? entry.name;
  const slug = `${entry.id}-${slugify(entry.name)}`;

  return {
    id: entry.id,
    slug,
    name: entry.name,
    city: cityLabel,
    address: entry.address ?? "",
    store: entry.store,
  };
}

const BUREAU_EN_GROS_STORES: BureauEnGrosStore[] = (stores as RawStore[]).map(
  mapToStore
);

export function listBureauEnGrosStores(): BureauEnGrosStore[] {
  return BUREAU_EN_GROS_STORES;
}

export function findBureauEnGrosStoreBySlug(
  slug: string
): BureauEnGrosStore | undefined {
  return BUREAU_EN_GROS_STORES.find((store) => store.slug === slug);
}

export function listBureauEnGrosStoreSlugs(): string[] {
  return BUREAU_EN_GROS_STORES.map((store) => store.slug);
}

export function getDefaultBureauEnGrosStoreSlug(): string | null {
  return BUREAU_EN_GROS_STORES[0]?.slug ?? null;
}
