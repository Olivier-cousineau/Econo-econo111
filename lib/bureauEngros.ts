// lib/bureauEngros.ts
import branches from '../data/bureauengros/branches.json';

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

function slugify(value: string): string {
  return value
    .normalize('NFD')
    .replace(/\p{Diacritic}/gu, '')
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/(^-|-$)/g, '');
}

function branchToStore(branch: Branch): BureauEnGrosStore {
  const cityLabel = branch.name.split('–')[1]?.trim() ?? branch.name;
  const slug = `${branch.id}-${slugify(branch.name)}`;

  return {
    id: branch.id,
    slug,
    name: branch.name,
    city: cityLabel,
    address: branch.address ?? '',
    store: branch.store,
  };
}

const BUREAU_EN_GROS_STORES: BureauEnGrosStore[] = (branches as Branch[]).map(
  branchToStore,
);

export function getBureauEnGrosStores(): BureauEnGrosStore[] {
  return BUREAU_EN_GROS_STORES;
}

export function listBureauEnGrosStoreSlugs(): string[] {
  return BUREAU_EN_GROS_STORES.map((store) => store.slug);
}

// For now: no deals in this repo
export function readBureauEnGrosDealsForAllStores(): any[] {
  return [];
}
