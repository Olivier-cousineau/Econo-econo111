// lib/bureauEnGrosDeals.js
import {
  getDefaultBureauEnGrosStoreSlug,
  listBureauEnGrosStoreSlugs,
} from './bureauEngros';

export async function readBureauEnGrosDealsForStore(storeSlug) {
  const res = await fetch(`/bureau-en-gros/${storeSlug}/data.json`);
  if (!res.ok) {
    throw new Error(
      `Failed to load Bureau en Gros deals for ${storeSlug} (${res.status})`
    );
  }
  return res.json();
}

/**
 * Charge les deals Bureau en Gros à partir des fichiers publics.
 * Le même contenu est utilisé pour tous les magasins lorsqu'aucun store n'est précisé.
 */
export async function loadBureauEnGrosDeals({ store, minDiscount = 0 } = {}) {
  try {
    const storeSlugs = listBureauEnGrosStoreSlugs();
    const defaultStore = getDefaultBureauEnGrosStoreSlug();
    const targetStore = store || defaultStore;

    if (!targetStore) {
      console.warn('loadBureauEnGrosDeals: aucun magasin disponible');
      return [];
    }

    if (storeSlugs.length > 0 && store && !storeSlugs.includes(store)) {
      console.warn('loadBureauEnGrosDeals: store slug not found in metadata', store);
      return [];
    }

    const data = await readBureauEnGrosDealsForStore(targetStore);
    const products = Array.isArray(data.products) ? data.products : [];

    if (!Array.isArray(products) || products.length === 0) {
      return [];
    }

    return products.filter((p) => {
      const discount =
        typeof p.discount === 'number'
          ? p.discount
          : typeof p.discountPercent === 'number'
          ? p.discountPercent
          : 0;

      return discount >= minDiscount;
    });
  } catch (err) {
    console.error(`Error loading Bureau en Gros deals:`, err);
    return [];
  }
}
