import fs from 'fs/promises';
import path from 'path';

export interface BureauEnGrosProduct {
  title?: string;
  url?: string;
  link?: string;
  image?: string;
  image_url?: string;
  imageUrl?: string;
  price?: number;
  regularPrice?: number;
  originalPrice?: number;
  currentPrice?: number;
  salePrice?: number;
  discountPercent?: number;
  discount_price?: number;
  discountPrice?: number;
  productUrl?: string;
  availability?: string | null;
  [key: string]: unknown;
}

export interface BureauEnGrosStoreInfo {
  id?: string;
  name?: string;
  address?: string;
  store?: string;
}

export interface BureauEnGrosBranch {
  id?: string;
  name?: string;
  address?: string;
  store?: string;
  city?: string;
  provinceAndPostal?: string;
  slug: string;
}

export interface BureauEnGrosStoreData {
  store: BureauEnGrosStoreInfo | Record<string, unknown> | null;
  products: BureauEnGrosProduct[];
  branch?: BureauEnGrosBranch | null;
}

// Format « unifié » utilisé par le frontend (à adapter si ton code a déjà un type)
export type UnifiedDeal = {
  retailer: 'bureauengros';
  store_id: string;
  store_name: string;
  store_address: string;

  title: string;
  url: string;
  price: number;
  original_price: number | null;
  discount_percent: number | null;
  image: string | null;
};

const branchesPath = path.join(process.cwd(), 'data', 'bureauengros', 'branches.json');
const outputsRoot = path.join(process.cwd(), 'outputs', 'bureauengros');
const outputsRelativeRoot = path.posix.join('outputs', 'bureauengros');
const repoRawBaseUrl = 'https://raw.githubusercontent.com/Olivier-cousineau/Econo-econo111/main';

function slugify(value: unknown): string {
  if (value === undefined || value === null) return '';
  const text = String(value)
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '');
  return text.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '').replace(/--+/g, '-');
}

async function readBranchDirectory(): Promise<BureauEnGrosBranch[]> {
  try {
    const raw = await fs.readFile(branchesPath, 'utf-8');
    const parsed = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [];

    return parsed
      .map((entry) => {
        const address = entry?.address || '';
        const parts = address.split(',').map((part: string) => part.trim()).filter(Boolean);
        const city = parts[1] || '';
        const province = (parts[2] || '').split(/\s+/)[0] || '';
        const id = entry?.id ? String(entry.id).trim() : '';
        const providedSlug = typeof entry?.slug === 'string' ? entry.slug.trim() : '';
        const nameSlug = slugify(entry?.name || '');
        const slug = providedSlug || (id && nameSlug ? `${id}-${nameSlug}` : nameSlug || slugify(address || id || ''));
        if (!slug) return null;

        return {
          ...entry,
          id,
          city: city || entry?.name || '',
          provinceAndPostal: entry?.provinceAndPostal || '',
          slug,
          name: entry?.name || address || 'Succursale',
          store: entry?.store || 'Bureau en Gros',
        } satisfies BureauEnGrosBranch;
      })
      .filter(Boolean) as BureauEnGrosBranch[];
  } catch (error) {
    console.warn('Unable to read Bureau en Gros branches', error);
    return [];
  }
}

let branchCache: BureauEnGrosBranch[] | null = null;

export async function loadBureauEnGrosBranches(): Promise<BureauEnGrosBranch[]> {
  if (branchCache) return branchCache;
  branchCache = await readBranchDirectory();
  return branchCache;
}

export async function readBureauEnGrosDeals(branchSlug: string): Promise<BureauEnGrosStoreData> {
  return readBureauEnGrosStoreDeals(branchSlug);
}

function buildEncodedRepoPath(storeSlug: string) {
  const segments = [outputsRelativeRoot, storeSlug, 'data.json'];
  return segments
    .join('/')
    .split('/')
    .map((segment) => encodeURIComponent(segment))
    .join('/');
}

async function readFromLocal(dataPath: string) {
  const raw = await fs.readFile(dataPath, 'utf-8');
  return JSON.parse(raw);
}

async function readFromRemote(storeSlug: string) {
  const encodedPath = buildEncodedRepoPath(storeSlug);
  const url = `${repoRawBaseUrl}/${encodedPath}`;
  const response = await fetch(url);
  if (!response.ok) {
    throw new Error(`Failed to fetch ${url} (${response.status})`);
  }
  return response.json();
}

function pickNumber(...values: unknown[]): number | null {
  for (const value of values) {
    if (typeof value === 'number' && Number.isFinite(value)) {
      return value;
    }
  }
  return null;
}

export async function readBureauEnGrosStoreDeals(storeSlug: string): Promise<BureauEnGrosStoreData> {
  const normalizedSlug = storeSlug?.trim();
  if (!normalizedSlug) return { store: null, products: [], branch: null };

  const branches = await loadBureauEnGrosBranches();
  const branch = branches.find((entry) => entry.slug === normalizedSlug);
  if (!branch) {
    if (process.env.NODE_ENV !== 'production') {
      console.warn(`Unknown Bureau en Gros branch slug: ${normalizedSlug}`);
    }
    return { store: null, products: [], branch: null };
  }

  const dataPath = path.join(outputsRoot, normalizedSlug, 'data.json');
  const loaders = process.env.NODE_ENV === 'production'
    ? [() => readFromRemote(normalizedSlug), () => readFromLocal(dataPath)]
    : [() => readFromLocal(dataPath), () => readFromRemote(normalizedSlug)];

  for (const load of loaders) {
    try {
      const parsed = await load();
      const store = typeof parsed?.store === 'object' && parsed.store ? parsed.store : {};
      const products = Array.isArray(parsed?.products) ? parsed.products : [];
      return { store, products, branch };
    } catch (error) {
      if (process.env.NODE_ENV !== 'production') {
        console.warn(`Bureau en Gros data load attempt failed for ${normalizedSlug}`, error);
      }
    }
  }

  if (process.env.NODE_ENV !== 'production') {
    console.error(`Failed to load Bureau en Gros data for ${normalizedSlug}`);
  }

  return { store: null, products: [], branch };
}

export async function readBureauEnGrosDealsBySlug(storeSlug: string): Promise<UnifiedDeal[]> {
  const data = await readBureauEnGrosStoreDeals(storeSlug);

  const storeInfo = (data.store as BureauEnGrosStoreInfo | null) ?? null;
  const storeId = String(storeInfo?.id ?? data.branch?.id ?? storeSlug ?? '').trim();
  const storeName = (storeInfo?.name ?? data.branch?.name ?? storeInfo?.store ?? data.branch?.store ?? '').trim();
  const storeAddress = (storeInfo?.address ?? data.branch?.address ?? '').trim();

  return data.products.map((product) => {
    const price = pickNumber(
      product.currentPrice,
      product.salePrice,
      product.discountPrice,
      product.discount_price,
      product.price,
      product.regularPrice,
      product.originalPrice
    ) ?? 0;

    const originalPrice = pickNumber(product.originalPrice, product.regularPrice);
    const discountPercent = typeof product.discountPercent === 'number' && Number.isFinite(product.discountPercent)
      ? product.discountPercent
      : null;

    return {
      retailer: 'bureauengros',
      store_id: storeId,
      store_name: storeName,
      store_address: storeAddress,

      title: product.title ?? '',
      url: product.productUrl ?? product.url ?? product.link ?? '',
      price,
      original_price: originalPrice,
      discount_percent: discountPercent,
      image: (product.imageUrl ?? product.image_url ?? product.image ?? null) as string | null,
    } satisfies UnifiedDeal;
  });
}
